# trpg-server/tests/test_tracing_idle_rounds.py

"""
할 일이 없던 바퀴의 추적을 보내지 않는 것을 이 서버의 바퀴로 검증한다.
5초마다 도는 바퀴 셋(app/rounds/clock.py, app/billing/settler.py, server_core/notifications/dispatcher.py)이
맡은 수를 싣는지 본다.
버리는 규칙(server_core/observability/idle_rounds.py 의 DropIdleRounds)은 server-core 의 테스트가 본다(#589).

메모리에 모으는 것(server_core/testing/spans.py)이 서버와 같은 DropIdleRounds 를 거친다.
바퀴는 DB 를 쓰는 부분을 가짜로 바꿔 돌린다. 실제 DB 로 도는 바퀴는 마지막 테스트가 본다.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

import pytest
from fastapi import FastAPI
from server_core.notifications.dispatcher import NotificationDispatcher
from server_core.observability.spans import ATTRIBUTE_HANDLED, add_handled, job_span, tracer
from server_core.testing.spans import SpanRecorder

from app.billing.settler import ChargeSettler
from app.rounds.clock import RoundClock

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
class QuietOutbox:
    """DB 대신 정해 둔 수를 돌려주는 발송함(server_core/notifications/store.py 의 OutboxStore). 보낼 것은 없다."""

    stale: int = 0

    async def drop_stale(self, cutoff: datetime) -> int:
        return self.stale

    async def due(self, now: datetime, limit: int) -> list:
        return []


async def test_the_dispatcher_counts_what_it_dropped(spans: SpanRecorder):
    await NotificationDispatcher(store=QuietOutbox(), notifications=lambda: None).tick()  # type: ignore[arg-type]
    assert spans.ended() == []

    await NotificationDispatcher(store=QuietOutbox(stale=1), notifications=lambda: None).tick()  # type: ignore[arg-type]
    assert spans.find('notification.send').attributes[ATTRIBUTE_HANDLED] == 1


@pytest.mark.usefixtures('clean_tables')
async def test_an_idle_round_of_the_real_clock_leaves_no_trace(app: FastAPI, spans: SpanRecorder):
    # 실제 DB 에서 찾아낸 것이 없는 바퀴. 쿼리는 돌았지만 하나도 보내지 않는다
    await app.state.round_clock.tick()

    assert spans.ended() == []
