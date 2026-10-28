# story-server/tests/test_summary_api.py

"""
굴리는 요약(app/memory/summarizer.py)을 API 로 검증한다. 실제 DB(story_test)에서 돈다.
asset 서버, 모델은 가짜다(tests/assets.py, tests/models.py).

보는 것.
  - 말 한 번이 끝나면 따로 돌아, 창 밖으로 밀려난 말이 기준만큼 쌓였으면 요약을 쓴다(원가를 적는다)
  - 다음 말의 카드에 "[앞의 줄거리]" 로 들어간다. GET /summary 가 지금 가지의 요약을 돌려준다
  - SUMMARY_MODEL 이 비어 있으면 요약하지 않는다. 요약의 모델을 부르지 못해도 이야기는 이어진다
  - 같은 호출에서 메모를 제안받는다. 제안은 받아들이기 전에는 모델에 가지 않고, 받아들이면 다음 말부터 간다.
    잘린 요약은 제안하지 않는다. 받아들이려면 자리가 있어야 하고, 기다리는 제안은 상한까지만 쌓인다
"""

import asyncio
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.memory.models import NOTES_PER_CONVERSATION, PROPOSALS_PER_CONVERSATION, MemoryNote, Summary
from app.memory.service import add_proposals
from tests.assets import FakeAsset
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, bearer, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

# 창(지난 말의 양)을 작게 두고 긴 말을 보내 앞의 말이 빨리 밀려나게 한다
LONG = '가' * 900


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter()
    app.state.model_router = fake
    return fake


@pytest.fixture
def summarizing(app: FastAPI, settings: Settings) -> None:
    """요약을 켠다. 밀려난 말이 둘 쌓이면 luna 로 요약한다."""
    app.state.settings = settings.model_copy(
        update={'summary_model': 'luna', 'summary_after_messages': 2, 'story_context_chars': 1000}
    )


@pytest.fixture
async def conversation(clean_tables: None, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict):
    await turn_on_luna(session)
    return await start_with_luna(client, asset, mine)


async def say(app: FastAPI, client: AsyncClient, headers: dict, conversation: dict, content: str = LONG) -> None:
    """말을 하나 보내고, 답과 그 뒤의 요약이 끝나기를 기다린다."""
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    response = await client.post(url, json={'content': content}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))
    await asyncio.gather(*list(app.state.summarizer.tasks))


def last_card(router: FakeRouter) -> str:
    """마지막 말 한 번의 카드(요약을 시킨 호출은 뺀다)."""
    cards = [messages[0].content for messages, _ in router.provider.calls if '[세계관]' in messages[0].content]
    return cards[-1]


async def summaries(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Summary))


async def test_a_summary_is_written_and_goes_to_the_card(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    router: FakeRouter,
    summarizing: None,
    conversation: dict,
    mine: dict,
):
    for _ in range(3):
        await say(app, client, mine, conversation)

    read = (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}/summary', headers=mine)).json()
    await say(app, client, mine, conversation, '안녕')

    row = (await session.scalars(select(Summary))).first()
    assert (row.model_slug, row.input_tokens, row.cost_usd is not None) == ('luna', 1000, True)
    assert read['text'] == row.text and read['covered_up_to'] == str(row.message_id)
    assert f'[앞의 줄거리]\n{row.text}' in last_card(router)
    # 요약을 시키는 호출은 이야기의 지시로 갔다
    asked = [messages for messages, _ in router.provider.calls if '[이어진 이야기]' in messages[-1].content]
    assert asked and '이야기를 요약하는 도우미' in asked[0][0].content


async def test_no_summary_without_a_summary_model(
    client: AsyncClient, app: FastAPI, session: AsyncSession, router: FakeRouter, conversation: dict, mine: dict
):
    for _ in range(3):
        await say(app, client, mine, conversation)

    assert await summaries(session) == 0
    response = await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}/summary', headers=mine)
    assert (response.status_code, response.json()) == (status.HTTP_200_OK, None)


async def test_a_failing_summary_model_leaves_the_story_going(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    router: FakeRouter,
    summarizing: None,
    conversation: dict,
    mine: dict,
):
    await say(app, client, mine, conversation)
    router.refuse = 'provider_unavailable'

    assert await app.state.summarizer.summarize(uuid.UUID(conversation['id'])) is False
    assert await summaries(session) == 0


# --- 요약이 제안하는 메모 ---

NOTES_REPLY = ['둘은 해변에서 만났다.\n<notes>\n1. 미나는 바다를 좋아한다.\n2. 축제에 같이 가기로 했다.\n</notes>']


