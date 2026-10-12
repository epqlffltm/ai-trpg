# game-server/app/billing/settler.py

"""
정리 작업. 몇 초마다 끝나지 않은 청구를 찾아 결제 서버에 마저 맡긴다.

한 바퀴에 두 가지를 한다.
  1. 끝난 테이블의 끝나지 않은 청구를 "돌려줄 것"으로 바꾼다. 테이블을 끝내는 길(방장이 끝내기, 마지막 사람이 나가기)이
     여럿이라 그 길마다 청구를 챙기지 않고 여기서 한 번에 본다. 끝난 테이블의 서술은 다음 장면이 되지 않는다.
  2. 부를 차례가 된 청구(걸어야 함, 확정할 것, 돌려줄 것)를 하나씩 맡긴다(settling.settle).
     - 걸어야 함: 라운드를 연 뒤 곧 건다. 크레딧이 모자라면 선언하기 전에 알린다.
       결제 서버가 잠깐 죽어도 이미 잡아 둔 값으로 그 라운드는 서술한다
     - 확정할 것, 돌려줄 것: 서술 작업이 바로 부르지만, 그때 못 했으면(결제 서버가 죽었다, 서버가 꺼졌다)
       여기서 마저 한다

답을 받지 못한 청구는 다시 부르기까지 기다리는 시간이 늘어난다(charges.retry_delay). 결제 서버가 오래 죽어 있어도
몇 초마다 두드리지 않는다.

서버가 여럿이면 모두 같은 일을 한다. 같은 청구를 둘이 불러도 된다. 결제 서버는 같은 이름표를 한 번만 처리하고,
상태는 "지금 이 상태일 때만" 옮긴다(app/billing/settling.py).

로그는 라운드의 시계와 같은 규칙이다(app/rounds/clock.py). 바퀴마다 job_id 를 걸고, operation 은 charge.settle 이다.
한 일이 없으면 debug, 있으면 info 로 한 줄을 남긴다. 한 청구가 실패해도 다른 청구는 맡긴다.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.billing import repository, settling
from app.billing.client import Billing
from app.billing.models import NarrationCharge
from app.core import loops
from app.core.jobs import JOB_FAILED_ERROR_CODE, elapsed_ms
from app.core.loops import Running
from app.observability.context import job_scope
from app.observability.identifiers import new_job_id

logger = logging.getLogger(__name__)

# 몇 초마다 보는가
SETTLE_INTERVAL_SECONDS = 5.0
# 한 바퀴에 맡기는 청구의 수. 밀리면 다음 바퀴에 마저 맡긴다
SETTLE_BATCH = 50
# 로그의 operation. 정해진 이름이다(docs/observability.md)
SETTLE_OPERATION = 'charge.settle'


@dataclass(frozen=True)
class Swept:
    """한 바퀴에 한 일. 돌려줄 것으로 바꾼 청구의 수와, 결제 서버에 맡긴 청구의 수."""

    abandoned: int
    settled: int

    def busy(self) -> bool:
        """한 일이 있었는가."""
        return bool(self.abandoned or self.settled)


@dataclass(frozen=True)
class ChargeSettler:
    """
    끝나지 않은 청구를 마저 끝내는 작업.

    billing 은 부를 때마다 앱에서 꺼낸다. 테스트가 결제 서버를 바꿔 꽂으면 그 뒤부터 바뀐 것을 쓴다.
    """

    session_factory: async_sessionmaker[AsyncSession]
    billing: Callable[[], Billing]
    interval: float = SETTLE_INTERVAL_SECONDS
    clock: Callable[[], datetime] = settling.now_utc

    async def abandon(self, now: datetime) -> int:
        """끝난 테이블의 끝나지 않은 청구를 돌려줄 것으로 바꾼다. 바꾼 수."""
        async with self.session_factory() as session:
            count = await repository.release_abandoned(session, now)
            await session.commit()
            return count

    async def due(self, now: datetime) -> list[NarrationCharge]:
        """부를 차례가 된 청구들. 잠그지 않는다."""
        async with self.session_factory() as session:
            return await repository.find_due(session, now, SETTLE_BATCH)

    async def settle_one(self, charge: NarrationCharge, now: datetime) -> bool:
        """청구 하나를 맡긴다. 맡겼으면 True. 예외가 나면 로그에 남기고 False."""
        try:
            await settling.settle(self.session_factory, self.billing(), charge, now)
        except Exception:
            logger.exception(
                '청구를 정리하지 못했습니다',
                extra={
                    'operation': SETTLE_OPERATION,
                    'charge_id': str(charge.id),
                    'result': 'server_error',
                    'error_code': JOB_FAILED_ERROR_CODE,
                },
            )
            return False
        return True

    async def sweep(self) -> Swept:
        """한 바퀴의 일. 끝난 테이블의 청구를 돌려줄 것으로 바꾸고, 차례가 된 청구를 맡긴다."""
        now = self.clock()
        abandoned = await self.abandon(now)
        settled = 0
        for charge in await self.due(now):
            settled += await self.settle_one(charge, now)
        return Swept(abandoned, settled)

    async def tick(self) -> Swept:
        """
        한 바퀴. 제 job_id 를 걸고 쓸어 담은 뒤, 어떻게 끝났는지 한 줄을 남긴다.

        찾는 일이 통째로 실패하면(DB 가 없다) 예외를 그대로 올린다. 그 줄은 도는 쪽(run)이 남긴다.
        """
        with job_scope(new_job_id()):
            started = time.perf_counter()
            swept = await self.sweep()
            logger.log(
                logging.INFO if swept.busy() else logging.DEBUG,
                '청구 정리가 한 바퀴를 돌았습니다',
                extra={
                    'operation': SETTLE_OPERATION,
                    'abandoned': swept.abandoned,
                    'settled': swept.settled,
                    'duration_ms': elapsed_ms(started),
                    'result': 'success',
                },
            )
            return swept

    async def run(self, stop: asyncio.Event) -> None:
        """stop 이 켜질 때까지 interval 마다 한 바퀴씩 돈다. 한 바퀴가 통째로 실패해도 멈추지 않는다."""
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                logger.exception(
                    '청구 정리가 한 바퀴를 돌지 못했습니다',
                    extra={
                        'operation': SETTLE_OPERATION,
                        'result': 'server_error',
                        'error_code': JOB_FAILED_ERROR_CODE,
                    },
                )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.interval)


def start(settler: ChargeSettler) -> Running:
    """청구 정리를 돌리기 시작한다. 서버가 뜰 때 부른다."""
    return loops.start(settler, 'charge-settler')
