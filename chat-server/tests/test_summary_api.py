# chat-server/tests/test_summary_api.py

"""
굴리는 요약(app/memory/summarizer.py)을 API 로 검증한다. 실제 DB(chat_test)에서 돈다. asset 서버와 모델은 가짜다.

보는 것.
  - 말 한 번이 끝나면 따로 돌아, 창 밖으로 밀려난 말이 쌓였으면 싼 모델(SUMMARY_MODEL)로 요약을 쓴다.
    요약은 밀려난 마지막 말에 붙고, 모델과 토큰과 원가가 적힌다. 다음 말의 카드에 "[앞의 줄거리]" 로 간다
  - 다음 요약은 앞의 요약과 그 뒤의 말로 굴린다
  - 요약을 끄면(SUMMARY_MODEL 이 비었다) 부르지 않는다. 밀려난 말이 적으면 쓰지 않는다
  - 요약이 실패해도 대화는 이어진다. 다른 가지로 가면 그 가지의 요약만 쓴다
  - 요약은 GET /summary 로 읽는다(없으면 null). 남의 대화는 404
  - 같은 말의 요약은 하나만 남는다. 서버가 꺼지면 도는 요약을 멈춘다
"""

import asyncio
import uuid
from dataclasses import dataclass

import pytest
from ai_core.provider import ProviderError
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory import repository
from app.memory.models import Summary
from app.memory.summaries import overflow
from tests.assets import FakeAsset
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, bearer, parse_sse, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables', 'router')

SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')
# 창에 서너 말만 드는 긴 말
LONG = '가' * 400


@dataclass(frozen=True)
class Said:
    id: uuid.UUID
    role: str
    content: str


class Answers(ScriptedProvider):
    """대화에는 짧은 답을, 요약을 시키면 줄거리를 준다. 요약의 부름을 따로 적는다."""

    summaries: list = []
    story: str | None = None

    async def complete(self, messages, params, on_text=None):
        if '요약하는 도우미' in messages[0].content:
            self.summaries.append(messages)
            if self.error is not None:
                raise self.error
            story = self.story if self.story is not None else f'줄거리 {len(self.summaries)}'
            return await ScriptedProvider(pieces=[story]).complete(messages, params)
        self.calls.append((list(messages), params))
        return await ScriptedProvider(pieces=['응.']).complete(messages, params, on_text or (lambda text: None))


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def provider() -> Answers:
    answers = Answers()
    answers.summaries = []
    return answers


@pytest.fixture
def router(app: FastAPI, provider: Answers) -> FakeRouter:
    fake = FakeRouter(provider)
    app.state.model_router = fake
    return fake


@pytest.fixture
def summarizing(app: FastAPI) -> None:
    """요약을 켠다. 창은 1,000자, 밀려난 말이 둘이면 요약한다."""
    app.state.settings = app.state.settings.model_copy(
        update={'summary_model': 'luna', 'chat_context_chars': 1000, 'summary_after_messages': 2}
    )


@pytest.fixture
async def conversation(clean_tables: None, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict):
    await turn_on_luna(session)
    return await start_with_luna(client, asset, mine)


async def say(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict, content: str = LONG) -> list:
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    response = await client.post(url, json={'content': content}, headers=headers)
    await asyncio.gather(*list(app.state.turns))
    await asyncio.gather(*list(app.state.summarizer.tasks))
    assert response.status_code == status.HTTP_200_OK, response.text
    return parse_sse(response.text)


async def summaries(session: AsyncSession) -> list[Summary]:
    session.expire_all()
    return list(await session.scalars(select(Summary).order_by(Summary.created_at)))


@pytest.mark.usefixtures('summarizing')
async def test_overflowing_messages_are_summarized_and_sent_as_the_story(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    for _ in range(3):
        await say(client, app, mine, conversation)

    (written,) = await summaries(session)
    assert (written.text, written.model_slug, written.input_tokens) == ('줄거리 1', 'luna', 1000)
    # 밀려난 마지막 말에 붙는다
    detail = (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)).json()
    path = [Said(uuid.UUID(m['id']), m['role'], m['content']) for m in detail['messages']]
    assert written.message_id == overflow(path, 1000)[-1].id
    assert written.cost_usd is not None
    # 다음 말의 카드에 들어간다
    await say(client, app, mine, conversation, '안녕')
    card = router.provider.calls[-1][0][0].content
    assert '[앞의 줄거리]\n줄거리 1' in card


@pytest.mark.usefixtures('summarizing')
async def test_the_next_summary_rolls_from_the_last(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, provider: Answers, mine: dict
):
    for _ in range(6):
        await say(client, app, mine, conversation)

    written = await summaries(session)
    assert len(written) >= 2
    assert '[앞의 줄거리]\n줄거리 1' in provider.summaries[1][1].content
    # 읽으면 지금 가지의 가장 뒤의 요약이다
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/summary'
    assert (await client.get(url, headers=mine)).json()['text'] == written[-1].text


