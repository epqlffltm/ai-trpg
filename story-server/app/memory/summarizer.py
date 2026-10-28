# story-server/app/memory/summarizer.py

"""
굴리는 요약을 쓰는 작업(chat 과 같다). 말 한 번이 끝나면 그 세션을 한 번 보고, 요약할 때가 되었으면 따로 돌아 쓴다.

  - 응답과 따로 돈다. 사람은 기다리지 않는다. 실패해도 이야기는 이어진다(로그 story.summary).
    다음 말 한 번이 끝나면 다시 본다
  - 싼 모델(SUMMARY_MODEL)로 부른다. 모델 목록의 이름표다. 사용자에게 팔지 않는(꺼 둔) 모델도 쓴다.
    비우면 요약하지 않는다. 원가는 서비스가 낸다(청구하지 않고 요약의 행에 적어 둔다)
  - 한 세션에 한 번에 하나만 돈다(이 서버 안). 서버가 여럿이라 같은 요약을 둘이 써도 먼저 쓴 것이 남는다
  - 서버가 꺼질 때 멈춘다(stop). 쓰다 만 요약은 버린다. 다음 말 한 번이 다시 쓴다
DB 연결은 읽을 때와 적을 때만 잡는다. 모델을 부르는 동안에는 잡지 않는다.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from ai_core.costs import charge_of
from ai_core.provider import GenerationParams
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.conversations import repository as conversations
from app.conversations.models import Conversation
from app.core.config import Settings
from app.memory import repository
from app.memory.models import Summary
from app.memory.summaries import SUMMARY_OUTPUT_LIMIT, Plan, overflow, plan_summary, summary_messages
from app.turns.providers import Router

logger = logging.getLogger(__name__)

# 요약의 다양함. 사실을 옮기는 일이라 낮게 둔다
SUMMARY_TEMPERATURE = 0.3
# 로그의 operation
SUMMARY_OPERATION = 'story.summary'


@dataclass
class Summarizer:
    """
    요약을 쓰는 작업. 앱에 하나 둔다(app.state.summarizer).

    router 와 settings 는 부를 때마다 앱에서 꺼낸다. 테스트가 바꿔 꽂으면 그 뒤부터 바뀐 것을 쓴다.
    """

    session_factory: async_sessionmaker[AsyncSession]
    router: Callable[[], Router]
    settings: Callable[[], Settings]
    running: set[uuid.UUID] = field(default_factory=set)
    tasks: set[asyncio.Task] = field(default_factory=set)

    def request(self, conversation_id: uuid.UUID) -> None:
        """그 세션을 요약할지 보러 간다(따로 돈다). 요약을 끄거나 이미 보는 중이면 하지 않는다."""
        if not self.settings().summary_model or conversation_id in self.running:
            return
        self.running.add(conversation_id)
        task = asyncio.create_task(self.summarize(conversation_id))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        task.add_done_callback(lambda _: self.running.discard(conversation_id))

    async def summarize(self, conversation_id: uuid.UUID) -> bool:
        """요약할 때가 되었으면 쓴다. 썼으면 True. 실패는 로그에 남기고 False(이야기는 이어진다)."""
        try:
            return await self.write(conversation_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                '요약을 쓰지 못했습니다',
                extra={'operation': SUMMARY_OPERATION, 'conversation_id': str(conversation_id)},
            )
            return False

    async def plan(self, conversation_id: uuid.UUID) -> Plan | None:
        """지금 가지에서 요약할 것. 세션이 없거나(지웠다) 아직 때가 아니면 None."""
        settings = self.settings()
        async with self.session_factory() as session:
            conversation = await session.get(Conversation, conversation_id)
            if conversation is None:
                return None
            path = await conversations.active_path(session, conversation.active_leaf_id)
            dropped = overflow(path, settings.story_context_chars)
            summaries = await repository.summaries_on(session, [message.id for message in dropped])
        return plan_summary(dropped, summaries, settings.summary_after_messages)

    async def write(self, conversation_id: uuid.UUID) -> bool:
        """요약할 것이 있으면 모델을 불러 요약을 적는다. 모델이 빈 줄거리를 주면 적지 않는다."""
        plan = await self.plan(conversation_id)
        if plan is None:
            return False
        slug = self.settings().summary_model
        route = await self.router().route(slug, allow_disabled=True)
        params = GenerationParams(max_tokens=SUMMARY_OUTPUT_LIMIT, temperature=SUMMARY_TEMPERATURE)
        completion = await route.provider.complete(summary_messages(plan), params)
        text = completion.text.strip()
        if not text:
            return False
        cost, _ = charge_of(completion, route.price)
        summary = Summary(
            message_id=plan.fresh[-1].id,
            conversation_id=conversation_id,
            text=text,
            model_slug=slug,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            cost_usd=cost,
        )
        async with self.session_factory() as session:
            await repository.add_summary(session, summary)
            await session.commit()
        return True

    async def stop(self) -> None:
        """도는 요약을 모두 멈추고 끝나기를 기다린다. 서버가 꺼질 때 부른다."""
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
