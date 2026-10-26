# story-server/tests/test_edit_of_api.py

"""
내 말 고치기(POST /conversations/{id}/messages 의 edit_of)를 API 로 검증한다. 실제 DB(story_test)에서 돈다.
asset 서버, 결제 서버, 모델은 가짜다(tests/assets.py, tests/billing.py, tests/models.py).

보는 것.
  - 고친 말은 원본의 대안(같은 부모 아래)이 되고 원본은 남는다. 가지는 새 말과 그 답으로 옮겨 가고 청구한다
  - 상태와 모델에 보낼 말들은 고칠 말의 앞까지의 가지의 것이다(그 뒤의 행동은 들지 않는다)
  - 끝난 세션이어도 엔딩 앞의 말은 고칠 수 있다(그 가지는 엔딩 전이다)
  - 답과 행동 말은 422 not_editable, 다른 세션의 말이나 없는 말은 404 다. 아무것도 저장하지 않는다
"""

import asyncio
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Message
from tests.assets import FakeAsset
from tests.billing import FakeBillingServer
from tests.engine_worlds import confession, ending, member
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, ME, PRICE_CODE, bearer, parse_sse, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

PATHS = [{'a': 'home', 'b': 'beach', 'minutes': 30}]


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter()
    app.state.model_router = fake
    return fake


@pytest.fixture
def billing(app: FastAPI) -> FakeBillingServer:
    """가짜 결제 서버. 나는 크레딧 1000 이 있고, luna 의 말 한 번은 30 이다."""
    server = FakeBillingServer(balances={ME: 1000})
    server.prices[PRICE_CODE] = 30
    app.state.billing = server.billing(server.make_client())
    return server


@pytest.fixture
async def model_on(clean_tables: None, session: AsyncSession, router: FakeRouter, billing: FakeBillingServer) -> None:
    await turn_on_luna(session)


async def streamed(app: FastAPI, response) -> list:
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))
    return parse_sse(response.text)


async def say(client: AsyncClient, headers: dict, conversation: dict, content: str, edit_of: str | None = None):
    body = {'content': content} | ({'edit_of': edit_of} if edit_of else {})
    return await client.post(f'{CONVERSATIONS_URL}/{conversation["id"]}/messages', json=body, headers=headers)


async def act(client: AsyncClient, headers: dict, conversation: dict, body: dict):
    return await client.post(f'{CONVERSATIONS_URL}/{conversation["id"]}/actions', json=body, headers=headers)


async def detail(client: AsyncClient, headers: dict, conversation: dict) -> dict:
    return (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)).json()


async def test_an_edited_message_is_a_new_branch_beside_the_original(
    client: AsyncClient,
    app: FastAPI,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    conversation = await start_with_luna(client, asset, mine, {'paths': PATHS})
    first = (await streamed(app, await say(client, mine, conversation, '안녕')))[0][1]['user_message']
    await streamed(app, await act(client, mine, conversation, {'kind': 'move', 'place': 'beach'}))

    events = await streamed(app, await say(client, mine, conversation, '반가워', edit_of=first['id']))

    turn = events[0][1]
    edited = turn['user_message']
    assert (edited['parent_id'], edited['content']) == (None, '반가워')
    # 앞의 가지의 상태다. 해변으로 간 것은 고친 말 뒤의 일이라 들지 않는다
    assert (turn['state']['place'], turn['cast']) == ('home', ['mina'])
    messages, _ = router.provider.calls[-1]
    assert [message.content for message in messages[1:]] == ['반가워']
    read = await detail(client, mine, conversation)
    assert read['messages'][0]['alternatives'] == [first['id'], edited['id']]
    assert read['messages'][-1]['id'] == events[-1][1]['message']['id']
    # 말 세 번을 청구했다
    assert billing.balance(ME) == 910


async def test_a_message_before_the_ending_can_be_edited_after_the_session_ended(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, mine: dict
):
    mina = {**member('mina', home='home', start=80, confession=confession('연인')), 'character': {'name': '미나'}}
    fields = {'cast': [mina], 'endings': [ending('with_mina', 'confess_success', 'mina')]}
    conversation = await start_with_luna(client, asset, mine, fields)
    first = (await streamed(app, await say(client, mine, conversation, '안녕')))[0][1]['user_message']
    await streamed(app, await act(client, mine, conversation, {'kind': 'confess', 'cast': 'mina'}))
    assert (await say(client, mine, conversation, '그리고')).json()['code'] == 'session_ended'

    events = await streamed(app, await say(client, mine, conversation, '다시', edit_of=first['id']))

    assert events[0][1]['state']['ending'] is None


async def test_answers_and_actions_are_not_editable_and_nothing_is_saved(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    model_on: None,
    asset: FakeAsset,
    mine: dict,
):
    conversation = await start_with_luna(client, asset, mine, {'paths': PATHS})
    answer = (await streamed(app, await say(client, mine, conversation, '안녕')))[-1][1]['message']
    moved = (await streamed(app, await act(client, mine, conversation, {'kind': 'move', 'place': 'beach'})))[0][1]
    before = await session.scalar(select(func.count()).select_from(Message))

    for message_id in (answer['id'], moved['user_message']['id']):
        response = await say(client, mine, conversation, '고친 말', edit_of=message_id)
        assert (response.status_code, response.json()['code']) == (
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            'not_editable',
        )

    assert await session.scalar(select(func.count()).select_from(Message)) == before


async def test_a_message_of_another_session_is_404(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, mine: dict
):
    conversation = await start_with_luna(client, asset, mine)
    other = await start_with_luna(client, asset, mine)
    theirs = (await streamed(app, await say(client, mine, other, '안녕')))[0][1]['user_message']

    elsewhere = await say(client, mine, conversation, '고친 말', edit_of=theirs['id'])
    unknown = await say(client, mine, conversation, '고친 말', edit_of=str(uuid.uuid4()))

    assert (elsewhere.status_code, elsewhere.json()['code']) == (status.HTTP_404_NOT_FOUND, 'message_not_found')
    assert unknown.status_code == status.HTTP_404_NOT_FOUND
