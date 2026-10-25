# chat-server/tests/test_edit_api.py

"""
고치기를 API 로 검증한다. 실제 DB(chat_test)에서 돈다. asset 서버, 결제 서버, 모델은 가짜다.

보는 것.
  - 내 말 고치기(말 보내기의 edit_of): 고칠 말의 부모 아래에 새 말을 붙이고 답을 받는다. 원본과 그 답은 남는다.
    첫 말(부모가 없다)도 고친다. 캐릭터의 말이면 422, 다른 대화의 말이면 404. 새로 청구한다
  - 상대의 말 고치기(PATCH /messages/{id}): 그 자리에서 고치고 고친 표시를 단다. 선택지는 지운다. 청구하지 않는다.
    다음 호출에 고친 글이 간다. 사람의 말이면 422, 남의 말이면 404, 답을 쓰는 중이면 409. 수정 시각은 그대로다
  - 가지의 끝은 차례를 잡은 뒤에 다시 읽는다. 그사이 바꾼 가지에 붙는다
"""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from ai_core.provider import Role
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation
from app.main import API_PREFIX
from app.turns import repository
from app.turns.models import Generation
from tests.assets import FakeAsset, make_character
from tests.billing import FakeBillingServer
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, ME, PRICE_CODE, bearer, parse_sse, start_with_luna, turn_on_luna

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
    fake = FakeRouter(ScriptedProvider(pieces=['어서 와요.\n<suggestions>\n가']))
    app.state.model_router = fake
    return fake


@pytest.fixture
def billing(app: FastAPI) -> FakeBillingServer:
    server = FakeBillingServer(balances={ME: 100})
    server.prices[PRICE_CODE] = 30
    app.state.billing = server.billing(server.make_client())
    return server


@pytest.fixture
async def conversation(clean_tables: None, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict):
    await turn_on_luna(session)
    return await start_with_luna(client, asset, mine)


async def finished(app: FastAPI) -> None:
    await asyncio.gather(*list(app.state.turns))


async def say(
    client: AsyncClient,
    app: FastAPI,
    headers: dict,
    conversation: dict,
    content: str = '책을 찾아요.',
    edit_of: str | None = None,
):
    body = {'content': content} if edit_of is None else {'content': content, 'edit_of': edit_of}
    response = await client.post(f'{CONVERSATIONS_URL}/{conversation["id"]}/messages', json=body, headers=headers)
    await finished(app)
    return response


async def patch(client: AsyncClient, headers: dict, message_id: str, body: dict):
    return await client.patch(f'{API_PREFIX}/messages/{message_id}', json=body, headers=headers)


async def read(client: AsyncClient, headers: dict, conversation: dict) -> dict:
    return (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)).json()


def contents(detail: dict) -> list[str]:
    return [message['content'] for message in detail['messages']]


async def generations(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Generation))


# --- 내 말 고치기 ---


