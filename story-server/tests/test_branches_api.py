# story-server/tests/test_branches_api.py

"""
대안과 가지 고르기(GET /conversations/{id} 의 alternatives, PUT /conversations/{id}/branch)를 API 로 검증한다.
실제 DB(story_test)에서 돈다. asset 서버, 결제 서버, 모델은 가짜다(tests/assets.py, tests/billing.py, tests/models.py).

보는 것.
  - 다시 쓴 답은 같은 부모 아래의 대안으로 읽힌다(먼저 생긴 것부터). 대안이 없는 말은 그 말 하나다
  - 앞의 대안을 고르면 그 아래에서 가장 나중에 생긴 말이 끝이 되고, 상태도 그 가지의 것이 된다
  - 가지를 바꿔도 세션의 수정 시각(목록의 차례)은 그대로다
  - 다른 세션의 말, 없는 말은 404, 답을 쓰는 중이면 409, 남의 세션은 404 다
"""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation
from app.main import API_PREFIX
from tests.assets import FakeAsset
from tests.billing import FakeBillingServer
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, ME, PRICE_CODE, bearer, parse_sse, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

MESSAGES_URL = f'{API_PREFIX}/messages'
PATHS = [{'a': 'home', 'b': 'beach', 'minutes': 30}]
OTHER = uuid.UUID('99999999-2222-4333-8444-555555555555')


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
    """가짜 결제 서버. 나는 크레딧이 넉넉하고, luna 의 말 한 번은 30 이다."""
    server = FakeBillingServer(balances={ME: 1000})
    server.prices[PRICE_CODE] = 30
    app.state.billing = server.billing(server.make_client())
    return server


@pytest.fixture
async def conversation(
    clean_tables: None,
    session: AsyncSession,
    client: AsyncClient,
    asset: FakeAsset,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
) -> dict:
    """집과 해변이 길로 이어진 세계관의 내 세션."""
    await turn_on_luna(session)
    return await start_with_luna(client, asset, mine, {'paths': PATHS})


async def answered(app: FastAPI, response) -> dict:
    """SSE 를 다 받은 뒤의 done 의 말."""
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))
    events = parse_sse(response.text)
    assert events[-1][0] == 'done', events
    return events[-1][1]['message']


async def send(app: FastAPI, client: AsyncClient, headers: dict, conversation: dict) -> dict:
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    return await answered(app, await client.post(url, json={'content': '안녕'}, headers=headers))


async def move(app: FastAPI, client: AsyncClient, headers: dict, conversation: dict) -> dict:
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/actions'
    return await answered(app, await client.post(url, json={'kind': 'move', 'place': 'beach'}, headers=headers))


async def regenerate(app: FastAPI, client: AsyncClient, headers: dict, message_id: str) -> dict:
    return await answered(app, await client.post(f'{MESSAGES_URL}/{message_id}/regenerate', headers=headers))


async def detail(client: AsyncClient, headers: dict, conversation: dict) -> dict:
    return (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)).json()


async def choose(client: AsyncClient, headers: dict, conversation: dict, message_id: str):
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/branch'
    return await client.put(url, json={'message_id': message_id}, headers=headers)


async def test_a_regenerated_answer_is_read_as_an_alternative(
    client: AsyncClient, app: FastAPI, conversation: dict, mine: dict
):
    first = await send(app, client, mine, conversation)
    second = await regenerate(app, client, mine, first['id'])

    messages = (await detail(client, mine, conversation))['messages']

    assert [message['alternatives'] for message in messages] == [[first['parent_id']], [first['id'], second['id']]]


async def test_choosing_an_earlier_branch_brings_back_its_end_and_its_state(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, mine: dict
):
    first = await send(app, client, mine, conversation)
    moved = await move(app, client, mine, conversation)
    # 첫 답을 다시 썼다. 해변으로 간 가지는 대안 밑으로 숨는다
    await regenerate(app, client, mine, first['id'])
    assert (await detail(client, mine, conversation))['state']['place'] == 'home'
    before = await session.scalar(select(Conversation.updated_at))

    response = await choose(client, mine, conversation, first['id'])

    assert response.status_code == status.HTTP_200_OK, response.text
    read = response.json()
    # 그 아래에서 가장 나중에 생긴 말(이동의 답)이 끝이고, 상태도 그 가지의 것(해변)이다
    assert read['messages'][-1]['id'] == moved['id']
    assert read['state']['place'] == 'beach'
    session.expire_all()
    assert await session.scalar(select(Conversation.updated_at)) == before


async def test_a_message_of_another_session_is_404(
    client: AsyncClient, app: FastAPI, asset: FakeAsset, conversation: dict, mine: dict
):
    other = await start_with_luna(client, asset, mine)
    theirs = await send(app, client, mine, other)

    elsewhere = await choose(client, mine, conversation, theirs['id'])
    unknown = await choose(client, mine, conversation, str(uuid.uuid4()))

    assert (elsewhere.status_code, elsewhere.json()['code']) == (status.HTTP_404_NOT_FOUND, 'message_not_found')
    assert unknown.status_code == status.HTTP_404_NOT_FOUND


async def test_someone_elses_session_is_404(
    client: AsyncClient, app: FastAPI, conversation: dict, mine: dict, signing_key: SigningKey
):
    first = await send(app, client, mine, conversation)

    response = await choose(client, bearer(signing_key, OTHER), conversation, first['id'])

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_choosing_while_answering_is_409(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, mine: dict
):
    first = await send(app, client, mine, conversation)
    await session.execute(update(Conversation).values(generating_since=datetime.now(UTC)))
    await session.commit()

    response = await choose(client, mine, conversation, first['id'])

    assert (response.status_code, response.json()['code']) == (status.HTTP_409_CONFLICT, 'generation_in_progress')


async def test_a_malformed_choice_is_an_input_error(client: AsyncClient, conversation: dict, mine: dict):
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/branch'

    response = await client.put(url, json={'message_id': 'x', 'extra': 1}, headers=mine)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
