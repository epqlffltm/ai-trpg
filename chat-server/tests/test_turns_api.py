# chat-server/tests/test_turns_api.py

"""
말 보내기(app/turns/)를 API 로 검증한다. 실제 DB(chat_test)에서 돈다.
asset 서버, 결제 서버, 모델은 가짜다(tests/assets.py, tests/billing.py, tests/models.py).

보는 것.
  - 한 번의 말: turn, delta 들, done 이 차례로 온다. 사람의 말과 답이 트리에 붙고 가지의 끝이 답이 된다.
    홀드를 걸고 확정한다. 모델에는 카드와 지난 대화와 방금의 말이 간다
  - 응답 전의 거절: 로그인, 남의 대화, 말의 모양, 모델이 없음, 쓸 수 없는 모델, 다른 답을 쓰는 중.
    모자람(402), 골드(402), 팔지 않음(422), 결제 서버나 공급자가 죽음(503)은 사람의 말을 남긴다
  - 응답 뒤의 실패: 글자 없이 실패하면 답이 없고 홀드를 돌려준다.
    도중에 끊기거나 잘리면 받은 만큼 partial 로 두고 청구한다
  - 확정을 못 하면 기록에 남고 나중에 부를 때를 미룬다(정리 작업은 tests/test_charge_settler.py)
사람이 떠나도 끝까지 저장하는 것, 서버가 꺼질 때 멈추는 것, 하트비트는 tests/test_turn_runs.py 가 본다
(httpx 의 ASGI 전송은 응답을 다 모은 뒤에 돌려주어 끊김을 흉내 낼 수 없다).
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from ai_core.provider import ProviderError, Role
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import service as catalog
from app.conversations.models import Conversation, Message
from app.turns.models import Generation
from tests.assets import FakeAsset, make_character, make_persona
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
    """모델을 부르는 자리의 가짜."""
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
    """luna 를 켠다. 표를 비운 뒤에 넣는다."""
    await turn_on_luna(session)


@pytest.fixture
async def conversation(model_on: None, client: AsyncClient, asset: FakeAsset, mine: dict) -> dict:
    """luna 로 시작한 내 대화. 인사말이 첫 말이다."""
    return await start_with_luna(client, asset, mine)


async def send(client: AsyncClient, headers: dict, conversation: dict, content: str = '책을 찾고 있어요.'):
    return await client.post(
        f'{CONVERSATIONS_URL}/{conversation["id"]}/messages', json={'content': content}, headers=headers
    )


async def finished(app: FastAPI) -> None:
    """따로 도는 작업(저장, 확정)이 끝나기를 기다린다."""
    await asyncio.gather(*list(app.state.turns))


async def generation_of(session: AsyncSession) -> Generation:
    session.expire_all()
    return (await session.scalars(select(Generation))).one()


async def conversation_row(session: AsyncSession, conversation: dict) -> Conversation:
    session.expire_all()
    return await session.get(Conversation, uuid.UUID(conversation['id']))


# --- 한 번의 말 ---


async def test_a_message_streams_the_answer_and_saves_both(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    response = await send(client, mine, conversation)
    await finished(app)

    assert response.status_code == status.HTTP_200_OK
    assert response.headers['content-type'].startswith('text/event-stream')
    assert response.headers['x-accel-buffering'] == 'no'
    events = parse_sse(response.text)
    assert [event for event, _ in events] == ['turn', 'delta', 'delta', 'done']
    turn, done = events[0][1], events[-1][1]
    greeting = conversation['messages'][0]
    assert (turn['user_message']['content'], turn['user_message']['parent_id']) == ('책을 찾고 있어요.', greeting['id'])
    assert [data['text'] for event, data in events if event == 'delta'] == ['어서 ', '와요.']
    assert done['message']['content'] == '어서 와요.'
    assert (done['message']['parent_id'], done['message']['status']) == (turn['user_message']['id'], 'complete')
    # 가지의 끝이 답이다. 대화를 읽으면 인사말, 사람의 말, 답이 차례로 나온다
    detail = (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)).json()
    assert [message['content'] for message in detail['messages']] == [
        greeting['content'],
        '책을 찾고 있어요.',
        '어서 와요.',
    ]
    row = await conversation_row(session, conversation)
    assert row.generating_since is None
    # 홀드를 걸고 확정했다. 기록에 토큰과 원가가 남는다
    generation = await generation_of(session)
    assert (generation.billing_status, generation.outcome, generation.price_code) == (
        'captured',
        'complete',
        PRICE_CODE,
    )
    assert (generation.input_tokens, generation.output_tokens, generation.cost_usd) == (1000, 200, Decimal('0.002'))
    assert billing.statuses() == {generation.reference: 'captured'}
    assert billing.balance(ME) == 70


async def test_the_model_gets_the_card_the_history_and_the_new_message(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, billing: FakeBillingServer, mine: dict
):
    await send(client, mine, conversation)
    await finished(app)

    ((messages, params),) = router.provider.calls
    assert [message.role for message in messages] == [Role.SYSTEM, Role.ASSISTANT, Role.USER]
    assert '[캐릭터]\n이름: 세라' in messages[0].content
    assert '[시작 상황]\n문을 두드리는 소리가 난다.' in messages[0].content
    assert messages[1].content == '어서 와요. 찾는 책이 있나요?'
    assert messages[2].content == '책을 찾고 있어요.'
    assert (params.max_tokens, params.temperature) == (1024, 0.9)
    assert router.routed == ['luna']


async def test_the_persona_is_in_the_card(
    model_on: None, client: AsyncClient, app: FastAPI, asset: FakeAsset, router: FakeRouter, mine: dict
):
    persona = asset.add_persona(make_persona(name='한서윤'))
    character = asset.add_character(make_character())
    body = {'character_id': str(character.id), 'model': 'luna', 'persona_id': str(persona.id)}
    made = (await client.post(CONVERSATIONS_URL, json=body, headers=mine)).json()

    await send(client, mine, made)
    await finished(app)

    card = router.provider.calls[0][0][0].content
    assert '[사용자]\n이름: 한서윤' in card


async def test_the_next_message_carries_the_whole_branch(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, billing: FakeBillingServer, mine: dict
):
    await send(client, mine, conversation, '하나')
    await finished(app)
    await send(client, mine, conversation, '둘')
    await finished(app)

    messages, _ = router.provider.calls[-1]
    assert [message.content for message in messages[1:]] == ['어서 와요. 찾는 책이 있나요?', '하나', '어서 와요.', '둘']


async def test_without_a_billing_server_the_message_is_free(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    response = await send(client, mine, conversation)
    await finished(app)

    assert parse_sse(response.text)[-1][0] == 'done'
    assert (await generation_of(session)).billing_status == 'captured'


# --- 응답 전의 거절 ---


async def test_sending_needs_login(client: AsyncClient):
    response = await client.post(f'{CONVERSATIONS_URL}/{uuid.uuid4()}/messages', json={'content': '안녕'})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_someone_elses_conversation_is_404(
    client: AsyncClient, conversation: dict, router: FakeRouter, theirs: dict
):
    response = await send(client, theirs, conversation)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert router.provider.calls == []


@pytest.mark.parametrize('body', [{'content': ''}, {'content': '   '}, {'content': 'x' * 4001}, {'text': '안녕'}])
async def test_a_malformed_message_is_refused(
    client: AsyncClient, conversation: dict, router: FakeRouter, mine: dict, body: dict
):
    response = await client.post(f'{CONVERSATIONS_URL}/{conversation["id"]}/messages', json=body, headers=mine)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_a_conversation_without_a_model_is_409(
    client: AsyncClient, session: AsyncSession, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    character = asset.add_character(make_character())
    made = (await client.post(CONVERSATIONS_URL, json={'character_id': str(character.id)}, headers=mine)).json()

    response = await send(client, mine, made)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['code'] == 'model_required'
    assert (await session.scalars(select(Generation))).all() == []


async def test_a_model_that_was_turned_off_is_422_and_saves_nothing(
    client: AsyncClient, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    await catalog.disable_model(session, 'luna')

    response = await send(client, mine, conversation)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['code'] == 'model_unavailable'
    session.expire_all()
    assert len((await session.scalars(select(Message))).all()) == 1


async def test_a_conversation_already_answering_is_409(
    client: AsyncClient, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    await lock(session, conversation, datetime.now(UTC))

    response = await send(client, mine, conversation)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['code'] == 'generation_in_progress'
    assert router.provider.calls == []


async def test_a_lock_left_by_a_dead_server_is_taken_over(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    await lock(session, conversation, datetime.now(UTC) - timedelta(minutes=16))

    response = await send(client, mine, conversation)
    await finished(app)

    assert parse_sse(response.text)[-1][0] == 'done'


async def lock(session: AsyncSession, conversation: dict, since: datetime) -> None:
    await session.execute(
        update(Conversation).where(Conversation.id == uuid.UUID(conversation['id'])).values(generating_since=since)
    )
    await session.commit()


@pytest.mark.parametrize(
    ('arrange', 'status_code', 'code'),
    [
        (lambda server: server.balances.update({ME: 10}), status.HTTP_402_PAYMENT_REQUIRED, 'credit_short'),
        (lambda server: server.gold_only.add(PRICE_CODE), status.HTTP_402_PAYMENT_REQUIRED, 'gold_required'),
        (
            lambda server: server.not_for_sale.add(PRICE_CODE),
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            'model_unavailable',
        ),
        (lambda server: server.prices.pop(PRICE_CODE), status.HTTP_422_UNPROCESSABLE_CONTENT, 'model_unavailable'),
        (lambda server: setattr(server, 'down', True), status.HTTP_503_SERVICE_UNAVAILABLE, 'billing_unavailable'),
    ],
)
async def test_a_hold_that_does_not_take_keeps_the_message_and_calls_no_model(
    client: AsyncClient,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
    arrange,
    status_code: int,
    code: str,
):
    arrange(billing)

    response = await send(client, mine, conversation)

    body = response.json()
    assert (response.status_code, body['code']) == (status_code, code)
    # 말은 저장하되 생성하지 않는다. 차례를 놓고 기록은 declined 다
    row = await conversation_row(session, conversation)
    assert (str(row.active_leaf_id), row.generating_since) == (body['message_id'], None)
    generation = await generation_of(session)
    assert (generation.billing_status, generation.error_code) == ('declined', code)
    assert router.provider.calls == []
    assert ('Retry-After' in response.headers) is (status_code == status.HTTP_503_SERVICE_UNAVAILABLE)


@pytest.mark.parametrize(
    ('reason', 'status_code', 'code'),
    [
        ('provider_not_configured', status.HTTP_503_SERVICE_UNAVAILABLE, 'provider_unavailable'),
        ('model_unavailable', status.HTTP_422_UNPROCESSABLE_CONTENT, 'model_unavailable'),
    ],
)
async def test_a_model_that_cannot_be_called_is_refused_before_the_hold(
    client: AsyncClient,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
    reason: str,
    status_code: int,
    code: str,
):
    router.refuse = reason

    response = await send(client, mine, conversation)

    assert (response.status_code, response.json()['code']) == (status_code, code)
    assert billing.calls == []
    assert (await generation_of(session)).billing_status == 'declined'


# --- 응답 뒤의 실패 ---


async def test_a_failure_before_any_text_saves_no_answer_and_releases(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    router.provider = ScriptedProvider(pieces=[], error=ProviderError('timeout'))

    response = await send(client, mine, conversation)
    await finished(app)

    events = parse_sse(response.text)
    assert [event for event, _ in events] == ['turn', 'failed']
    assert events[-1][1] == {'code': 'timeout'}
    row = await conversation_row(session, conversation)
    assert (str(row.active_leaf_id), row.generating_since) == (events[0][1]['user_message']['id'], None)
    generation = await generation_of(session)
    assert (generation.billing_status, generation.outcome, generation.message_id) == ('released', 'failed', None)
    assert billing.balance(ME) == 100


@pytest.mark.parametrize(
    'provider',
    [
        ScriptedProvider(pieces=['어서 ', '와'], error=ProviderError('stream_broken')),
        ScriptedProvider(pieces=['어서 ', '와'], truncated=True),
    ],
)
async def test_a_cut_answer_is_saved_as_partial_and_charged(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
    provider: ScriptedProvider,
):
    router.provider = provider

    response = await send(client, mine, conversation)
    await finished(app)

    done = parse_sse(response.text)[-1]
    assert done[0] == 'done'
    assert (done[1]['message']['content'], done[1]['message']['status']) == ('어서 와', 'partial')
    generation = await generation_of(session)
    assert (generation.billing_status, generation.outcome) == ('captured', 'partial')
    assert billing.balance(ME) == 70


async def test_an_empty_answer_is_a_failure(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    router.provider = ScriptedProvider(pieces=[])

    response = await send(client, mine, conversation)
    await finished(app)

    assert parse_sse(response.text)[-1] == ('failed', {'code': 'empty'})
    assert (await generation_of(session)).billing_status == 'released'


async def test_a_capture_that_could_not_be_sent_waits_for_the_settler(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    hold = asyncio.Event()
    router.provider = ScriptedProvider(hold=hold)

    request = asyncio.create_task(send(client, mine, conversation))
    while not router.provider.calls:
        await asyncio.sleep(0.01)
    billing.down = True
    hold.set()
    response = await request
    await finished(app)

    # 답은 저장하고 사람에게 보냈다. 확정은 결제 서버가 받지 못해 나중에 다시 부른다
    assert parse_sse(response.text)[-1][0] == 'done'
    generation = await generation_of(session)
    assert (generation.billing_status, generation.settle_attempts) == ('capture_due', 1)
    assert generation.next_settle_at > datetime.now(UTC)


def test_the_stream_address_is_left_out_of_the_request_spans():
    from app.main import STREAMS

    assert STREAMS.matches(f'{CONVERSATIONS_URL}/{uuid.uuid4()}/messages')
    assert not STREAMS.matches(f'{CONVERSATIONS_URL}/{uuid.uuid4()}')


async def test_a_billing_server_that_refuses_the_capture_marks_it_failed(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    hold = asyncio.Event()
    router.provider = ScriptedProvider(hold=hold)

    request = asyncio.create_task(send(client, mine, conversation))
    while not router.provider.calls:
        await asyncio.sleep(0.01)
    # 정리 작업이 만료된 홀드를 돌려준 뒤라 확정이 409 다
    billing.expire((await generation_of(session)).reference)
    hold.set()
    await request
    await finished(app)

    generation = await generation_of(session)
    assert (generation.billing_status, generation.error_code) == ('failed', 'rejected_409')
