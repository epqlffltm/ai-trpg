# trpg-server/tests/test_metrics.py

"""
메트릭을 세는 곳을 검증한다. 이름, 단위, label 이 docs/observability.md 의 "메트릭"의 표와 같은지 본다.
메모리에 모으는 것(tests/metrics.py)으로 읽는다. 끝에서 끝까지(Prometheus 에 들어오는가)는 CI 의 stack 이 본다.

  - HTTP 셋(app/observability/request_metrics.py). 테이블의 스트림은 수에만 든다
  - DB 넷(readiness 의 db_up, 연결 풀)
  - 작업 넷(맡긴 작업 app/core/jobs.py, 도는 작업의 한 바퀴)
  - SSE 셋(app/realtime/router.py)
  - AI 호출(app/ai_log/metered.py), 다시 시도와 넘어가기(app/rounds/retrying_narrator.py)
  - 라운드(닫기 시작 app/rounds/service.py, 서술 app/rounds/closing.py)
  - 서술 값(결제 서버를 부른 것 app/billing/metered.py, 끝나지 않은 청구 app/billing/settler.py)
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from ai_core.calls import CallRecord, CallScope, Outcome
from ai_core.fake import FakeCallLog
from ai_core.provider import Reasoning
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import text

from app.ai_log.metered import MeteredCallLog
from app.ai_log.retention import PRUNE_OPERATION, AiLogPruner
from app.api import readiness
from app.billing.client import (
    BillingRejected,
    BillingUnavailable,
    ExtendOutcome,
    ExtendResult,
    HoldOutcome,
    HoldResult,
)
from app.billing.free_billing import FreeBilling
from app.billing.metered import MeteredBilling
from app.billing.models import UNFINISHED_STATUSES
from app.billing.repository import unfinished_by_status
from app.billing.settler import ChargeSettler
from app.core.database import POOL_MAX_CONNECTIONS
from app.core.jobs import BackgroundJobs
from app.main import API_PREFIX
from app.observability.metrics import (
    DURATION_BUCKETS,
    LONG_DURATION_BUCKETS,
    OTHER_METHOD,
    STREAM_BUCKETS,
    method_label,
    record_request,
)
from app.observability.pool_metrics import MeteredPool
from app.observability.request_metrics import RequestMetricsMiddleware
from app.realtime.router import encode_all
from app.realtime.sse import Frame
from app.rounds.clock import CLOCK_OPERATION
from app.rounds.closing import NARRATE_OPERATION
from app.rounds.llm_narrator import NarrationError
from app.rounds.narrator import NO_PREVIEW, Move, NarrationRequest, Preview, StoryContext
from app.rounds.retrying_narrator import RetryingNarrator
from tests.metrics import MetricsRecorder
from tests.test_npc_actions import bearer, declare, table_url
from tests.test_round_time_limit import after, clock_at, current, start_with

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
STREAM = f'{API_PREFIX}/tables/9d1c2b3a-4e5f-4a6b-8c7d-0e1f2a3b4c5d/stream'


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """두 번째로 앉는 사람."""
    return bearer(signing_key, FRIEND)


def bounds_of(metrics: MetricsRecorder, name: str) -> tuple[float, ...]:
    """그 이름의 히스토그램의 구간."""
    data = metrics.reader.get_metrics_data()
    point = next(
        metric.data.data_points[0]
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name == name
    )
    return tuple(point.explicit_bounds)


# --- HTTP ---


async def test_a_request_is_counted_by_method_route_and_status(client: AsyncClient, metrics: MetricsRecorder):
    await client.get(f'{API_PREFIX}/me')

    labels = {'method': 'GET', 'route': f'{API_PREFIX}/me'}
    assert metrics.value('http_server_requests', **labels, status_code=401) == 1
    assert metrics.value('http_server_request_duration', **labels) == 1
    # 끝난 요청은 처리 중인 수에서 빠진다
    assert metrics.value('http_server_active_requests') == 0


async def test_the_route_is_the_template_and_unmatched_is_one_label(client: AsyncClient, metrics: MetricsRecorder):
    await client.get(f'{API_PREFIX}/tables/{uuid.uuid4()}')
    await client.get('/no/such/secret-path')

    routes = {point.labels['route'] for point in metrics.points('http_server_requests')}
    assert routes == {f'{API_PREFIX}/tables/{{table_id}}', '(unmatched)'}


def test_an_unknown_method_is_one_label():
    assert method_label('GET') == 'GET'
    assert method_label('BREW') == OTHER_METHOD


async def test_the_duration_is_in_seconds_with_the_shared_buckets(client: AsyncClient, metrics: MetricsRecorder):
    await client.get('/health')

    (point,) = metrics.points('http_server_request_duration')
    assert point.unit == 's'
    assert bounds_of(metrics, 'http_server_request_duration') == DURATION_BUCKETS


async def test_a_request_that_raises_is_counted_as_500(metrics: MetricsRecorder):
    async def broken(scope, receive, send) -> None:
        raise RuntimeError('부서졌다')

    with pytest.raises(RuntimeError):
        await RequestMetricsMiddleware(broken)({'type': 'http', 'method': 'GET', 'path': '/x'}, None, None)

    assert metrics.value('http_server_requests', status_code=500) == 1
    assert metrics.value('http_server_active_requests') == 0


async def test_a_scope_that_is_not_http_is_not_counted(metrics: MetricsRecorder):
    seen: list[dict] = []

    async def inner(scope, receive, send) -> None:
        seen.append(scope)

    await RequestMetricsMiddleware(inner)({'type': 'lifespan'}, None, None)

    assert seen == [{'type': 'lifespan'}]
    assert metrics.points('http_server_requests') == []


async def test_a_stream_is_counted_but_neither_timed_nor_active(metrics: MetricsRecorder):
    active_while_open: list[float | None] = []

    async def streaming(scope, receive, send) -> None:
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        active_while_open.append(metrics.value('http_server_active_requests'))

    async def ignore(message) -> None:
        return

    await RequestMetricsMiddleware(streaming)({'type': 'http', 'method': 'GET', 'path': STREAM}, None, ignore)

    # 몇 시간씩 열려 있는 스트림이 처리 중인 수와 시간 분포를 덮지 않는다. 스트림은 sse_* 가 센다
    assert active_while_open == [None]
    assert metrics.value('http_server_requests', status_code=200) == 1
    assert metrics.points('http_server_request_duration') == []


def test_recording_without_a_provider_does_nothing():
    # 끼운 것이 없으면(NoOp) 세어도 아무 일이 없다. 테스트가 아닌 PC 에서 띄운 서버와 같다
    record_request('GET', '/health', 200, 0.01)


# --- DB ---


async def test_readiness_records_the_database_state(
    client: AsyncClient, metrics: MetricsRecorder, monkeypatch: pytest.MonkeyPatch
):
    await client.get('/health/ready')
    assert metrics.value('db_up') == 1

    async def unreachable(session) -> str:
        return 'DB 에 닿지 않는다(OSError)'

    monkeypatch.setattr(readiness, 'database_problem', unreachable)
    response = await client.get('/health/ready')

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert metrics.value('db_up') == 0


async def test_a_redis_that_is_down_is_not_a_database_that_is_down(
    client: AsyncClient, metrics: MetricsRecorder, monkeypatch: pytest.MonkeyPatch
):
    async def unreachable(client) -> str:
        return 'Redis 에 닿지 않는다(OSError)'

    monkeypatch.setattr(readiness, 'redis_problem', unreachable)
    response = await client.get('/health/ready')

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert metrics.value('db_up') == 1


async def test_a_database_that_hangs_is_not_reachable(
    client: AsyncClient, metrics: MetricsRecorder, monkeypatch: pytest.MonkeyPatch
):
    async def hanging(session) -> None:
        await asyncio.sleep(30)

    monkeypatch.setattr(readiness, 'READINESS_TIMEOUT_SECONDS', 0.2)
    monkeypatch.setattr(readiness, 'database_problem', hanging)
    response = await client.get('/health/ready')

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert metrics.value('db_up') == 0


async def test_the_pool_reports_its_connections_and_waits(app: FastAPI, metrics: MetricsRecorder):
    async with app.state.engine.connect() as connection:
        await connection.execute(text('SELECT 1'))
        in_use = metrics.value('db_pool_connections', state='in_use')

    assert in_use is not None and in_use >= 1
    assert metrics.value('db_pool_connections', state='idle') is not None
    assert metrics.value('db_pool_connections_max') == POOL_MAX_CONNECTIONS
    (wait,) = metrics.points('db_pool_wait')
    assert (wait.unit, wait.value >= 1) == ('s', True)


def test_the_engine_uses_the_metered_pool(app: FastAPI):
    # SQLAlchemy 의 안쪽 이름(_do_get)을 감싼다. 판이 바뀌어 이름이 사라지면 여기서 안다
    assert isinstance(app.state.engine.sync_engine.pool, MeteredPool)
    assert callable(getattr(super(MeteredPool, app.state.engine.sync_engine.pool), '_do_get', None))


# --- 작업 ---


async def test_a_spawned_job_is_counted_once_it_runs(metrics: MetricsRecorder):
    jobs = BackgroundJobs()

    async def job() -> None:
        assert metrics.value('background_jobs_running', operation='lore.index') == 1

    jobs.spawn(job(), name='index:1', operation='lore.index')
    await jobs.drain()

    labels = {'operation': 'lore.index'}
    assert metrics.value('background_jobs_started', **labels) == 1
    assert metrics.value('background_jobs_finished', **labels, result='success') == 1
    assert metrics.value('background_jobs_running', **labels) == 0
    assert metrics.value('background_job_duration', **labels) == 1


async def test_a_failed_job_is_a_server_error(metrics: MetricsRecorder):
    jobs = BackgroundJobs()

    async def job() -> None:
        raise RuntimeError('부서졌다')

    jobs.spawn(job(), name='index:1', operation='lore.index')
    await jobs.drain()

    assert metrics.value('background_jobs_finished', operation='lore.index', result='server_error') == 1


async def test_a_job_stopped_by_shutdown_is_cancelled(metrics: MetricsRecorder):
    jobs = BackgroundJobs()

    async def job() -> None:
        await asyncio.sleep(30)

    jobs.spawn(job(), name='index:1', operation='lore.index')
    await asyncio.sleep(0)
    await jobs.aclose(grace=0)

    assert metrics.value('background_jobs_finished', operation='lore.index', result='cancelled') == 1
    assert metrics.value('background_jobs_running', operation='lore.index') == 0


@pytest.mark.usefixtures('clean_tables')
async def test_a_round_of_a_loop_is_counted_as_a_job(app: FastAPI, metrics: MetricsRecorder):
    await AiLogPruner(app.state.session_factory, 30, clock=lambda: datetime.now(UTC)).tick()

    assert metrics.value('background_jobs_finished', operation=PRUNE_OPERATION, result='success') == 1


# --- SSE ---


async def frames(count: int) -> AsyncIterator[Frame]:
    """스트림에 실을 메시지 count 개."""
    for number in range(count):
        yield Frame(event='table_event', data='{}', id=f'{number}-0-0')


async def test_a_stream_is_counted_from_its_first_message_until_it_ends(metrics: MetricsRecorder):
    sent = [chunk async for chunk in encode_all(frames(2))]

    assert len(sent) == 2
    assert metrics.value('sse_connections_opened') == 1
    assert metrics.value('sse_connections') == 0
    (duration,) = metrics.points('sse_connection_duration')
    assert (duration.unit, duration.value) == ('s', 1)
    assert bounds_of(metrics, 'sse_connection_duration') == STREAM_BUCKETS


async def test_a_stream_cut_off_by_the_reader_is_still_counted(metrics: MetricsRecorder):
    stream = encode_all(frames(5))
    await anext(stream)
    assert metrics.value('sse_connections') == 1

    # 받는 쪽이 끊으면 응답이 스트림을 닫는다
    await stream.aclose()

    assert metrics.value('sse_connections') == 0
    assert metrics.value('sse_connection_duration') == 1


# --- AI 호출 ---


def call(**changes: object) -> CallRecord:
    """서술 호출 하나의 기록."""
    values = {
        'scope': CallScope(purpose='narration'),
        'provider': 'openai',
        'model': 'model-a',
        'prompt_version': 'narration-3',
        'reasoning': Reasoning.NONE,
        'outcome': Outcome.OK,
        'latency_ms': 2400,
        'input_tokens': 1050,
        'output_tokens': 180,
    }
    return CallRecord(**{**values, **changes})


class BrokenLog:
    """쓰면 실패하는 기록장. DB 가 내려간 것이다."""

    async def write(self, record: CallRecord) -> None:
        raise OSError('DB 에 닿지 않는다')


async def test_an_ai_call_is_counted_with_its_time_and_tokens(metrics: MetricsRecorder):
    inner = FakeCallLog()

    await MeteredCallLog(inner).write(call())

    labels = {'operation': 'narration', 'provider': 'openai', 'model': 'model-a'}
    assert inner.records == [call()]
    assert metrics.value('ai_calls', **labels, outcome='ok') == 1
    (duration,) = metrics.points('ai_call_duration')
    assert (duration.labels, duration.unit, duration.value) == (labels, 's', 1)
    assert bounds_of(metrics, 'ai_call_duration') == LONG_DURATION_BUCKETS
    assert metrics.value('ai_tokens', provider='openai', model='model-a', direction='input') == 1050
    assert metrics.value('ai_tokens', provider='openai', model='model-a', direction='output') == 180


async def test_a_call_without_an_answer_has_no_tokens(metrics: MetricsRecorder):
    await MeteredCallLog(FakeCallLog()).write(call(outcome=Outcome.FAILED, input_tokens=None, output_tokens=None))

    assert metrics.value('ai_calls', outcome='failed') == 1
    assert metrics.points('ai_tokens') == []


async def test_a_call_is_counted_even_when_the_record_cannot_be_written(metrics: MetricsRecorder):
    with pytest.raises(OSError):
        await MeteredCallLog(BrokenLog()).write(call())

    # 호출은 이미 시간과 토큰을 썼다
    assert metrics.value('ai_calls', outcome='ok') == 1


REQUEST = NarrationRequest(
    round_number=1,
    scene='사이렌이 울린다.',
    moves=[Move('엘프', '달린다.')],
    story=StoryContext(title='추격전', rating='all', guide=''),
)


@dataclass
class Scripted:
    """정해 둔 대로 답하는 모델 하나의 서술자. outcomes 를 차례로 꺼내 글이면 돌려주고 예외면 올린다."""

    model: str
    outcomes: list = field(default_factory=list)

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def retrying(*narrators: Scripted) -> RetryingNarrator:
    """쉬지 않고 다시 시도하는 서술자."""

    async def no_sleep(seconds: float) -> None:
        return

    return RetryingNarrator(list(narrators), attempt_timeout=1.0, pause=lambda: 0.0, sleep=no_sleep)


async def test_a_retry_and_a_fallback_are_counted(metrics: MetricsRecorder):
    first = Scripted('model-a', [NarrationError('cut_off'), NarrationError('cut_off')])
    second = Scripted('model-b', ['장면'])

    assert await retrying(first, second).narrate(REQUEST) == '장면'

    assert metrics.value('round_narration_retries') == 1
    # 넘어간 것의 model 은 실패해 떠난 모델이다
    assert metrics.value('ai_fallbacks', operation='narration', model='model-a') == 1


async def test_a_good_first_answer_counts_no_retry_and_no_fallback(metrics: MetricsRecorder):
    assert await retrying(Scripted('model-a', ['장면']), Scripted('model-b')).narrate(REQUEST) == '장면'

    assert metrics.points('round_narration_retries') == []
    assert metrics.points('ai_fallbacks') == []


# --- 라운드 ---


class FailingNarrator:
    """늘 실패하는 서술자."""

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        raise RuntimeError('서술자가 답하지 못했다')


@pytest.mark.usefixtures('clean_tables')
async def test_a_round_closed_by_everyone_is_counted_and_its_narration_too(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], narrated, metrics: MetricsRecorder
):
    table = await start_with(client, me, friend)
    await declare(client, me, table, '달린다.')
    assert metrics.points('rounds_closed') == []

    await declare(client, friend, table, '숨는다.')
    await narrated()

    assert metrics.value('rounds_closed', reason='all_declared') == 1
    assert metrics.value('round_narrations', result='success') == 1
    (duration,) = metrics.points('round_narration_duration')
    assert (duration.unit, duration.value) == ('s', 1)
    assert bounds_of(metrics, 'round_narration_duration') == LONG_DURATION_BUCKETS
    assert metrics.value('background_jobs_finished', operation=NARRATE_OPERATION, result='success') == 1


@pytest.mark.usefixtures('clean_tables')
async def test_a_round_closed_by_the_host_is_counted_once(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated, metrics: MetricsRecorder
):
    app.state.narrator = FailingNarrator()
    table = await start_with(client, me, friend)
    closed = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    assert closed.status_code == status.HTTP_202_ACCEPTED, closed.text
    await narrated()

    # 실패한 서술을 다시 맡긴 것은 새로 닫은 것이 아니다
    again = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    assert again.status_code == status.HTTP_202_ACCEPTED, again.text
    await narrated()

    assert metrics.value('rounds_closed', reason='host') == 1
    assert metrics.value('round_narrations', result='failure') == 2
    assert metrics.points('round_narration_duration') == []
    assert metrics.value('background_jobs_finished', operation=NARRATE_OPERATION, result='server_error') == 2


@pytest.mark.usefixtures('clean_tables')
async def test_a_round_closed_by_the_clock_is_a_timeout(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated, metrics: MetricsRecorder
):
    table = await start_with(client, me, friend, round_time_limit=60)
    round_ = await current(client, me, table)

    await clock_at(app, after(round_)).tick()
    await narrated()

    assert metrics.value('rounds_closed', reason='timeout') == 1
    assert metrics.value('background_jobs_finished', operation=CLOCK_OPERATION, result='success') == 1


# --- 서술 값 ---


@dataclass
class Answering:
    """정해 둔 결과를 돌려주거나 정해 둔 예외를 올리는 결제 서버."""

    held: HoldOutcome = HoldOutcome(HoldResult.HELD)
    extended: ExtendOutcome = ExtendOutcome(ExtendResult.EXTENDED)
    error: Exception | None = None

    def answer[Result](self, result: Result) -> Result:
        if self.error is not None:
            raise self.error
        return result

    async def hold(self, reference: str, user_id: uuid.UUID, price_code: str) -> HoldOutcome:
        return self.answer(self.held)

    async def capture(self, reference: str) -> None:
        return self.answer(None)

    async def release(self, reference: str) -> None:
        return self.answer(None)

    async def extend(self, reference: str) -> ExtendOutcome:
        return self.answer(self.extended)


async def call_all(billing: MeteredBilling) -> None:
    """네 일을 한 번씩 부른다."""
    await billing.hold('r', ME, 'p')
    await billing.capture('r')
    await billing.release('r')
    await billing.extend('r')


async def test_billing_calls_are_counted_by_operation_and_outcome(metrics: MetricsRecorder):
    await call_all(MeteredBilling(Answering()))
    await MeteredBilling(Answering(held=HoldOutcome(HoldResult.SHORT))).hold('r', ME, 'p')
    await MeteredBilling(Answering(extended=ExtendOutcome(ExtendResult.MISSING))).extend('r')
    await MeteredBilling(Answering(extended=ExtendOutcome(ExtendResult.ENDED))).extend('r')

    counted = {
        (point.labels['operation'], point.labels['outcome']): point.value for point in metrics.points('billing_calls')
    }
    assert counted == {
        ('hold', 'held'): 1,
        ('hold', 'short'): 1,
        ('capture', 'done'): 1,
        ('release', 'done'): 1,
        ('extend', 'done'): 1,
        ('extend', 'missing'): 1,
        ('extend', 'ended'): 1,
    }


@pytest.mark.parametrize(
    ('error', 'outcome'), [(BillingUnavailable('timeout'), 'unavailable'), (BillingRejected(409), 'rejected')]
)
async def test_a_failed_billing_call_is_counted_and_raised(error: Exception, outcome: str, metrics: MetricsRecorder):
    billing = MeteredBilling(Answering(error=error))

    with pytest.raises(type(error)):
        await billing.capture('r')

    assert metrics.value('billing_calls', operation='capture', outcome=outcome) == 1


@pytest.mark.usefixtures('clean_tables')
async def test_the_settler_reports_every_unfinished_status(app: FastAPI, metrics: MetricsRecorder):
    await ChargeSettler(app.state.session_factory, billing=FreeBilling).tick()

    statuses = {point.labels['status']: point.value for point in metrics.points('narration_charges')}
    # 없는 상태도 0 으로 낸다. 끝난 것과 failed 는 내지 않는다
    assert statuses == {status.value: 0 for status in UNFINISHED_STATUSES}


async def test_counting_unfinished_charges_reads_only_the_two_partial_indexes(app: FastAPI):
    # 끝난 청구가 쌓여도 매 바퀴(5초)의 셈이 표 전체를 읽지 않는다. 표가 작으면 PostgreSQL 이 표를 읽는 쪽을
    # 고르므로 그 길을 막고 계획을 본다
    query = unfinished_by_status().compile(app.state.engine.sync_engine, compile_kwargs={'literal_binds': True})
    async with app.state.engine.connect() as connection:
        await connection.execute(text('SET LOCAL enable_seqscan = off'))
        plan = '\n'.join(row[0] for row in await connection.execute(text(f'EXPLAIN {query}')))

    assert 'BitmapOr' in plan
    assert 'ix_narration_charges_due' in plan
    assert 'ix_narration_charges_open' in plan
