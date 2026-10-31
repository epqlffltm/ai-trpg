# story-server/tests/test_session_copy_api.py

"""
플레이 복사(POST /conversations/{id}/copy, app/conversations/copying.py)를 검증한다. 실제 DB(story_test)에서 돈다.
asset 서버, 모델은 가짜다(tests/assets.py, tests/models.py).

보는 것.
  - 지금 가지의 말들이 같은 차례, 같은 글과 조각으로 새 세션에 복사된다. 말의 id 는 새것이고 가지의 끝도 이어진다
  - 말에 붙은 상태, 기억 메모, 페르소나의 사본, 모델, 굳힌 엔딩이 함께 옮겨진다. 요약은 원가 없이 옮겨진다
  - 다른 가지(대안)와 청구 기록은 옮기지 않는다. 판의 사본은 같은 것을 가리킨다. 원래 세션은 그대로다
  - 복사한 세션에서 이어 하면 원래 세션은 바뀌지 않는다
  - 답을 쓰는 중이면 409 generation_in_progress, 남의 것과 없는 것은 404 다
"""

import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, ImportedWorld, Message, MessageState
from app.memory.models import MemoryNote, NoteSource, Summary
from app.turns.models import Generation
from tests.assets import FakeAsset, make_persona, make_world
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, WORLD_FIELDS, bearer, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

MESSAGES_URL = CONVERSATIONS_URL.replace('/conversations', '/messages')
THEM = uuid.UUID('99999999-2222-4333-8444-555555555555')
PATHS = [{'a': 'home', 'b': 'beach', 'minutes': 30}]


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter()
    app.state.model_router = fake
    return fake


async def finished(app: FastAPI) -> None:
    await asyncio.gather(*list(app.state.turns))


