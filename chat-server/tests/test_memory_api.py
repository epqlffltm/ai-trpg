# chat-server/tests/test_memory_api.py

"""
기억 메모(app/memory/)를 API 로 검증한다. 실제 DB(chat_test)에서 돈다. asset 서버와 모델은 가짜다.

보는 것.
  - 더하고, 보고, 고치고, 지운다. 먼저 쓴 것부터 보인다. 사용자가 쓴 것(source user)이다
  - 모델의 카드에 "[기억]" 으로 간다(시작 상황 뒤). 지운 것과 요약의 제안은 가지 않는다. 메모가 없으면 블록이 없다
  - 남의 대화는 404, 다른 대화의 메모는 404 note_not_found, 스물을 넘으면 409 notes_full(동시에 더해도 넘지 않는다)
  - 글의 모양(빈 글, 300자 넘음, 모르는 칸)은 422. 앞뒤 빈칸은 뗀다
  - 답을 쓰는 중에도 고칠 수 있다. 대화를 지우면(행) 함께 지워진다
"""

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation
from app.memory import repository
from app.memory.models import NOTES_PER_CONVERSATION, MemoryNote
from app.memory.service import render_memory
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
    fake = FakeRouter(ScriptedProvider(pieces=['응.']))
    app.state.model_router = fake
    return fake


@pytest.fixture
async def conversation(clean_tables: None, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict):
    await turn_on_luna(session)
    return await start_with_luna(client, asset, mine)


def notes_url(conversation: dict, note_id: str | None = None) -> str:
    base = f'{CONVERSATIONS_URL}/{conversation["id"]}/notes'
    return base if note_id is None else f'{base}/{note_id}'


async def add(client: AsyncClient, headers: dict, conversation: dict, text: str):
    return await client.post(notes_url(conversation), json={'text': text}, headers=headers)


async def say(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict) -> None:
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    await client.post(url, json={'content': '안녕'}, headers=headers)
    await asyncio.gather(*list(app.state.turns))


async def test_notes_are_added_listed_edited_and_deleted(client: AsyncClient, conversation: dict, mine: dict):
    first = (await add(client, mine, conversation, '  고양이를 좋아한다.  ')).json()
    second = (await add(client, mine, conversation, '생일은 3월이다.')).json()

    edited = await client.patch(notes_url(conversation, first['id']), json={'text': '강아지를 좋아한다.'}, headers=mine)
    deleted = await client.delete(notes_url(conversation, second['id']), headers=mine)
    listed = (await client.get(notes_url(conversation), headers=mine)).json()

    assert (first['text'], first['source']) == ('고양이를 좋아한다.', 'user')
    assert edited.json()['text'] == '강아지를 좋아한다.'
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    assert [note['text'] for note in listed] == ['강아지를 좋아한다.']


async def test_notes_are_listed_oldest_first(client: AsyncClient, conversation: dict, mine: dict):
    for text in ['하나', '둘', '셋']:
        await add(client, mine, conversation, text)

    listed = (await client.get(notes_url(conversation), headers=mine)).json()

    assert [note['text'] for note in listed] == ['하나', '둘', '셋']


