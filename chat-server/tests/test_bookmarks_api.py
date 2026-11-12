# chat-server/tests/test_bookmarks_api.py

"""
말의 책갈피(app/bookmarks/, #982)를 API 로 검증한다. 실제 DB(chat_test)에서 돈다. asset 서버와 모델은 가짜다.

보는 것.
  - 책갈피를 달고, 나중에 단 것부터 보고, 다시 달면 메모만 바뀌고, 뗀다(다시 떼도 204)
  - 목록에 그 말의 역할과 앞부분이 실린다. 메모는 앞뒤 빈칸을 떼고, 비우면 메모가 없다. 긴 메모는 422
  - 다른 가지의 말에도 달 수 있고, 가지 고르기로 그 자리가 보인다
  - 다른 대화의 말은 404 message_not_found, 남의 대화는 404. 가득 차면 409 bookmarks_full(이미 단 말은 된다)
  - 대화를 지우면 책갈피도 지운다. 대화의 행이 지워지면(탈퇴) 함께 지워진다
"""

import asyncio
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bookmarks import service
from app.bookmarks.models import Bookmark
from app.conversations.models import Conversation
from app.main import API_PREFIX
from tests.assets import FakeAsset
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, bearer, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def theirs(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, SOMEONE_ELSE)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter(ScriptedProvider(pieces=['첫 답이에요.\n둘째 줄.']))
    app.state.model_router = fake
    return fake


@pytest.fixture
async def conversation(clean_tables: None, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict):
    await turn_on_luna(session)
    return await start_with_luna(client, asset, mine)


def bookmarks_url(conversation: dict, message_id: str | None = None) -> str:
    base = f'{CONVERSATIONS_URL}/{conversation["id"]}/bookmarks'
    return base if message_id is None else f'{base}/{message_id}'


async def mark(client: AsyncClient, headers: dict, conversation: dict, message_id: str, note: str | None = None):
    body = {} if note is None else {'note': note}
    return await client.put(bookmarks_url(conversation, message_id), json=body, headers=headers)


async def listed(client: AsyncClient, headers: dict, conversation: dict) -> list[dict]:
    return (await client.get(bookmarks_url(conversation), headers=headers)).json()


async def finished(app: FastAPI) -> None:
    await asyncio.gather(*list(app.state.turns))


async def say(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict) -> None:
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    response = await client.post(url, json={'content': '안녕'}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await finished(app)


async def messages(client: AsyncClient, headers: dict, conversation: dict) -> list[dict]:
    return (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)).json()['messages']


async def count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Bookmark)) or 0


@pytest.mark.usefixtures('router')
async def test_bookmarks_are_put_listed_renoted_and_removed(
    client: AsyncClient, app: FastAPI, conversation: dict, mine: dict
):
    await say(client, app, mine, conversation)
    greeting, question, answer = await messages(client, mine, conversation)

    first = await mark(client, mine, conversation, greeting['id'], '  첫인사  ')
    await mark(client, mine, conversation, answer['id'])
    renoted = await mark(client, mine, conversation, greeting['id'], '처음 만난 날')
    items = await listed(client, mine, conversation)

    assert first.status_code == status.HTTP_200_OK
    assert first.json()['note'] == '첫인사'
    assert renoted.json()['note'] == '처음 만난 날'
    # 나중에 단 것부터. 다시 단 것은 늘지 않는다
    assert [(item['message_id'], item['role']) for item in items] == [
        (answer['id'], 'assistant'),
        (greeting['id'], 'assistant'),
    ]
    assert items[0] | {'created_at': None} == {
        'message_id': answer['id'],
        'note': None,
        'role': 'assistant',
        'excerpt': '첫 답이에요. 둘째 줄.',
        'created_at': None,
    }
    removed = await client.delete(bookmarks_url(conversation, answer['id']), headers=mine)
    again = await client.delete(bookmarks_url(conversation, answer['id']), headers=mine)
    assert (removed.status_code, again.status_code) == (status.HTTP_204_NO_CONTENT, status.HTTP_204_NO_CONTENT)
    assert [item['message_id'] for item in await listed(client, mine, conversation)] == [greeting['id']]
    assert question['role'] == 'user'


