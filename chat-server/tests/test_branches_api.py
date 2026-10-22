# chat-server/tests/test_branches_api.py

"""
다시 생성, 멈추기, 대안 오가기를 API 로 검증한다. 실제 DB(chat_test)에서 돈다.
asset 서버, 결제 서버, 모델은 가짜다(tests/assets.py, tests/billing.py, tests/models.py).

보는 것.
  - 다시 생성: 캐릭터의 답이면 같은 사람의 말 아래에 새 대안을 쓴다. 앞의 답은 남는다.
    답을 못 받은 사람의 말이면 그 말에 답을 쓴다. 새로 청구한다. 모델에는 처음과 같은 대화가 간다.
    인사말은 422, 남의 말은 404, 답을 쓰는 중이면 409. 거절되면 앞의 답이 그대로 보인다
  - 멈추기: 받은 만큼 partial 로 저장하고 확정한다. 남의 것, 없는 것, 끝난 것은 404
  - 대안: 대화를 읽으면 말마다 대안들의 id 가 실린다. 다른 대안을 고르면 그 아래의 가장 나중 말이 끝이 된다.
    수정 시각은 그대로다. 남의 대화의 말은 404, 답을 쓰는 중이면 409
  - generating: 차례를 쥐고 있으면 참이다. 오래된 차례(서버가 꺼졌다)는 아니다
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from ai_core.provider import ProviderError
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation
from app.main import API_PREFIX, STREAMS
from app.turns.models import Generation
from tests.assets import FakeAsset
from tests.billing import FakeBillingServer
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, ME, PRICE_CODE, bearer, parse_sse, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')
QUESTION = '책을 찾고 있어요.'


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def theirs(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, SOMEONE_ELSE)


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
async def conversation(clean_tables: None, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict):
    """luna 로 시작한 내 대화. 인사말이 첫 말이다."""
    await turn_on_luna(session)
    return await start_with_luna(client, asset, mine)


async def finished(app: FastAPI) -> None:
    """따로 도는 작업(저장, 확정)이 끝나기를 기다린다."""
    await asyncio.gather(*list(app.state.turns))


async def say(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict, content: str = QUESTION) -> list:
    """말을 보내고 끝까지 기다린다. SSE 의 (event, data) 들."""
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    response = await client.post(url, json={'content': content}, headers=headers)
    await finished(app)
    assert response.status_code == status.HTTP_200_OK, response.text
    return parse_sse(response.text)


async def regenerate(client: AsyncClient, headers: dict, message_id: str):
    return await client.post(f'{API_PREFIX}/messages/{message_id}/regenerate', headers=headers)


async def choose(client: AsyncClient, headers: dict, conversation: dict, message_id: str):
    body = {'message_id': message_id}
    return await client.put(f'{CONVERSATIONS_URL}/{conversation["id"]}/branch', json=body, headers=headers)


async def read(client: AsyncClient, headers: dict, conversation: dict) -> dict:
    response = await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def conversation_row(session: AsyncSession, conversation: dict) -> Conversation:
    session.expire_all()
    return await session.get(Conversation, uuid.UUID(conversation['id']))


async def lock(session: AsyncSession, conversation: dict, since: datetime) -> None:
    await session.execute(
        update(Conversation).where(Conversation.id == uuid.UUID(conversation['id'])).values(generating_since=since)
    )
    await session.commit()


def contents(detail: dict) -> list[str]:
    return [message['content'] for message in detail['messages']]


# --- 다시 생성 ---


async def test_regenerating_an_answer_adds_a_sibling_and_charges_again(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    first = await say(client, app, mine, conversation)
    question, answer = first[0][1]['user_message'], first[-1][1]['message']
    router.provider = ScriptedProvider(pieces=['다시 ', '와요.'])

    response = await regenerate(client, mine, answer['id'])
    await finished(app)

    assert response.status_code == status.HTTP_200_OK
    events = parse_sse(response.text)
    assert [event for event, _ in events] == ['turn', 'delta', 'delta', 'done']
    # 사람의 말은 새로 저장하지 않았다. 새 답은 같은 사람의 말 아래에 있다
    assert events[0][1]['user_message']['id'] == question['id']
    again = events[-1][1]['message']
    assert (again['parent_id'], again['content']) == (question['id'], '다시 와요.')
    detail = await read(client, mine, conversation)
    assert contents(detail)[-1] == '다시 와요.'
    assert detail['messages'][-1]['alternatives'] == [answer['id'], again['id']]
    # 새 호출이라 새로 청구했다
    assert billing.balance(ME) == 40
    assert len(billing.statuses()) == 2


async def test_the_model_gets_the_same_conversation_again(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    first = await say(client, app, mine, conversation)
    provider = router.provider

    await regenerate(client, mine, first[-1][1]['message']['id'])
    await finished(app)

    # 앞의 답은 보내지 않는다. 마지막이 사람의 말이다
    assert provider.calls[1][0] == provider.calls[0][0]


async def test_a_message_left_without_an_answer_gets_one(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    router.provider = ScriptedProvider(pieces=[], error=ProviderError('timeout'))
    failed = await say(client, app, mine, conversation)
    question = failed[0][1]['user_message']
    router.provider = ScriptedProvider()

    response = await regenerate(client, mine, question['id'])
    await finished(app)

    done = parse_sse(response.text)[-1][1]['message']
    assert done['parent_id'] == question['id']
    assert contents(await read(client, mine, conversation))[-2:] == [QUESTION, '어서 와요.']


async def test_the_greeting_cannot_be_regenerated(
    client: AsyncClient, conversation: dict, router: FakeRouter, mine: dict
):
    response = await regenerate(client, mine, conversation['messages'][0]['id'])

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['code'] == 'not_regenerable'
    assert router.provider.calls == []


@pytest.mark.parametrize('who', ['theirs', 'nobody'])
async def test_someone_elses_or_a_missing_message_is_404(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict, theirs: dict, who: str
):
    answer = (await say(client, app, mine, conversation))[-1][1]['message']
    headers, message_id = (theirs, answer['id']) if who == 'theirs' else (mine, str(uuid.uuid4()))
    calls = len(router.provider.calls)

    response = await regenerate(client, headers, message_id)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()['code'] == 'message_not_found'
    assert len(router.provider.calls) == calls


async def test_regenerating_while_answering_is_409(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    answer = (await say(client, app, mine, conversation))[-1][1]['message']
    await lock(session, conversation, datetime.now(UTC))

    response = await regenerate(client, mine, answer['id'])

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['code'] == 'generation_in_progress'


async def test_a_refused_regeneration_keeps_the_old_answer_in_view(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    answer = (await say(client, app, mine, conversation))[-1][1]['message']
    billing.balances[ME] = 10

    response = await regenerate(client, mine, answer['id'])

    assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
    assert response.json()['code'] == 'credit_short'
    row = await conversation_row(session, conversation)
    assert (str(row.active_leaf_id), row.generating_since) == (answer['id'], None)


async def test_a_regeneration_failing_before_any_text_keeps_the_old_answer_in_view(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    answer = (await say(client, app, mine, conversation))[-1][1]['message']
    router.provider = ScriptedProvider(pieces=[], error=ProviderError('timeout'))

    response = await regenerate(client, mine, answer['id'])
    await finished(app)

    assert parse_sse(response.text)[-1] == ('failed', {'code': 'timeout'})
    row = await conversation_row(session, conversation)
    assert str(row.active_leaf_id) == answer['id']


def test_the_regenerate_address_is_left_out_of_the_request_spans():
    assert STREAMS.matches(f'{API_PREFIX}/messages/{uuid.uuid4()}/regenerate')
    # 멈추기는 보통의 요청이다
    assert not STREAMS.matches(f'{API_PREFIX}/generations/{uuid.uuid4()}/stop')


# --- 멈추기 ---


async def stop(client: AsyncClient, headers: dict, generation_id: str):
    return await client.post(f'{API_PREFIX}/generations/{generation_id}/stop', headers=headers)


async def running_generation(session: AsyncSession, provider: ScriptedProvider) -> str:
    """모델을 부르는 중인 기록의 id. 조각을 다 흘릴 때까지 기다린다."""
    while not provider.calls:
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.01)
    session.expire_all()
    return str((await session.scalars(select(Generation.id))).one())


async def test_stopping_keeps_what_was_written_and_charges_it(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    router.provider = ScriptedProvider(pieces=['어서 ', '와'], hold=asyncio.Event())
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    sending = asyncio.create_task(client.post(url, json={'content': QUESTION}, headers=mine))
    generation_id = await running_generation(session, router.provider)

    response = await stop(client, mine, generation_id)
    streamed = await sending
    await finished(app)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    done = parse_sse(streamed.text)[-1]
    assert done[0] == 'done'
    assert (done[1]['message']['content'], done[1]['message']['status']) == ('어서 와', 'partial')
    session.expire_all()
    generation = await session.get(Generation, uuid.UUID(generation_id))
    assert (generation.billing_status, generation.error_code) == ('captured', 'stopped')
    assert billing.balance(ME) == 70
    # 다 끝난 것은 멈출 것이 없다. 스위치도 놓았다
    assert (await stop(client, mine, generation_id)).status_code == status.HTTP_404_NOT_FOUND
    assert app.state.stops == {}


async def test_someone_else_cannot_stop_my_answer(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    mine: dict,
    theirs: dict,
):
    hold = asyncio.Event()
    router.provider = ScriptedProvider(pieces=['어서 '], hold=hold)
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    sending = asyncio.create_task(client.post(url, json={'content': QUESTION}, headers=mine))
    generation_id = await running_generation(session, router.provider)

    response = await stop(client, theirs, generation_id)
    hold.set()
    streamed = await sending
    await finished(app)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()['code'] == 'generation_not_running'
    assert parse_sse(streamed.text)[-1][1]['message']['status'] == 'complete'


async def test_stopping_nothing_is_404(client: AsyncClient, mine: dict):
    response = await stop(client, mine, str(uuid.uuid4()))

    assert response.status_code == status.HTTP_404_NOT_FOUND


# --- 대안 ---


async def two_answers(client: AsyncClient, app: FastAPI, router: FakeRouter, mine: dict, conversation: dict):
    """한 사람의 말에 답 둘(first, second). 가지의 끝은 second 다."""
    first = (await say(client, app, mine, conversation))[-1][1]['message']
    router.provider = ScriptedProvider(pieces=['둘째'])
    response = await regenerate(client, mine, first['id'])
    await finished(app)
    return first, parse_sse(response.text)[-1][1]['message']


async def test_each_message_carries_its_alternatives(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    first, second = await two_answers(client, app, router, mine, conversation)

    detail = await read(client, mine, conversation)

    greeting, question, answer = detail['messages']
    assert greeting['alternatives'] == [greeting['id']]
    assert question['alternatives'] == [question['id']]
    assert answer['alternatives'] == [first['id'], second['id']]
    assert detail['generating'] is False


async def test_choosing_an_alternative_shows_its_branch_without_touching_the_time(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    mine: dict,
):
    first, _ = await two_answers(client, app, router, mine, conversation)
    before = (await conversation_row(session, conversation)).updated_at

    response = await choose(client, mine, conversation, first['id'])

    assert response.status_code == status.HTTP_200_OK
    assert contents(response.json())[-1] == '어서 와요.'
    assert (await conversation_row(session, conversation)).updated_at == before


async def test_the_branch_ends_at_the_latest_message_under_the_choice(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    first, second = await two_answers(client, app, router, mine, conversation)
    await choose(client, mine, conversation, first['id'])
    router.provider = ScriptedProvider(pieces=['더 깊이'])
    await say(client, app, mine, conversation, '그 아래로')
    await choose(client, mine, conversation, second['id'])

    detail = (await choose(client, mine, conversation, first['id'])).json()

    # 첫째 답 아래로 이어 간 말까지 다시 보인다
    assert contents(detail)[-3:] == ['어서 와요.', '그 아래로', '더 깊이']


async def test_a_message_of_another_conversation_is_404(
    client: AsyncClient, app: FastAPI, asset: FakeAsset, conversation: dict, router: FakeRouter, mine: dict
):
    other = await start_with_luna(client, asset, mine)

    response = await choose(client, mine, conversation, other['messages'][0]['id'])

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()['code'] == 'message_not_found'


async def test_someone_elses_conversation_cannot_be_turned(client: AsyncClient, conversation: dict, theirs: dict):
    response = await choose(client, theirs, conversation, conversation['messages'][0]['id'])

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_choosing_while_answering_is_409(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    mine: dict,
):
    first, second = await two_answers(client, app, router, mine, conversation)
    await lock(session, conversation, datetime.now(UTC))

    response = await choose(client, mine, conversation, first['id'])

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['code'] == 'generation_in_progress'
    assert str((await conversation_row(session, conversation)).active_leaf_id) == second['id']


@pytest.mark.parametrize(('minutes', 'generating'), [(1, True), (16, False)])
async def test_generating_follows_the_turn_lock(
    client: AsyncClient, session: AsyncSession, conversation: dict, mine: dict, minutes: int, generating: bool
):
    await lock(session, conversation, datetime.now(UTC) - timedelta(minutes=minutes))

    assert (await read(client, mine, conversation))['generating'] is generating