async def test_the_model_reads_the_notes(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    kept = (await add(client, mine, conversation, '고양이를 좋아한다.')).json()
    gone = (await add(client, mine, conversation, '틀린 기억')).json()
    await client.delete(notes_url(conversation, gone['id']), headers=mine)

    await say(client, app, mine, conversation)

    card = router.provider.calls[0][0][0].content
    assert '[기억]\n- 고양이를 좋아한다.' in card
    assert '틀린 기억' not in card
    assert card.index('[시작 상황]') < card.index('[기억]')
    assert kept['id']


async def test_without_notes_there_is_no_memory_block(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    await say(client, app, mine, conversation)

    assert '[기억]' not in router.provider.calls[0][0][0].content


async def test_someone_elses_conversation_is_404(client: AsyncClient, conversation: dict, mine: dict, theirs: dict):
    note = (await add(client, mine, conversation, '비밀')).json()

    listed = await client.get(notes_url(conversation), headers=theirs)
    edited = await client.patch(notes_url(conversation, note['id']), json={'text': '바꿈'}, headers=theirs)

    assert (listed.status_code, edited.status_code) == (status.HTTP_404_NOT_FOUND, status.HTTP_404_NOT_FOUND)


async def test_a_note_of_another_conversation_is_404(
    client: AsyncClient, asset: FakeAsset, conversation: dict, mine: dict
):
    other = await start_with_luna(client, asset, mine)
    note = (await add(client, mine, other, '다른 대화')).json()

    response = await client.delete(notes_url(conversation, note['id']), headers=mine)

    assert (response.status_code, response.json()['code']) == (status.HTTP_404_NOT_FOUND, 'note_not_found')


async def test_a_full_memory_refuses_more(client: AsyncClient, conversation: dict, mine: dict):
    for index in range(NOTES_PER_CONVERSATION):
        assert (await add(client, mine, conversation, f'메모 {index}')).status_code == status.HTTP_201_CREATED

    response = await add(client, mine, conversation, '하나 더')

    assert (response.status_code, response.json()['code']) == (status.HTTP_409_CONFLICT, 'notes_full')


async def test_adding_at_the_same_time_keeps_the_limit(
    client: AsyncClient,
    session: AsyncSession,
    conversation: dict,
    mine: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    for index in range(NOTES_PER_CONVERSATION - 1):
        await add(client, mine, conversation, f'메모 {index}')
    original = repository.count_notes
    counted = []
    everyone = asyncio.Event()

    async def count_then_wait(*args):
        # 넷이 모두 센 뒤에(또는 잠깐 뒤에) 더한다. 잠그지 않으면 넷이 같은 수를 보고 모두 더한다
        found = await original(*args)
        counted.append(found)
        if len(counted) == 4:
            everyone.set()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(everyone.wait(), timeout=0.3)
        return found

    monkeypatch.setattr(repository, 'count_notes', count_then_wait)

    answers = await asyncio.gather(*(add(client, mine, conversation, f'동시 {index}') for index in range(4)))

    created = [answer.status_code for answer in answers].count(status.HTTP_201_CREATED)
    count = await session.scalar(select(func.count()).select_from(MemoryNote))
    assert (created, count) == (1, NOTES_PER_CONVERSATION)


async def test_notes_suggested_by_a_summary_are_not_sent_yet(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    session.add(MemoryNote(conversation_id=uuid.UUID(conversation['id']), text='요약의 제안', source='summary'))
    await session.commit()

    await say(client, app, mine, conversation)

    assert '요약의 제안' not in router.provider.calls[0][0][0].content


@pytest.mark.parametrize(
    'body', [{'text': ''}, {'text': '   '}, {'text': 'x' * 301}, {'text': '좋다', 'source': 'summary'}]
)
async def test_a_malformed_note_is_refused(client: AsyncClient, conversation: dict, mine: dict, body: dict):
    response = await client.post(notes_url(conversation), json=body, headers=mine)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_notes_can_be_edited_while_answering(
    client: AsyncClient, session: AsyncSession, conversation: dict, mine: dict
):
    await session.execute(
        update(Conversation)
        .where(Conversation.id == uuid.UUID(conversation['id']))
        .values(generating_since=datetime.now(UTC))
    )
    await session.commit()

    response = await add(client, mine, conversation, '쓰는 중에도')

    assert response.status_code == status.HTTP_201_CREATED


async def test_notes_go_with_the_conversation(
    client: AsyncClient, session: AsyncSession, conversation: dict, mine: dict
):
    await add(client, mine, conversation, '사라질 것')

    await session.execute(delete(Conversation).where(Conversation.id == uuid.UUID(conversation['id'])))
    await session.commit()

    assert await session.scalar(select(func.count()).select_from(MemoryNote)) == 0


def test_the_memory_block_lists_the_notes():
    assert render_memory(['가', '나']) == '[기억]\n- 가\n- 나'
    assert render_memory([]) is None
