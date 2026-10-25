# story-server/tests/test_turns_api.py

"""
말 보내기(app/turns/)를 API 로 검증한다. 실제 DB(story_test)에서 돈다.
asset 서버, 결제 서버, 모델은 가짜다(tests/assets.py, tests/billing.py, tests/models.py).

보는 것.
  - 한 번의 말: turn, segment 와 delta 들, done 이 차례로 온다. 사람의 말과 답(말 조각, 그때의 장면의 인물)이
    트리에 붙고 가지의 끝이 답이 된다. 홀드를 걸고 확정한다
  - 모델에 가는 것: 카드(장면의 인물만, 쓰는 법), 지난 말(답은 표식이 붙은 줄), 방금의 말
  - 장면에 없는 인물의 줄은 흘리지 않고 저장하지 않으며 센다. 모두 버려지면 실패한 말이고 청구하지 않는다
  - 기다리는 이벤트가 있으면 그 장면 지시가 카드에 들어가고 그 장면이 부른 인물이 장면에 들어온다
  - 응답 전의 거절: 로그인, 남의 세션, 말의 모양, 모델이 없음, 쓸 수 없는 모델, 다른 답을 쓰는 중, 끝난 세션.
    모자람(402), 팔지 않음(422), 결제 서버나 공급자가 죽음(503)은 사람의 말을 남긴다
  - 응답 뒤의 실패: 글자 없이 실패하면 답이 없고 홀드를 돌려준다.
    도중에 끊기거나 잘리면 받은 만큼 partial 로 두고 청구한다
  - 확정을 못 하면 기록에 남고 나중에 부를 때를 미룬다(정리 작업은 tests/test_charge_settler.py)
서버가 꺼질 때 멈추는 것과 저장하지 못하는 것은 tests/test_turn_runs.py 가 본다.
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
from app.conversations.models import Conversation, Message, MessageState
from app.engine.state import StoryState
from app.main import STREAMS
from app.turns.models import Generation
from app.turns.states import state_to_json
from tests.assets import FakeAsset
from tests.billing import FakeBillingServer
from tests.engine_worlds import clock, event
from tests.models import FakeRouter
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
    """luna 로 시작한 내 세션. 집에서 아침이고 미나가 장면에 있다."""
    return await start_with_luna(client, asset, mine)


async def send(client: AsyncClient, headers: dict, conversation: dict, content: str = '안녕, 미나.'):
    return await client.post(
        f'{CONVERSATIONS_URL}/{conversation["id"]}/messages', json={'content': content}, headers=headers
    )


async def finished(app: FastAPI) -> None:
    """따로 도는 작업(저장, 확정)이 끝나기를 기다린다."""
    await asyncio.gather(*list(app.state.turns))


async def generation_of(session: AsyncSession) -> Generation:
    session.expire_all()
    return (await session.scalars(select(Generation))).one()


async def detail(client: AsyncClient, headers: dict, conversation: dict) -> dict:
    return (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)).json()


async def put_state(session: AsyncSession, conversation: dict, state: StoryState) -> None:
    """지금 가지의 끝에 상태가 붙은 행동 말을 하나 둔다(행동을 더하는 조각이 하는 일을 흉내 낸다)."""
    conversation_id = uuid.UUID(conversation['id'])
    message = Message(
        id=uuid.uuid4(), conversation_id=conversation_id, role='action', content='행동', status='complete'
    )
    session.add(message)
    await session.flush()
    session.add(MessageState(message_id=message.id, state=state_to_json(state)))
    await session.execute(
        update(Conversation).where(Conversation.id == conversation_id).values(active_leaf_id=message.id)
    )
    await session.commit()


# --- 한 번의 말 ---


async def test_a_message_streams_segments_and_saves_both(
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
    assert [event for event, _ in events] == ['turn', 'segment', 'delta', 'delta', 'segment', 'delta', 'done']
    turn, done = events[0][1], events[-1][1]
    assert (turn['user_message']['content'], turn['user_message']['parent_id'], turn['cast']) == (
        '안녕, 미나.',
        None,
        ['mina'],
    )
    assert [data for event, data in events[1:-1]] == [
        {'speaker': None},
        {'text': '바람이 '},
        {'text': '분다.'},
        {'speaker': 'mina'},
        {'text': '왔구나.'},
    ]
    answer = done['message']
    assert answer['segments'] == [{'speaker': None, 'text': '바람이 분다.'}, {'speaker': 'mina', 'text': '왔구나.'}]
    assert (answer['content'], answer['cast'], answer['status'], answer['role']) == (
        '@narration: 바람이 분다.\n@mina: 왔구나.',
        ['mina'],
        'complete',
        'assistant',
    )
    # 가지의 끝이 답이다. 세션을 읽으면 사람의 말과 답이 차례로 나온다
    read = await detail(client, mine, conversation)
    assert [(message['role'], message['segments']) for message in read['messages']] == [
        ('user', []),
        ('assistant', answer['segments']),
    ]
    session.expire_all()
    row = await session.get(Conversation, uuid.UUID(conversation['id']))
    assert (row.active_leaf_id, row.generating_since) == (uuid.UUID(answer['id']), None)
    # 홀드를 걸고 확정했다. 기록에 토큰과 원가가 남는다
    generation = await generation_of(session)
    assert (generation.billing_status, generation.outcome, generation.price_code, generation.dropped_segments) == (
        'captured',
        'complete',
        PRICE_CODE,
        0,
    )
    assert (generation.input_tokens, generation.output_tokens, generation.cost_usd) == (1000, 200, Decimal('0.002'))
    assert billing.statuses() == {generation.reference: 'captured'}
    assert billing.balance(ME) == 70


async def test_the_model_gets_the_scene_the_history_and_the_new_message(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, billing: FakeBillingServer, mine: dict
):
    await send(client, mine, conversation, '하나')
    await finished(app)
    await send(client, mine, conversation, '둘')
    await finished(app)

    messages, params = router.provider.calls[-1]
    card = messages[0].content
    assert '[지금]\n날: 1일째\n시간대: 아침\n장소: 집' in card
    # 해변에 사는 준은 장면에 없다. 카드에도 없다
    assert '@mina (미나)' in card
    assert 'jun' not in card
    assert [message.role for message in messages] == [Role.SYSTEM, Role.USER, Role.ASSISTANT, Role.USER]
    assert [message.content for message in messages[1:]] == ['하나', '@narration: 바람이 분다.\n@mina: 왔구나.', '둘']
    assert (params.max_tokens, params.temperature) == (1024, 0.9)
    assert router.routed == ['luna', 'luna']


async def test_without_a_billing_server_the_message_is_free(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    response = await send(client, mine, conversation)
    await finished(app)

    assert parse_sse(response.text)[-1][0] == 'done'
    assert (await generation_of(session)).billing_status == 'captured'


async def test_a_speaker_outside_the_scene_is_dropped(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    router.provider.pieces = ['@jun: 나도 왔어.\n', '@미나: 준은 해변에 있잖아.\n엉뚱한 줄']

    response = await send(client, mine, conversation)
    await finished(app)

    events = parse_sse(response.text)
    assert '나도 왔어' not in response.text
    done = events[-1][1]['message']
    assert done['segments'] == [
        {'speaker': 'mina', 'text': '준은 해변에 있잖아.'},
        {'speaker': None, 'text': '엉뚱한 줄'},
    ]
    assert (await generation_of(session)).dropped_segments == 1


async def test_an_answer_only_from_outside_the_scene_is_a_failure(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    router.provider.pieces = ['@jun: 아무도 없나?\n@sora: 여기.']

    response = await send(client, mine, conversation)
    await finished(app)

    assert parse_sse(response.text)[-1] == ('failed', {'code': 'empty'})
    generation = await generation_of(session)
    assert (generation.billing_status, generation.outcome, generation.message_id, generation.dropped_segments) == (
        'released',
        'failed',
        None,
        2,
    )
    assert billing.balance(ME) == 100


async def test_talking_while_a_choice_waits_drops_the_choice(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    mine: dict,
):
    storm = event('storm', cast=['jun'], choices=[{'id': 'stay', 'text': '머문다', 'effects': []}])
    storm['scene']['text'] = '갑자기 소나기가 쏟아진다.'
    conversation = await start_with_luna(client, asset, mine, {'events': [storm]})
    await put_state(session, conversation, StoryState(minutes=clock(1, 8), place='home', choosing='storm'))
    # 기다리는 동안 세션을 읽으면 그 이벤트가 부른 인물도 장면에 있다(이벤트가 집에 사는 인물보다 앞선다)
    waiting = await detail(client, mine, conversation)
    assert (waiting['state']['choosing'], waiting['state']['cast']) == ('storm', ['jun', 'mina'])

    response = await send(client, mine, conversation)
    await finished(app)

    # 고르지 않고 말을 이으면 선택지는 사라진다(효과 없이). 답에는 장면 지시가 없고 그 장소의 인물만 있다
    turn = parse_sse(response.text)[0][1]
    assert (turn['cast'], turn['state']['choosing']) == (['mina'], None)
    card = router.provider.calls[0][0][0].content
    assert '[장면 지시]' not in card
    assert 'jun' not in card
    # 행동 말은 [행동] 을 붙여 보낸다
    assert router.provider.calls[0][0][1].content == '[행동] 행동'
    assert (await detail(client, mine, conversation))['state']['choosing'] is None


# --- 응답 전의 거절 ---


async def test_sending_needs_login(client: AsyncClient):
    response = await client.post(f'{CONVERSATIONS_URL}/{uuid.uuid4()}/messages', json={'content': '안녕'})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_someone_elses_session_is_404(client: AsyncClient, conversation: dict, router: FakeRouter, theirs: dict):
    response = await send(client, theirs, conversation)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert router.routed == []


@pytest.mark.parametrize('content', ['', '   ', 'a' * 4001])
async def test_a_malformed_message_is_refused(client: AsyncClient, conversation: dict, mine: dict, content: str):
    response = await send(client, mine, conversation, content)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_a_session_without_a_model_is_409(
    client: AsyncClient, session: AsyncSession, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start_with_luna(client, asset, mine)
    await session.execute(update(Conversation).values(model_slug=None))
    await session.commit()

    response = await send(client, mine, conversation)

    assert (response.status_code, response.json()['code']) == (status.HTTP_409_CONFLICT, 'model_required')
    assert (await session.scalars(select(Message))).all() == []


async def test_a_model_that_was_turned_off_is_422_and_saves_nothing(
    client: AsyncClient, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    await catalog.disable_model(session, 'luna')

    response = await send(client, mine, conversation)

    assert (response.status_code, response.json()['code']) == (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        'model_unavailable',
    )
    assert (await session.scalars(select(Message))).all() == []


async def test_a_session_already_answering_is_409(
    client: AsyncClient, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    await session.execute(update(Conversation).values(generating_since=datetime.now(UTC)))
    await session.commit()

    response = await send(client, mine, conversation)

    assert (response.status_code, response.json()['code']) == (status.HTTP_409_CONFLICT, 'generation_in_progress')


async def test_a_lock_left_by_a_dead_server_is_taken_over(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    await session.execute(update(Conversation).values(generating_since=datetime.now(UTC) - timedelta(hours=1)))
    await session.commit()

    response = await send(client, mine, conversation)
    await finished(app)

    assert parse_sse(response.text)[-1][0] == 'done'


async def test_an_ended_session_takes_no_message(
    client: AsyncClient, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    await put_state(session, conversation, StoryState(minutes=clock(1, 8), place='home', ending='solo'))

    response = await send(client, mine, conversation)

    assert (response.status_code, response.json()['code']) == (status.HTTP_409_CONFLICT, 'session_ended')
    assert router.routed == []
    session.expire_all()
    assert (await session.scalars(select(Conversation.generating_since))).one() is None


async def test_an_epilogue_still_takes_messages(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    mine: dict,
):
    conversation = await start_with_luna(client, asset, mine, {'after_ending': 'epilogue'})
    await put_state(session, conversation, StoryState(minutes=clock(1, 8), place='home', ending='solo'))

    response = await send(client, mine, conversation)
    await finished(app)

    assert parse_sse(response.text)[-1][0] == 'done'


@pytest.mark.parametrize(
    ('setup', 'status_code', 'code'),
    [
        ('short', status.HTTP_402_PAYMENT_REQUIRED, 'credit_short'),
        ('not_for_sale', status.HTTP_422_UNPROCESSABLE_CONTENT, 'model_unavailable'),
        ('down', status.HTTP_503_SERVICE_UNAVAILABLE, 'billing_unavailable'),
    ],
)
async def test_a_hold_that_does_not_take_keeps_the_message_and_calls_no_model(
    client: AsyncClient,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
    setup: str,
    status_code: int,
    code: str,
):
    if setup == 'short':
        billing.balances[ME] = 10
    elif setup == 'not_for_sale':
        billing.not_for_sale.add(PRICE_CODE)
    else:
        billing.down = True

    response = await send(client, mine, conversation)

    assert (response.status_code, response.json()['code']) == (status_code, code)
    assert router.provider.calls == []
    # 사람의 말은 남는다. 차례는 놓고 기록은 declined 다
    saved = (await session.scalars(select(Message))).one()
    assert response.json()['message_id'] == str(saved.id)
    generation = await generation_of(session)
    assert (generation.billing_status, generation.error_code) == ('declined', code)
    session.expire_all()
    assert (await session.scalars(select(Conversation.generating_since))).one() is None


@pytest.mark.parametrize(
    ('refuse', 'status_code', 'code'),
    [
        ('model_unavailable', status.HTTP_422_UNPROCESSABLE_CONTENT, 'model_unavailable'),
        ('provider_not_configured', status.HTTP_503_SERVICE_UNAVAILABLE, 'provider_unavailable'),
    ],
)
async def test_a_model_that_cannot_be_called_is_refused_before_the_hold(
    client: AsyncClient,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
    refuse: str,
    status_code: int,
    code: str,
):
    router.refuse = refuse

    response = await send(client, mine, conversation)

    assert (response.status_code, response.json()['code']) == (status_code, code)
    assert billing.calls == []


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
    router.provider.pieces = []
    router.provider.error = ProviderError('timeout')

    response = await send(client, mine, conversation)
    await finished(app)

    assert parse_sse(response.text)[-1] == ('failed', {'code': 'timeout'})
    generation = await generation_of(session)
    assert (generation.billing_status, generation.outcome, generation.error_code) == ('released', 'failed', 'timeout')
    assert billing.balance(ME) == 100
    assert [message['role'] for message in (await detail(client, mine, conversation))['messages']] == ['user']


async def test_a_failure_midway_keeps_what_came_and_charges(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    router.provider.pieces = ['@mina: 그래서 말인데']
    router.provider.error = ProviderError('status_500')

    response = await send(client, mine, conversation)
    await finished(app)

    done = parse_sse(response.text)[-1]
    assert done[0] == 'done'
    assert (done[1]['message']['status'], done[1]['message']['segments']) == (
        'partial',
        [{'speaker': 'mina', 'text': '그래서 말인데'}],
    )
    generation = await generation_of(session)
    assert (generation.billing_status, generation.outcome, generation.error_code) == (
        'captured',
        'partial',
        'status_500',
    )


async def test_a_cut_answer_is_saved_as_partial_and_charged(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    router.provider.truncated = True

    response = await send(client, mine, conversation)
    await finished(app)

    assert parse_sse(response.text)[-1][1]['message']['status'] == 'partial'
    assert (await generation_of(session)).billing_status == 'captured'


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
    router.provider.hold = hold

    response_task = asyncio.create_task(send(client, mine, conversation))
    while not router.provider.calls:
        await asyncio.sleep(0.01)
    billing.down = True
    hold.set()
    await response_task
    await finished(app)

    generation = await generation_of(session)
    assert (generation.billing_status, generation.settle_attempts) == ('capture_due', 1)
    assert generation.next_settle_at is not None


def test_the_stream_address_is_left_out_of_the_request_spans():
    assert STREAMS.matches(f'{CONVERSATIONS_URL}/{uuid.uuid4()}/messages')
    assert STREAMS.matches(f'{CONVERSATIONS_URL}/{uuid.uuid4()}/actions')
    assert not STREAMS.matches(f'{CONVERSATIONS_URL}/{uuid.uuid4()}')