async def test_notes_are_trimmed_emptied_and_capped(client: AsyncClient, conversation: dict, mine: dict):
    greeting = conversation['messages'][0]['id']

    emptied = await mark(client, mine, conversation, greeting, '   ')
    too_long = await mark(client, mine, conversation, greeting, '가' * 101)

    assert emptied.json()['note'] is None
    assert too_long.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_a_long_excerpt_is_cut():
    assert service.excerpt_of('가' * 200) == '가' * 79 + '…'


async def test_a_bookmark_on_another_branch_is_reached_by_choosing_it(
    client: AsyncClient, app: FastAPI, router: FakeRouter, conversation: dict, mine: dict
):
    await say(client, app, mine, conversation)
    _, _, answer = await messages(client, mine, conversation)
    router.provider = ScriptedProvider(pieces=['다시 쓴 답.'])
    await client.post(f'{API_PREFIX}/messages/{answer["id"]}/regenerate', headers=mine)
    await finished(app)
    assert (await messages(client, mine, conversation))[-1]['content'] == '다시 쓴 답.'

    # 지금 보지 않는 가지의 말에도 단다
    marked = await mark(client, mine, conversation, answer['id'], '좋았던 답')
    chosen = await client.put(
        f'{CONVERSATIONS_URL}/{conversation["id"]}/branch', json={'message_id': answer['id']}, headers=mine
    )

    assert marked.status_code == status.HTTP_200_OK
    assert chosen.status_code == status.HTTP_200_OK, chosen.text
    assert (await messages(client, mine, conversation))[-1]['id'] == answer['id']


async def test_other_conversations_and_other_people_are_404(
    client: AsyncClient, asset: FakeAsset, conversation: dict, mine: dict, theirs: dict
):
    other = await start_with_luna(client, asset, mine)

    foreign = await mark(client, mine, conversation, other['messages'][0]['id'])
    missing = await mark(client, mine, conversation, str(uuid.uuid4()))
    not_mine = await mark(client, theirs, conversation, conversation['messages'][0]['id'])
    not_mine_list = await client.get(bookmarks_url(conversation), headers=theirs)

    assert (foreign.status_code, foreign.json()['code']) == (status.HTTP_404_NOT_FOUND, 'message_not_found')
    assert missing.status_code == status.HTTP_404_NOT_FOUND
    assert (not_mine.status_code, not_mine_list.status_code) == (status.HTTP_404_NOT_FOUND, status.HTTP_404_NOT_FOUND)


@pytest.mark.usefixtures('router')
async def test_a_full_conversation_refuses_new_bookmarks_but_renotes(
    client: AsyncClient, app: FastAPI, conversation: dict, mine: dict, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(service, 'BOOKMARKS_PER_CONVERSATION', 2)
    await say(client, app, mine, conversation)
    greeting, question, answer = await messages(client, mine, conversation)
    await mark(client, mine, conversation, greeting['id'])
    await mark(client, mine, conversation, question['id'])

    full = await mark(client, mine, conversation, answer['id'])
    renoted = await mark(client, mine, conversation, greeting['id'], '그래도 메모는 바꾼다')

    assert (full.status_code, full.json()['code']) == (status.HTTP_409_CONFLICT, 'bookmarks_full')
    assert renoted.status_code == status.HTTP_200_OK


async def test_deleting_the_conversation_removes_its_bookmarks(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, conversation: dict, mine: dict
):
    other = await start_with_luna(client, asset, mine)
    await mark(client, mine, conversation, conversation['messages'][0]['id'])
    await mark(client, mine, other, other['messages'][0]['id'])

    response = await client.delete(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await count(session) == 1
    # 대화의 행이 지워지면(탈퇴) 함께 지워진다
    await session.execute(delete(Conversation).where(Conversation.id == uuid.UUID(other['id'])))
    await session.commit()
    assert await count(session) == 0
