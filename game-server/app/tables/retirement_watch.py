# game-server/app/tables/retirement_watch.py

"""
서술 모델의 은퇴를 지켜보는 작업. 한 시간마다 한 바퀴 돈다(app/tables/model_retirement.py 의 규칙).

한 바퀴에 은퇴일이 30 일 안에 들었거나 이미 지난 모델을 쓰는 테이블을 찾아, 테이블마다 따로 잠그고 본다.
  - 은퇴가 다가오면 그 단계(30, 14, 7, 1 일 전)를 알린다.
  - 은퇴했으면 같은 회사의 다른 모델로 바꾼다. 없으면 방장에게 알린다.
은퇴는 날짜(UTC)의 시작부터다. 하루에 한 번만 돌면 은퇴한 뒤 하루 가까이 서술이 막힐 수 있어 한 시간마다 본다.
볼 테이블이 없으면 DB 를 한 번 읽고 끝난다.

라운드가 열린 뒤에도 그 테이블 하나를 본다(after_round_opened). 작업이 아직 돌지 않았어도 은퇴한 모델로
라운드를 계속하지 않게 한다. 라운드를 연 트랜잭션이 끝난 뒤에 따로 본다. 실패해도 라운드에는 영향이 없다.

서버가 여럿이면 모두 같은 일을 한다. 테이블을 잠그고 보고, 알린 단계를 적어 두므로 같은 알림이 두 번 가지 않는다.
결제 서버의 가격 목록을 받지 못하면 그 테이블은 바꾸지 않고 다음 바퀴에 다시 본다.

로그는 청구 정리와 같은 규칙이다(app/billing/settler.py). 바퀴마다 job_id 를 걸고, operation 은 model.retirement 다.
"""

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.billing.price_list import PriceList
from app.core import loops
from app.core.jobs import JOB_FAILED_ERROR_CODE, elapsed_ms
from app.core.loops import Running
from app.observability.context import job_scope
from app.observability.identifiers import new_job_id
from app.tables import model_retirement
from app.tables import repository as table_repository
from app.tables.model_retirement import NOTHING, Checked

logger = logging.getLogger(__name__)

# 몇 초마다 보는가
WATCH_INTERVAL_SECONDS = 60 * 60
# 로그의 operation. 정해진 이름이다(docs/observability.md)
WATCH_OPERATION = 'model.retirement'


def now_utc() -> datetime:
    """지금 시각(UTC)."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class Watched:
    """한 바퀴에 한 일. 알린 테이블, 바꾼 테이블, 대신할 모델이 없다고 알린 테이블, 보지 못한 테이블의 수."""

    noticed: int = 0
    replaced: int = 0
    stranded: int = 0
    failed: int = 0

    def busy(self) -> bool:
        """한 일이 있었는가."""
        return bool(self.noticed or self.replaced or self.stranded or self.failed)


def add(watched: Watched, checked: Checked | None) -> Watched:
    """한 테이블을 본 것을 더한다. None 이면 보지 못했다."""
    if checked is None:
        return Watched(watched.noticed, watched.replaced, watched.stranded, watched.failed + 1)
    return Watched(
        watched.noticed + checked.noticed,
        watched.replaced + checked.replaced,
        watched.stranded + checked.stranded,
        watched.failed,
    )


@dataclass(frozen=True)
class RetirementWatch:
    """
    은퇴를 지켜보는 작업.

    prices 는 부를 때마다 앱에서 꺼낸다. 테스트가 가격 목록을 바꿔 꽂으면 그 뒤부터 바뀐 것을 쓴다.
    clock 은 테스트가 바꿔 꽂는다.
    """

    session_factory: async_sessionmaker[AsyncSession]
    prices: Callable[[], PriceList]
    interval: float = WATCH_INTERVAL_SECONDS
    clock: Callable[[], datetime] = now_utc

    async def check_in(self, session: AsyncSession, table_id: uuid.UUID, now: datetime) -> Checked:
        """테이블 하나를 잠그고 본 뒤 저장한다. 없어졌으면 볼 것이 없다."""
        table = await table_repository.lock_table(session, table_id)
        if table is None:
            return NOTHING
        checked = await model_retirement.check_table(session, table, self.prices(), now)
        await session.commit()
        return checked

    async def check(self, table_id: uuid.UUID, now: datetime) -> Checked:
        """테이블 하나를 제 세션으로 본다. 예외는 그대로 올린다."""
        async with self.session_factory() as session:
            return await self.check_in(session, table_id, now)

    async def check_safely(self, table_id: uuid.UUID, now: datetime) -> Checked | None:
        """테이블 하나를 본다. 예외가 나면 로그에 남기고 None. 한 테이블이 실패해도 다른 테이블은 본다."""
        try:
            return await self.check(table_id, now)
        except Exception:
            logger.exception(
                '서술 모델의 은퇴를 보지 못했습니다',
                extra={
                    'operation': WATCH_OPERATION,
                    'table_id': str(table_id),
                    'result': 'server_error',
                    'error_code': JOB_FAILED_ERROR_CODE,
                },
            )
            return None

    async def after_round_opened(self, table_id: uuid.UUID) -> None:
        """라운드가 열린 뒤 그 테이블을 본다. 예외를 올리지 않는다."""
        await self.check_safely(table_id, self.clock())

    async def watched(self, now: datetime) -> list[uuid.UUID]:
        """볼 테이블들. 잠그지 않는다."""
        async with self.session_factory() as session:
            return await model_retirement.watched_table_ids(session, now.date())

    async def sweep(self) -> Watched:
        """한 바퀴의 일. 볼 테이블을 하나씩 본다."""
        now = self.clock()
        watched = Watched()
        for table_id in await self.watched(now):
            watched = add(watched, await self.check_safely(table_id, now))
        return watched

    async def tick(self) -> Watched:
        """
        한 바퀴. 제 job_id 를 걸고 본 뒤, 어떻게 끝났는지 한 줄을 남긴다.

        찾는 일이 통째로 실패하면(DB 가 없다) 예외를 그대로 올린다. 그 줄은 도는 쪽(run)이 남긴다.
        """
        with job_scope(new_job_id()):
            started = time.perf_counter()
            watched = await self.sweep()
            logger.log(
                logging.INFO if watched.busy() else logging.DEBUG,
                '서술 모델의 은퇴를 한 바퀴 보았습니다',
                extra={
                    'operation': WATCH_OPERATION,
                    'noticed': watched.noticed,
                    'replaced': watched.replaced,
                    'stranded': watched.stranded,
                    'failed': watched.failed,
                    'duration_ms': elapsed_ms(started),
                    'result': 'success',
                },
            )
            return watched

    async def run(self, stop: asyncio.Event) -> None:
        """stop 이 켜질 때까지 interval 마다 한 바퀴씩 돈다. 한 바퀴가 통째로 실패해도 멈추지 않는다."""
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                logger.exception(
                    '서술 모델의 은퇴를 한 바퀴 보지 못했습니다',
                    extra={
                        'operation': WATCH_OPERATION,
                        'result': 'server_error',
                        'error_code': JOB_FAILED_ERROR_CODE,
                    },
                )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.interval)


def start(watch: RetirementWatch) -> Running:
    """은퇴를 지켜보기 시작한다. 서버가 뜰 때 부른다."""
    return loops.start(watch, 'retirement-watch')
