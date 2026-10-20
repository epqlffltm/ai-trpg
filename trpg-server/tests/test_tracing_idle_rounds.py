# trpg-server/tests/test_tracing_idle_rounds.py

"""
할 일이 없던 바퀴의 추적을 보내지 않는 것을 검증한다.
app/observability/idle_rounds.py 의 DropIdleRounds, app/observability/spans.py 의 add_handled 와 job_span,
5초마다 도는 바퀴 셋(app/rounds/clock.py, app/billing/settler.py, app/notifications/dispatcher.py).

메모리에 모으는 것(tests/spans.py)이 서버와 같은 DropIdleRounds 를 거친다.
바퀴는 DB 를 쓰는 부분을 가짜로 바꿔 돌린다. 실제 DB 로 도는 바퀴는 마지막 테스트가 본다.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

import pytest
from fastapi import FastAPI
from opentelemetry.trace import StatusCode

from app.billing.settler import ChargeSettler
from app.notifications.dispatcher import NotificationDispatcher
from app.observability.spans import ATTRIBUTE_HANDLED, add_handled, job_span, tracer
from app.rounds.clock import RoundClock
from tests.spans import SpanRecorder

TABLE = uuid.UUID('00000000-0000-4000-8000-000000000001')


def query_span(name: str = 'db SELECT tables') -> None:
    """바퀴 안의 쿼리 하나만큼의 span."""
    tracer().start_span(name).end()


def round_of(handled: int | None, fail: bool = False) -> None:
    """작업 한 바퀴. 쿼리 하나를 남기고, 맡은 수를 더한다(None 이면 더하지 않는다)."""
    with job_span('round.close_overdue', 'job-1'):
        query_span()
        if handled is not None:
            add_handled(handled)
        if fail:
            raise RuntimeError('DB 가 없다')


def test_add_handled_outside_a_job_does_nothing(spans: SpanRecorder):
    add_handled(3)

    with job_span('round.narrate', 'job-1'):
        pass

    assert ATTRIBUTE_HANDLED not in spans.only().attributes


def test_job_span_carries_the_sum_of_handled(spans: SpanRecorder):
    with job_span('charge.settle', 'job-1'):
        add_handled(2)
        add_handled(0)
        add_handled(3)

    assert spans.only().attributes[ATTRIBUTE_HANDLED] == 5


def test_an_idle_round_is_dropped_with_its_queries(spans: SpanRecorder):
    round_of(0)

    assert spans.ended() == []


def test_a_round_that_took_something_is_kept_with_its_queries(spans: SpanRecorder):
    round_of(1)

    assert spans.names() == ['db SELECT tables', 'round.close_overdue']


def test_a_failed_round_is_kept_even_if_it_took_nothing(spans: SpanRecorder):
    with pytest.raises(RuntimeError):
        round_of(0, fail=True)

    assert spans.find('round.close_overdue').status.status_code == StatusCode.ERROR
    assert len(spans.ended()) == 2


def test_a_job_without_handled_is_kept(spans: SpanRecorder):
    round_of(None)

    assert len(spans.ended()) == 2


def test_a_round_under_a_request_is_not_held(spans: SpanRecorder):
    # 부모가 있는 작업(요청이 맡긴 것)은 그 요청의 추적이라 버리지 않는다
    with spans.parent():
        round_of(0)

    assert spans.names() == ['db SELECT tables', 'round.close_overdue']


def test_a_request_trace_passes_through_as_spans_end(spans: SpanRecorder):
    with spans.parent():
        query_span()
        assert spans.names() == ['db SELECT tables']


@dataclass(frozen=True)
class QuietClock(RoundClock):
    """DB 대신 정해 둔 테이블을 찾는 시계. overdue 의 테이블만 닫는다."""

    found: tuple[uuid.UUID, ...] = ()

    async def vanished(self, now: datetime) -> list[uuid.UUID]:
        return []

    async def waiting(self, now: datetime) -> list[uuid.UUID]:
        return []

    async def overdue(self, now: datetime) -> list[uuid.UUID]:
        query_span('db SELECT rounds')
        return list(self.found)

    async def close_one(self, table_id: uuid.UUID, now: datetime) -> bool:
        # 닫다가 실패한 것(False)이다. 그래도 맡은 것이라 추적은 남는다
        return False


def clock_finding(*found: uuid.UUID) -> QuietClock:
    return QuietClock(session_factory=None, scheduler=lambda: None, dice=lambda: None, found=found)  # type: ignore[arg-type]


async def test_the_clock_drops_a_round_that_found_nothing(spans: SpanRecorder):
    await clock_finding().tick()

    assert spans.ended() == []


async def test_the_clock_keeps_a_round_that_found_a_table_even_if_closing_failed(spans: SpanRecorder):
    assert await clock_finding(TABLE).tick() == 0

    span = spans.find('round.close_overdue')
    assert span.attributes[ATTRIBUTE_HANDLED] == 1
    assert 'db SELECT rounds' in spans.names()


@dataclass(frozen=True)
class QuietSettler(ChargeSettler):
    """DB 대신 정해 둔 수를 돌려주는 청구 정리."""

    abandoned: int = 0

    async def abandon(self, now: datetime) -> int:
        return self.abandoned

    async def due(self, now: datetime) -> list:
        return []

    async def count_unfinished(self) -> dict[str, int]:
        return {}


async def test_the_settler_counts_what_it_released(spans: SpanRecorder):
    await QuietSettler(session_factory=None, billing=lambda: None).tick()  # type: ignore[arg-type]
    assert spans.ended() == []

    await QuietSettler(session_factory=None, billing=lambda: None, abandoned=2).tick()  # type: ignore[arg-type]
    assert spans.find('charge.settle').attributes[ATTRIBUTE_HANDLED] == 2


@dataclass(frozen=True)
class QuietDispatcher(NotificationDispatcher):
    """DB 대신 정해 둔 수를 돌려주는 알림 보내기. 보낼 곳이 없다."""

    stale: int = 0

    async def drop_stale(self, now: datetime) -> int:
        return self.stale


async def test_the_dispatcher_counts_what_it_dropped(spans: SpanRecorder):
    await QuietDispatcher(session_factory=None, notifications=lambda: None).tick()  # type: ignore[arg-type]
    assert spans.ended() == []

    await QuietDispatcher(session_factory=None, notifications=lambda: None, stale=1).tick()  # type: ignore[arg-type]
    assert spans.find('notification.send').attributes[ATTRIBUTE_HANDLED] == 1


@pytest.mark.usefixtures('clean_tables')
async def test_an_idle_round_of_the_real_clock_leaves_no_trace(app: FastAPI, spans: SpanRecorder):
    # 실제 DB 에서 찾아낸 것이 없는 바퀴. 쿼리는 돌았지만 하나도 보내지 않는다
    await app.state.round_clock.tick()

    assert spans.ended() == []
