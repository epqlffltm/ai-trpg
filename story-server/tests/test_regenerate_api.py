# story-server/tests/test_regenerate_api.py

"""
다시 생성(POST /messages/{id}/regenerate)과 멈추기(POST /generations/{id}/stop)를 API 로 검증한다.
실제 DB(story_test)에서 돈다. asset 서버, 결제 서버, 모델은 가짜다(tests/assets.py, tests/billing.py, tests/models.py).

보는 것.
  - 답을 다시 쓰면 같은 말 아래에 대안이 생기고, 가지는 새 답으로 옮겨 가고, 다시 청구한다
  - 행동의 답을 다시 쓰면 그 행동에 적힌 이벤트의 장면을 다시 세운다. 이벤트를 다시 열지 않고 상태도 새로 붙지 않는다
  - 답을 못 받은 말에 다시 쓰면 그 말에 답한다
  - 끝난 세션에서도 엔딩의 장면을 다시 쓸 수 있다. 엔딩의 기록은 하나다
  - 다시 쓰다 실패하면 앞의 답이 그대로 보인다
  - 없는 말, 남의 말은 404, 답을 쓰는 중이면 409. 부모가 없는 답은 다시 쓰지 않는다
  - 도는 답을 멈추면 받은 만큼 저장하고 청구한다. 멈출 것이 없거나 남의 것이면 404 다
"""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from ai_core.provider import ProviderError
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, Message, MessageState, MessageStatus, Role
from app.main import API_PREFIX, STREAMS
from app.records.models import EndingRecord
from app.turns.service import NotRegenerableError, answered_message
from app.turns.stops import StopSwitch
from tests.assets import FakeAsset
from tests.billing import FakeBillingServer
from tests.engine_worlds import condition, confession, ending, event, member
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, ME, PRICE_CODE, bearer, parse_sse, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

MESSAGES_URL = f'{API_PREFIX}/messages'
GENERATIONS_URL = f'{API_PREFIX}/generations'
PATHS = [{'a': 'home', 'b': 'beach', 'minutes': 30}]
# 해변에 가면 열리는 이벤트. 집에 사는 미나를 부르고 선택지 하나를 기다린다
SHELL = event(
    'shell',
    condition('reach_place', 'beach'),
    cast=['mina'],
    choices=[{'id': 'leave', 'text': '그냥 둔다', 'effects': []}],
)
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
    """가짜 결제 서버. 나는 크레딧 100 이 있고, luna 의 말 한 번은 30 이다."""
    server = FakeBillingServer(balances={ME: 100})
    server.prices[PRICE_CODE] = 30
    app.state.billing = server.billing(server.make_client())
    return server


@pytest.fixture
async def model_on(clean_tables: None, session: AsyncSession) -> None:
    await turn_on_luna(session)


async def finished(app: FastAPI) -> None:
    await asyncio.gather(*list(app.state.turns))


async def send(client: AsyncClient, headers: dict, conversation: dict, content: str = '안녕'):
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    return await client.post(url, json={'content': content}, headers=headers)


async def act(client: AsyncClient, headers: dict, conversation: dict, body: dict):
    return await client.post(f'{CONVERSATIONS_URL}/{conversation["id"]}/actions', json=body, headers=headers)


async def regenerate(client: AsyncClient, headers: dict, message_id: str):
    return await client.post(f'{MESSAGES_URL}/{message_id}/regenerate', headers=headers)


async def answered(app: FastAPI, response) -> dict:
    """SSE 를 다 받은 뒤의 done 의 말."""
    assert response.status_code == status.HTTP_200_OK, response.text
    await finished(app)
    events = parse_sse(response.text)
    assert events[-1][0] == 'done', events
    return events[-1][1]['message']


async def detail(client: AsyncClient, headers: dict, conversation: dict) -> dict:
    return (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)).json()


# --- 다시 생성 ---