async def test_nothing_is_summarized_when_it_is_off(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, provider: Answers, mine: dict
):
    app.state.settings = app.state.settings.model_copy(update={'chat_context_chars': 1000})
    for _ in range(3):
        await say(client, app, mine, conversation)

    assert (await summaries(session), provider.summaries) == ([], [])


@pytest.mark.usefixtures('summarizing')
async def test_a_short_conversation_is_not_summarized(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, provider: Answers, mine: dict
):
    await say(client, app, mine, conversation, '안녕')

    assert (await summaries(session), provider.summaries) == ([], [])


@pytest.mark.usefixtures('summarizing')
async def test_a_failed_summary_does_not_stop_the_conversation(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, provider: Answers, mine: dict
):
    provider.error = ProviderError('timeout')
    for _ in range(3):
        await say(client, app, mine, conversation)

    last = await say(client, app, mine, conversation, '안녕')

    assert last[-1][0] == 'done'
    assert await summaries(session) == []


@pytest.mark.usefixtures('summarizing')
async def test_another_branch_uses_only_its_own_summary(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    first = (await say(client, app, mine, conversation))[0][1]['user_message']
    for _ in range(2):
        await say(client, app, mine, conversation)
    assert len(await summaries(session)) == 1

    # 첫 말을 고쳐 새 가지로 가면 앞의 요약은 이 가지에 없다
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    await client.post(url, json={'content': '다시', 'edit_of': first['id']}, headers=mine)
    await asyncio.gather(*list(app.state.turns))

    assert '[앞의 줄거리]' not in router.provider.calls[-1][0][0].content


@pytest.mark.usefixtures('summarizing')
async def test_the_summary_is_read_on_its_own(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict, signing_key: SigningKey
):
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/summary'
    before = await client.get(url, headers=mine)
    for _ in range(3):
        await say(client, app, mine, conversation)

    after = (await client.get(url, headers=mine)).json()
    theirs = await client.get(url, headers=bearer(signing_key, SOMEONE_ELSE))

    assert (before.status_code, before.json()) == (status.HTTP_200_OK, None)
    assert after['text'] == '줄거리 1' and after['covered_up_to']
    assert theirs.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.usefixtures('summarizing')
async def test_an_empty_summary_is_not_kept(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, provider: Answers, mine: dict
):
    provider.story = '  '
    for _ in range(3):
        await say(client, app, mine, conversation)

    assert provider.summaries and await summaries(session) == []


@pytest.mark.usefixtures('summarizing')
async def test_a_deleted_conversation_is_not_summarized(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, provider: Answers, mine: dict
):
    app.state.settings = app.state.settings.model_copy(update={'summary_model': ''})
    for _ in range(3):
        await say(client, app, mine, conversation)
    await client.delete(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)
    app.state.settings = app.state.settings.model_copy(update={'summary_model': 'luna'})

    assert await app.state.summarizer.summarize(uuid.UUID(conversation['id'])) is False
    assert provider.summaries == []


@pytest.mark.usefixtures('summarizing')
async def test_a_summary_inside_the_window_is_not_sent(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    answer = (await say(client, app, mine, conversation, '안녕'))[-1][1]['message']
    session.add(
        Summary(
            message_id=uuid.UUID(answer['id']),
            conversation_id=uuid.UUID(conversation['id']),
            text='창 안의 요약',
            model_slug='luna',
        )
    )
    await session.commit()

    await say(client, app, mine, conversation, '또')

    # 창에 든 말은 그대로 가니 요약을 겹쳐 보내지 않는다
    assert '창 안의 요약' not in router.provider.calls[-1][0][0].content


async def test_the_same_message_keeps_one_summary(session: AsyncSession, conversation: dict):
    greeting = uuid.UUID(conversation['messages'][0]['id'])
    for text in ('먼저', '나중'):
        await repository.add_summary(
            session,
            Summary(message_id=greeting, conversation_id=uuid.UUID(conversation['id']), text=text, model_slug='luna'),
        )
        await session.commit()

    assert [summary.text for summary in await summaries(session)] == ['먼저']
    assert await session.scalar(select(func.count()).select_from(Summary)) == 1


@pytest.mark.usefixtures('summarizing')
async def test_one_conversation_is_summarized_once_at_a_time(app: FastAPI, conversation: dict, router: FakeRouter):
    hold = asyncio.Event()

    async def slow_write(conversation_id):
        await hold.wait()
        return True

    app.state.summarizer.write = slow_write
    conversation_id = uuid.UUID(conversation['id'])

    app.state.summarizer.request(conversation_id)
    app.state.summarizer.request(conversation_id)

    assert len(app.state.summarizer.tasks) == 1
    hold.set()
    await asyncio.gather(*list(app.state.summarizer.tasks))
    assert app.state.summarizer.running == set()


@pytest.mark.usefixtures('summarizing')
async def test_shutdown_stops_the_summaries(app: FastAPI, conversation: dict):
    async def forever(conversation_id):
        await asyncio.Event().wait()

    app.state.summarizer.write = forever
    app.state.summarizer.request(uuid.UUID(conversation['id']))
    (task,) = app.state.summarizer.tasks

    await app.state.summarizer.stop()

    assert task.cancelled()