async def test_editing_my_message_starts_a_new_branch_and_keeps_the_old_one(
    client: AsyncClient,
    app: FastAPI,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    first = parse_sse((await say(client, app, mine, conversation)).text)
    original = first[0][1]['user_message']
    router.provider = ScriptedProvider(pieces=['그 책은 여기 있어요.'])

    response = await say(client, app, mine, conversation, '시집을 찾아요.', edit_of=original['id'])

    assert response.status_code == status.HTTP_200_OK
    events = parse_sse(response.text)
    edited = events[0][1]['user_message']
    assert (edited['parent_id'], edited['content']) == (original['parent_id'], '시집을 찾아요.')
    detail = await read(client, mine, conversation)
    assert contents(detail)[1:] == ['시집을 찾아요.', '그 책은 여기 있어요.']
    assert detail['messages'][1]['alternatives'] == [original['id'], edited['id']]
    # 원본의 가지로 돌아가면 원본과 그 답이 그대로다
    back = await client.put(
        f'{CONVERSATIONS_URL}/{conversation["id"]}/branch', json={'message_id': original['id']}, headers=mine
    )
    assert contents(back.json())[1:] == ['책을 찾아요.', '어서 와요.']
    # 고친 말에 답을 받았으니 새로 청구했다
    assert billing.balance(ME) == 40


async def test_the_model_gets_the_edited_branch_only(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    first = parse_sse((await say(client, app, mine, conversation)).text)

    await say(client, app, mine, conversation, '시집을 찾아요.', edit_of=first[0][1]['user_message']['id'])

    sent = router.provider.calls[1][0]
    assert [message.content for message in sent if message.role == Role.USER] == ['시집을 찾아요.']


async def test_the_first_message_without_a_greeting_can_be_edited(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router: FakeRouter, mine: dict
):
    await turn_on_luna(session)
    character = asset.add_character(make_character(greeting=''))
    body = {'character_id': str(character.id), 'model': 'luna'}
    conversation = (await client.post(CONVERSATIONS_URL, json=body, headers=mine)).json()
    first = parse_sse((await say(client, app, mine, conversation)).text)[0][1]['user_message']

    edited = parse_sse((await say(client, app, mine, conversation, '다시', edit_of=first['id'])).text)[0][1]

    assert edited['user_message']['parent_id'] is None
    detail = await read(client, mine, conversation)
    assert detail['messages'][0]['alternatives'] == [first['id'], edited['user_message']['id']]


async def test_a_characters_message_cannot_be_edited_as_mine(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    answer = parse_sse((await say(client, app, mine, conversation)).text)[-1][1]['message']
    count = await generations(session)

    response = await say(client, app, mine, conversation, '고친 말', edit_of=answer['id'])

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['code'] == 'not_editable'
    assert await generations(session) == count
    session.expire_all()
    row = await session.get(Conversation, uuid.UUID(conversation['id']))
    assert (str(row.active_leaf_id), row.generating_since) == (answer['id'], None)


async def test_a_message_of_another_conversation_is_404(
    client: AsyncClient, app: FastAPI, asset: FakeAsset, conversation: dict, router: FakeRouter, mine: dict
):
    other = await start_with_luna(client, asset, mine)
    theirs_first = parse_sse((await say(client, app, mine, other)).text)[0][1]['user_message']

    response = await say(client, app, mine, conversation, '고친 말', edit_of=theirs_first['id'])

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()['code'] == 'message_not_found'


async def test_a_branch_changed_before_the_lock_is_where_the_message_goes(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    mine: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    greeting = conversation['messages'][0]['id']
    await say(client, app, mine, conversation)
    original = repository.lock_turn

    async def moved_first(locking: AsyncSession, conversation_id, now, stale):
        # 대화를 읽은 뒤 차례를 잡기 전에 다른 요청이 가지를 인사말로 바꿨다
        await session.execute(
            update(Conversation).where(Conversation.id == conversation_id).values(active_leaf_id=uuid.UUID(greeting))
        )
        await session.commit()
        return await original(locking, conversation_id, now, stale)

    monkeypatch.setattr(repository, 'lock_turn', moved_first)

    turn = parse_sse((await say(client, app, mine, conversation, '다른 말')).text)[0][1]

    assert turn['user_message']['parent_id'] == greeting


# --- 상대의 말 고치기 ---


async def test_editing_the_characters_message_changes_it_in_place(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    answer = parse_sse((await say(client, app, mine, conversation)).text)[-1][1]['message']
    assert answer['suggestions'] == ['가']
    before = (await session.get(Conversation, uuid.UUID(conversation['id']))).updated_at
    count = await generations(session)

    response = await patch(client, mine, answer['id'], {'content': '반가워요.'})

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert (body['id'], body['content'], body['edited'], body['suggestions']) == (answer['id'], '반가워요.', True, [])
    detail = await read(client, mine, conversation)
    assert (detail['messages'][-1]['content'], detail['messages'][-1]['edited']) == ('반가워요.', True)
    assert detail['messages'][1]['edited'] is False
    # 호출이 아니라 청구하지 않는다. 대화의 차례도 그대로다
    assert (await generations(session), billing.balance(ME)) == (count, 70)
    session.expire_all()
    assert (await session.get(Conversation, uuid.UUID(conversation['id']))).updated_at == before


async def test_the_next_call_gets_the_edited_text(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    answer = parse_sse((await say(client, app, mine, conversation)).text)[-1][1]['message']
    await patch(client, mine, answer['id'], {'content': '반가워요.'})

    await say(client, app, mine, conversation, '네')

    sent = router.provider.calls[1][0]
    assert [message.content for message in sent if message.role == Role.ASSISTANT][-1] == '반가워요.'


async def test_the_greeting_can_be_edited(client: AsyncClient, conversation: dict, mine: dict):
    response = await patch(client, mine, conversation['messages'][0]['id'], {'content': '안녕하세요.'})

    assert (response.status_code, response.json()['content']) == (status.HTTP_200_OK, '안녕하세요.')


async def test_my_message_cannot_be_edited_in_place(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    mine_first = parse_sse((await say(client, app, mine, conversation)).text)[0][1]['user_message']

    response = await patch(client, mine, mine_first['id'], {'content': '고친 말'})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['code'] == 'not_editable'


@pytest.mark.parametrize('who', ['theirs', 'nobody'])
async def test_someone_elses_or_a_missing_message_is_404(
    client: AsyncClient, conversation: dict, mine: dict, theirs: dict, who: str
):
    headers, message_id = (theirs, conversation['messages'][0]['id']) if who == 'theirs' else (mine, str(uuid.uuid4()))

    response = await patch(client, headers, message_id, {'content': '고친 말'})

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()['code'] == 'message_not_found'


async def test_editing_while_answering_is_409(
    client: AsyncClient, session: AsyncSession, conversation: dict, mine: dict
):
    greeting = conversation['messages'][0]
    await session.execute(
        update(Conversation)
        .where(Conversation.id == uuid.UUID(conversation['id']))
        .values(generating_since=datetime.now(UTC))
    )
    await session.commit()

    response = await patch(client, mine, greeting['id'], {'content': '고친 말'})

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['code'] == 'generation_in_progress'
    assert (await read(client, mine, conversation))['messages'][0]['content'] == greeting['content']


@pytest.mark.parametrize(
    'body', [{'content': ''}, {'content': '  \n'}, {'content': 'x' * 20001}, {'content': 'a', 'x': 1}]
)
async def test_a_malformed_edit_is_refused(client: AsyncClient, conversation: dict, mine: dict, body: dict):
    response = await patch(client, mine, conversation['messages'][0]['id'], body)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    # 칸이 틀린 요청은 서버들이 함께 쓰는 본문이다(server_core/input_errors.py)
    assert set(response.json()) == {'detail', 'errors'}