async def test_regenerating_an_answer_adds_a_sibling_and_charges_again(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    conversation = await start_with_luna(client, asset, mine)
    first = await answered(app, await send(client, mine, conversation))
    router.provider.pieces = ['@mina: 다시 왔구나.']

    response = await regenerate(client, mine, first['id'])

    second = await answered(app, response)
    turn = parse_sse(response.text)[0][1]
    # 같은 사람의 말에 답한다. 사람의 말은 새로 저장하지 않는다
    assert turn['user_message']['id'] == first['parent_id'] == second['parent_id']
    assert second['segments'] == [{'speaker': 'mina', 'text': '다시 왔구나.'}]
    assert (await session.scalar(select(func.count()).select_from(Message).where(Message.role == Role.USER))) == 1
    # 모델에는 그 말까지만 간다(앞의 답은 가지 밖이다)
    messages, _ = router.provider.calls[1]
    assert messages[-1].content == '안녕'
    # 가지는 새 답으로 옮겨 갔다. 다시 청구했다
    read = await detail(client, mine, conversation)
    assert [message['id'] for message in read['messages']] == [first['parent_id'], second['id']]
    assert billing.balance(ME) == 40


async def test_regenerating_an_action_restages_its_event_without_opening_it_again(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    conversation = await start_with_luna(client, asset, mine, {'paths': PATHS, 'events': [SHELL]})
    first = await answered(app, await act(client, mine, conversation, {'kind': 'move', 'place': 'beach'}))

    response = await regenerate(client, mine, first['id'])

    await answered(app, response)
    turn = parse_sse(response.text)[0][1]
    assert (turn['user_message']['role'], turn['user_message']['event_id']) == ('action', 'shell')
    # 그 이벤트의 장면 지시와 부른 인물이 다시 든다. 상태는 행동 뒤의 것 그대로다
    assert turn['cast'] == ['mina', 'jun']
    assert (turn['state']['place'], turn['state']['choosing']) == ('beach', 'shell')
    assert '[장면 지시]\nshell 의 장면.' in router.provider.calls[1][0][0].content
    assert router.provider.calls[1][0][-1].content == '[행동] 해변(으)로 갔다. 지금은 1일째 아침.'
    # 엔진은 다시 판정하지 않았다. 행동 말도 상태도 하나다
    assert (await session.scalar(select(func.count()).select_from(MessageState))) == 1
    assert (await session.scalar(select(func.count()).select_from(Message).where(Message.role == Role.ACTION))) == 1


async def test_a_message_left_without_an_answer_gets_one(
    client: AsyncClient,
    app: FastAPI,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    conversation = await start_with_luna(client, asset, mine)
    billing.balances[ME] = 10
    declined = await send(client, mine, conversation)
    assert declined.status_code == status.HTTP_402_PAYMENT_REQUIRED
    message_id = declined.json()['message_id']
    billing.balances[ME] = 100

    answer = await answered(app, await regenerate(client, mine, message_id))

    assert answer['parent_id'] == message_id
    read = await detail(client, mine, conversation)
    assert [message['id'] for message in read['messages']] == [message_id, answer['id']]


async def test_the_ending_scene_can_be_regenerated_after_the_session_ended(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    mina = {**member('mina', home='home', start=80, confession=confession('연인')), 'character': {'name': '미나'}}
    fields = {'cast': [mina], 'endings': [ending('with_mina', 'confess_success', 'mina')]}
    conversation = await start_with_luna(client, asset, mine, fields)
    first = await answered(app, await act(client, mine, conversation, {'kind': 'confess', 'cast': 'mina'}))

    response = await regenerate(client, mine, first['id'])

    await answered(app, response)
    assert parse_sse(response.text)[0][1]['state']['ending'] == 'with_mina'
    assert '엔딩 「with_mina」에 닿았다.' in router.provider.calls[1][0][0].content
    # 엔딩은 다시 보지 않는다. 기록은 하나다
    assert (await session.scalar(select(func.count()).select_from(EndingRecord))) == 1


async def test_a_failed_regeneration_keeps_the_previous_answer(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    conversation = await start_with_luna(client, asset, mine)
    first = await answered(app, await send(client, mine, conversation))
    router.provider.pieces = []
    router.provider.error = ProviderError('timeout')

    response = await regenerate(client, mine, first['id'])

    await finished(app)
    assert parse_sse(response.text)[-1] == ('failed', {'code': 'timeout'})
    read = await detail(client, mine, conversation)
    assert read['messages'][-1]['id'] == first['id']
    # 답이 없으니 돌려줬다
    assert billing.balance(ME) == 70


async def test_regenerating_a_message_that_is_not_mine_is_404(
    client: AsyncClient,
    app: FastAPI,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
    signing_key: SigningKey,
):
    conversation = await start_with_luna(client, asset, mine)
    first = await answered(app, await send(client, mine, conversation))

    theirs = await regenerate(client, bearer(signing_key, OTHER), first['id'])
    unknown = await regenerate(client, mine, str(uuid.uuid4()))

    assert (theirs.status_code, theirs.json()['code']) == (status.HTTP_404_NOT_FOUND, 'message_not_found')
    assert (unknown.status_code, unknown.json()['code']) == (status.HTTP_404_NOT_FOUND, 'message_not_found')
    assert len(router.provider.calls) == 1


async def test_regenerating_while_answering_is_409(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    conversation = await start_with_luna(client, asset, mine)
    first = await answered(app, await send(client, mine, conversation))
    await session.execute(update(Conversation).values(generating_since=datetime.now(UTC)))
    await session.commit()

    response = await regenerate(client, mine, first['id'])

    assert (response.status_code, response.json()['code']) == (status.HTTP_409_CONFLICT, 'generation_in_progress')


def test_an_answer_without_a_parent_cannot_be_regenerated():
    opening = Message(id=uuid.uuid4(), parent_id=None, role=Role.ASSISTANT, status=MessageStatus.COMPLETE)

    with pytest.raises(NotRegenerableError):
        answered_message(opening)


def test_regenerating_is_a_stream():
    assert STREAMS.matches(f'{MESSAGES_URL}/{uuid.uuid4()}/regenerate')
    assert not STREAMS.matches(f'{GENERATIONS_URL}/{uuid.uuid4()}/stop')


# --- 멈추기 ---


async def test_stopping_a_running_answer_saves_what_it_got(
    client: AsyncClient,
    app: FastAPI,
    model_on: None,
    asset: FakeAsset,
    billing: FakeBillingServer,
    mine: dict,
):
    app.state.model_router = FakeRouter(ScriptedProvider(pieces=['@mina: 어서', ' 와'], hold=asyncio.Event()))
    conversation = await start_with_luna(client, asset, mine)
    sending = asyncio.create_task(send(client, mine, conversation))
    while not app.state.stops:
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)
    generation_id = next(iter(app.state.stops))

    stopped = await client.post(f'{GENERATIONS_URL}/{generation_id}/stop', headers=mine)

    assert stopped.status_code == status.HTTP_204_NO_CONTENT
    answer = await answered(app, await sending)
    assert (answer['status'], answer['segments']) == ('partial', [{'speaker': 'mina', 'text': '어서 와'}])
    # 받은 만큼 청구했다. 끝난 생성은 스위치를 놓는다
    assert billing.balance(ME) == 70
    assert app.state.stops == {}


async def test_stopping_nothing_is_404(client: AsyncClient, mine: dict):
    response = await client.post(f'{GENERATIONS_URL}/{uuid.uuid4()}/stop', headers=mine)

    assert (response.status_code, response.json()['code']) == (status.HTTP_404_NOT_FOUND, 'generation_not_running')


async def test_stopping_someone_elses_answer_is_404(client: AsyncClient, app: FastAPI, mine: dict):
    generation_id = uuid.uuid4()
    switch = StopSwitch()
    app.state.stops[generation_id] = (OTHER, switch)

    response = await client.post(f'{GENERATIONS_URL}/{generation_id}/stop', headers=mine)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert switch.requested is False


async def test_stop_needs_login(client: AsyncClient):
    response = await client.post(f'{GENERATIONS_URL}/{uuid.uuid4()}/stop')

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
