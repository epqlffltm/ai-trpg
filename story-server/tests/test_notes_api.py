# story-server/tests/test_notes_api.py

"""
기억 메모(app/memory/)를 API 로 검증한다. 실제 DB(story_test)에서 돈다.
asset 서버, 모델은 가짜다(tests/assets.py, tests/models.py).

보는 것.
  - 더하기, 읽기(먼저 쓴 것부터), 고치기, 지우기. 앞뒤 빈칸은 걷고 빈 글과 긴 글은 422 다
  - 메모는 다음 말의 카드에 "[기억]" 으로 간다(사용자 뒤, 지금 앞). 메모가 없으면 블록이 없다
  - 가득 차면 409 notes_full, 그 세션에 없는 메모는 404 note_not_found, 남의 세션은 404 다
  - 세션을 지우면 메모도 지워진다
"""

import asyncio
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation
from app.memory.models import NOTE_MAX_CHARS, NOTES_PER_CONVERSATION, MemoryNote
from tests.assets import FakeAsset
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, bearer, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter()
    app.state.model_router = fake
    return fake


@pytest.fixture
async def conversation(clean_tables: None, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict):
    await turn_on_luna(session)
    return await start_with_luna(client, asset, mine)


def notes_url(conversation: dict) -> str:
    return f'{CONVERSATIONS_URL}/{conversation["id"]}/notes'


async def add(client: AsyncClient, headers: dict, conversation: dict, text: str):
    return await client.post(notes_url(conversation), json={'text': text}, headers=headers)


async def card_after_a_message(
    app: FastAPI, client: AsyncClient, router: FakeRouter, headers: dict, conversation: dict
):
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    response = await client.post(url, json={'content': '안녕'}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))
    return router.provider.calls[-1][0][0].content


async def test_notes_are_added_listed_edited_and_deleted(client: AsyncClient, conversation: dict, mine: dict):
    first = await add(client, mine, conversation, '  미나는 바다를 좋아한다.  ')
    second = await add(client, mine, conversation, '나는 전학생이다.')

    assert first.status_code == status.HTTP_201_CREATED, first.text
    assert first.json()['text'] == '미나는 바다를 좋아한다.'
    edited = await client.patch(
        f'{notes_url(conversation)}/{first.json()["id"]}', json={'text': '미나는 산을 좋아한다.'}, headers=mine
    )
    assert edited.json()['text'] == '미나는 산을 좋아한다.'
    deleted = await client.delete(f'{notes_url(conversation)}/{second.json()["id"]}', headers=mine)
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    listed = (await client.get(notes_url(conversation), headers=mine)).json()
    assert [note['text'] for note in listed] == ['미나는 산을 좋아한다.']


@pytest.mark.parametrize('text', ['   ', 'x' * (NOTE_MAX_CHARS + 1)])
async def test_empty_and_long_notes_are_refused(client: AsyncClient, conversation: dict, mine: dict, text: str):
    assert (await add(client, mine, conversation, text)).status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_notes_go_to_the_next_card(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    assert '[기억]' not in await card_after_a_message(app, client, router, mine, conversation)
    await add(client, mine, conversation, '미나는 바다를 좋아한다.')
    await add(client, mine, conversation, '어제 축제에 갔다.')

    card = await card_after_a_message(app, client, router, mine, conversation)

    assert '[기억]\n- 미나는 바다를 좋아한다.\n- 어제 축제에 갔다.' in card
    assert card.index('[세계관]') < card.index('[기억]') < card.index('[지금]')


async def test_a_full_session_takes_no_more_notes(
    client: AsyncClient, session: AsyncSession, conversation: dict, mine: dict
):
    conversation_id = uuid.UUID(conversation['id'])
    session.add_all(MemoryNote(conversation_id=conversation_id, text=f'{n}') for n in range(NOTES_PER_CONVERSATION))
    await session.commit()

    response = await add(client, mine, conversation, '하나 더')

    assert (response.status_code, response.json()['code']) == (status.HTTP_409_CONFLICT, 'notes_full')


async def test_notes_of_other_sessions_and_people_are_not_found(
    client: AsyncClient, asset: FakeAsset, signing_key: SigningKey, conversation: dict, mine: dict
):
    other = await start_with_luna(client, asset, mine)
    note = (await add(client, mine, other, '다른 세션의 메모')).json()
    theirs = bearer(signing_key, SOMEONE_ELSE)

    response = await client.patch(f'{notes_url(conversation)}/{note["id"]}', json={'text': '고침'}, headers=mine)

    assert (response.status_code, response.json()['code']) == (status.HTTP_404_NOT_FOUND, 'note_not_found')
    assert (await client.get(notes_url(other), headers=theirs)).status_code == status.HTTP_404_NOT_FOUND
    assert (await add(client, theirs, other, '남의 것')).status_code == status.HTTP_404_NOT_FOUND


async def test_notes_go_with_the_session(client: AsyncClient, session: AsyncSession, conversation: dict, mine: dict):
    await add(client, mine, conversation, '사라질 메모')

    await session.execute(delete(Conversation))
    await session.commit()

    assert await session.scalar(select(func.count()).select_from(MemoryNote)) == 0