async def summarize_now(app: FastAPI, router: FakeRouter, conversation: dict, pieces: list[str], truncated=False):
    """요약을 시키는 호출의 답을 pieces 로 바꿔 지금 요약한다."""
    router.provider.pieces, router.provider.truncated = pieces, truncated
    return await app.state.summarizer.write(uuid.UUID(conversation['id']))


async def notes_of(client: AsyncClient, headers: dict, conversation: dict) -> list[dict]:
    return (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}/notes', headers=headers)).json()


async def test_the_summary_proposes_notes_that_wait_to_be_accepted(
    client: AsyncClient,
    app: FastAPI,
    router: FakeRouter,
    summarizing: None,
    conversation: dict,
    mine: dict,
):
    app.state.settings = app.state.settings.model_copy(update={'summary_after_messages': 200})
    for _ in range(3):
        await say(app, client, mine, conversation)
    app.state.settings = app.state.settings.model_copy(update={'summary_after_messages': 2})
    assert await summarize_now(app, router, conversation, NOTES_REPLY) is True

    proposed = await notes_of(client, mine, conversation)
    router.provider.pieces = ['@narration: 바람.']
    await say(app, client, mine, conversation, '안녕')

    # 한 번에 더한 제안은 같은 시각이라 차례를 보지 않는다
    assert sorted((note['text'], note['source'], note['pending']) for note in proposed) == [
        ('미나는 바다를 좋아한다.', 'summary', True),
        ('축제에 같이 가기로 했다.', 'summary', True),
    ]
    proposed = [note for note in proposed if note['text'].startswith('미나')]
    # 받아들이기 전에는 모델에 가지 않는다. 줄거리에는 제안이 섞이지 않는다
    assert '바다를 좋아한다' not in last_card(router)
    assert '[앞의 줄거리]\n둘은 해변에서 만났다.\n' in last_card(router)
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/notes/{proposed[0]["id"]}/accept'
    accepted = (await client.post(url, headers=mine)).json()
    assert (accepted['pending'], accepted['accepted_at'] is not None) == (False, True)
    await say(app, client, mine, conversation, '안녕')
    assert '[기억]\n- 미나는 바다를 좋아한다.' in last_card(router)


async def test_a_cut_summary_proposes_nothing(
    client: AsyncClient,
    app: FastAPI,
    router: FakeRouter,
    summarizing: None,
    conversation: dict,
    mine: dict,
):
    app.state.settings = app.state.settings.model_copy(update={'summary_after_messages': 200})
    for _ in range(3):
        await say(app, client, mine, conversation)
    app.state.settings = app.state.settings.model_copy(update={'summary_after_messages': 2})

    assert await summarize_now(app, router, conversation, NOTES_REPLY, truncated=True) is True

    assert await notes_of(client, mine, conversation) == []


async def test_accepting_needs_room_and_user_notes_need_no_accepting(
    client: AsyncClient, session: AsyncSession, conversation: dict, mine: dict
):
    conversation_id = uuid.UUID(conversation['id'])
    session.add_all(MemoryNote(conversation_id=conversation_id, text=f'{n}') for n in range(NOTES_PER_CONVERSATION))
    proposal = MemoryNote(conversation_id=conversation_id, text='제안', source='summary')
    session.add(proposal)
    await session.commit()
    notes = await notes_of(client, mine, conversation)
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/notes'

    # 가득 차도 제안은 수에 들지 않아 보인다. 받아들이려면 자리가 있어야 한다
    full = await client.post(f'{url}/{proposal.id}/accept', headers=mine)
    user_note = next(note for note in notes if note['source'] == 'user')
    mine_note = await client.post(f'{url}/{user_note["id"]}/accept', headers=mine)

    assert (full.status_code, full.json()['code']) == (status.HTTP_409_CONFLICT, 'notes_full')
    assert (mine_note.status_code, mine_note.json()['source'], mine_note.json()['pending']) == (200, 'user', False)
    assert len(notes) == NOTES_PER_CONVERSATION + 1


async def test_proposals_stop_at_the_waiting_limit(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, mine: dict
):
    conversation_id = uuid.UUID(conversation['id'])
    session.add_all(
        MemoryNote(conversation_id=conversation_id, text=f'제안 {n}', source='summary')
        for n in range(PROPOSALS_PER_CONVERSATION - 1)
    )
    await session.commit()

    async with app.state.session_factory() as fresh:
        added = await add_proposals(fresh, conversation_id, ['새 제안 하나', '새 제안 둘', '제안 0'])
        await fresh.commit()

    assert [note.text for note in added] == ['새 제안 하나']
