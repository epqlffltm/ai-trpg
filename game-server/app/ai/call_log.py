# game-server/app/ai/call_log.py

"""
AI 호출의 기록을 DB(ai_invocations)에 쓰는 기록장. app/ai/calls.py 의 CallLog 모양을 따른다.

기록 하나를 쓸 때마다 세션을 따로 열고 바로 저장한다. 게임의 상태를 바꾸는 트랜잭션과 섞지 않는다.
  - 모델을 부르는 동안에는 DB 연결을 쥐고 있지 않다(app/rounds/closing.py). 기록은 부른 뒤에 쓴다.
  - 실패한 호출도 남아야 한다. 게임의 트랜잭션에 넣으면, 그 트랜잭션이 없는 실패의 길에서는 기록이 사라진다.
  - 서술이 다른 작업에 밀려 버려져도(같은 라운드를 두 번 맡긴 경우) 그 호출은 시간과 토큰을 썼다. 남긴다.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.calls import CallRecord
from app.ai.models import AiInvocation


def to_row(record: CallRecord) -> AiInvocation:
    """기록을 DB 의 한 줄로 바꾼다. 아직 저장하지 않는다."""
    scope = record.scope
    return AiInvocation(
        purpose=scope.purpose,
        table_id=scope.table_id,
        round_number=scope.round_number,
        host_id=scope.host_id,
        provider=record.provider,
        model=record.model,
        prompt_version=record.prompt_version,
        reasoning=record.reasoning,
        narration_style=record.narration_style,
        outcome=record.outcome,
        error=record.error,
        latency_ms=record.latency_ms,
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
        finish_reason=record.finish_reason,
        text=record.text,
    )


@dataclass(frozen=True)
class DbCallLog:
    """
    DB 에 쓰는 기록장. 앱이 만들 때 세션 틀을 넣는다(app/rounds/narrator_setup.py).

    쓰다가 실패하면(DB 가 내려감) 예외를 그대로 올린다. 기록 없이 넘어가지 않는다.
    """

    session_factory: async_sessionmaker[AsyncSession]

    async def write(self, record: CallRecord) -> None:
        """기록 하나를 새 세션으로 저장한다."""
        async with self.session_factory() as session:
            session.add(to_row(record))
            await session.commit()