async def say(client: AsyncClient, app: FastAPI, headers: dict, conversation_id: str, content: str) -> None:
    response = await client.post(
        f'{CONVERSATIONS_URL}/{conversation_id}/messages', json={'content': content}, headers=headers
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    await finished(app)


async def move(client: AsyncClient, app: FastAPI, headers: dict, conversation_id: str) -> None:
    body = {'kind': 'move', 'place': 'beach'}
    response = await client.post(f'{CONVERSATIONS_URL}/{conversation_id}/actions', json=body, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await finished(app)


async def detail(client: AsyncClient, headers: dict, conversation_id: str) -> dict:
    return (await client.get(f'{CONVERSATIONS_URL}/{conversation_id}', headers=headers)).json()


async def copy(client: AsyncClient, headers: dict, conversation_id: str):
    return await client.post(f'{CONVERSATIONS_URL}/{conversation_id}/copy', headers=headers)


async def count(session: AsyncSession, model: type, *where) -> int:
    return await session.scalar(select(func.count()).select_from(model).where(*where))


@pytest.fixture
async def played(
    clean_tables: None, client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router, mine
) -> dict:
    """
    페르소나로 시작해 말 하나, 이동 하나, 말 하나를 한 세션. 첫 답은 다시 생성해 대안이 둘이다.
    기억 메모 하나와 첫 답에 붙은 요약 하나가 있고, 시작할 때 본 엔딩(solo)이 굳어 있다.
    """
    await turn_on_luna(session)
    world = asset.add_world(make_world_with_paths())
    persona = asset.add_persona(make_persona())
    body = {'world_id': str(world.id), 'model': 'luna', 'persona_id': str(persona.id)}
    started = (await client.post(CONVERSATIONS_URL, json=body, headers=mine)).json()
    conversation_id = started['id']
    await say(client, app, mine, conversation_id, '안녕')
    first_answer = (await detail(client, mine, conversation_id))['messages'][-1]
    response = await client.post(f'{MESSAGES_URL}/{first_answer["id"]}/regenerate', headers=mine)
    assert response.status_code == status.HTTP_200_OK, response.text
    await finished(app)
    await move(client, app, mine, conversation_id)
    await say(client, app, mine, conversation_id, '바다다')
    source = uuid.UUID(conversation_id)
    answer = (await detail(client, mine, conversation_id))['messages'][1]
    session.add(MemoryNote(conversation_id=source, text='미나는 바다를 좋아한다.', source=NoteSource.USER))
    session.add(
        Summary(
            message_id=uuid.UUID(answer['id']),
            conversation_id=source,
            text='처음 만났다.',
            model_slug='luna',
            input_tokens=100,
            output_tokens=20,
            cost_usd=Decimal('0.001'),
        )
    )
    await session.execute(update(Conversation).where(Conversation.id == source).values(cleared_endings=['solo']))
    await session.commit()
    return await detail(client, mine, conversation_id)


def make_world_with_paths():
    return make_world(fields={**WORLD_FIELDS, 'paths': PATHS})


def comparable(message: dict) -> tuple:
    """말에서 복사한 뒤에도 같아야 하는 칸들."""
    return (
        message['role'],
        message['content'],
        message['status'],
        message.get('segments'),
        message.get('cast'),
        message.get('event_id'),
        message.get('ending_id'),
        message.get('edited'),
    )


async def test_the_branch_is_copied_into_a_new_session(
    client: AsyncClient, session: AsyncSession, played: dict, mine: dict
):
    response = await copy(client, mine, played['id'])

    assert response.status_code == status.HTTP_201_CREATED, response.text
    copied = response.json()
    assert copied['id'] != played['id']
    assert copied['title'] == f'{played["title"]} (복사)'
    assert [comparable(message) for message in copied['messages']] == [comparable(m) for m in played['messages']]
    assert not {message['id'] for message in copied['messages']} & {message['id'] for message in played['messages']}
    # 대안은 옮기지 않는다. 복사한 세션의 첫 답에는 대안이 하나뿐이다
    assert [len(message['alternatives']) for message in copied['messages']][1] == 1
    assert (copied['state'], copied['model'], copied['persona']) == (
        played['state'],
        played['model'],
        played['persona'],
    )
    assert copied['world'] == played['world']


async def test_states_notes_summaries_and_cleared_endings_come_along(
    client: AsyncClient, session: AsyncSession, played: dict, mine: dict
):
    copied_id = uuid.UUID((await copy(client, mine, played['id'])).json()['id'])
    source_id = uuid.UUID(played['id'])

    copied, source = await session.get(Conversation, copied_id), await session.get(Conversation, source_id)
    assert (copied.cleared_endings, copied.world_id) == (['solo'], source.world_id)
    assert await count(session, ImportedWorld) == 1
    states_of = select(func.count()).select_from(MessageState).join(Message, Message.id == MessageState.message_id)
    assert await session.scalar(states_of.where(Message.conversation_id == copied_id)) == await session.scalar(
        states_of.where(Message.conversation_id == source_id)
    )
    notes = list(await session.scalars(select(MemoryNote.text).where(MemoryNote.conversation_id == copied_id)))
    assert notes == ['미나는 바다를 좋아한다.']
    summary = (await session.scalars(select(Summary).where(Summary.conversation_id == copied_id))).one()
    assert (summary.text, summary.cost_usd, summary.input_tokens) == ('처음 만났다.', None, None)
    # 청구 기록은 옮기지 않는다(다시 청구하지 않는다)
    assert await count(session, Generation, Generation.conversation_id == copied_id) == 0


async def test_playing_on_in_the_copy_leaves_the_source_alone(
    client: AsyncClient, app: FastAPI, played: dict, mine: dict
):
    copied = (await copy(client, mine, played['id'])).json()

    await say(client, app, mine, copied['id'], '이어서')

    assert len((await detail(client, mine, copied['id']))['messages']) == len(played['messages']) + 2
    assert await detail(client, mine, played['id']) == played


async def test_a_busy_session_is_not_copied(client: AsyncClient, session: AsyncSession, played: dict, mine: dict):
    await session.execute(update(Conversation).values(generating_since=datetime.now(UTC)))
    await session.commit()

    response = await copy(client, mine, played['id'])

    assert (response.status_code, response.json()['code']) == (status.HTTP_409_CONFLICT, 'generation_in_progress')
    assert await count(session, Conversation) == 1


async def test_someone_elses_and_missing_sessions_are_404(
    client: AsyncClient, signing_key: SigningKey, played: dict, mine: dict
):
    theirs = await copy(client, bearer(signing_key, THEM), played['id'])
    missing = await copy(client, mine, str(uuid.uuid4()))

    assert (theirs.status_code, missing.status_code) == (status.HTTP_404_NOT_FOUND, status.HTTP_404_NOT_FOUND)


async def test_a_session_without_messages_is_copied_empty(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict
):
    await turn_on_luna(session)
    started = (
        await client.post(
            CONVERSATIONS_URL, json={'world_id': str(asset.add_world(make_world_with_paths()).id)}, headers=mine
        )
    ).json()

    copied = (await copy(client, mine, started['id'])).json()

    assert (copied['messages'], copied['persona']) == ([], started['persona'])
