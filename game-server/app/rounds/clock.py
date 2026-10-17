# game-server/app/rounds/clock.py

"""
서버의 시계. 마감이 지난 라운드를 몇 초마다 찾아 닫기 시작한다(#57).
크레딧이 모자란 사람을 기다리는 시간이 지난 라운드도 함께 마무리한다(#181, app/rounds/credit_waits.py).
서술을 맡은 작업이 사라진 라운드도 찾아 다시 맡긴다(#275, app/rounds/recovery.py).

라운드는 세 길로 닫힌다. 기다리던 사람이 모두 냈을 때, 방장이 닫을 때, 그리고 마감이 지났을 때.
앞의 둘은 요청이 있어서 그 자리에서 닫는다. 마감은 아무도 요청하지 않아도 지나가므로 서버가 스스로 본다.

서버 안에서 도는 작업 하나다. 따로 띄우는 워커가 없다.
서버가 여럿이면 모두 같은 일을 한다. 같은 라운드를 두 번 닫지 않는 것은 테이블의 잠금이 지킨다.
찾을 때는 잠그지 않고, 닫기 전에 테이블을 잠그고 다시 본다(app/rounds/service.py 의 close_on_time).
먼저 잠근 서버가 닫으면 뒤의 서버는 "이미 닫는 중"을 보고 그냥 지나간다.

한 테이블에서 실패해도 다른 테이블은 닫는다. 실패는 로그에 남기고 다음 바퀴에 다시 본다.
시계는 서버가 뜰 때 시작하고 꺼질 때 멈춘다(app/main.py 의 lifespan). 테스트는 한 바퀴(tick)를 직접 돌린다.

로그는 공통 관측 규격을 따른다(docs/observability.md). 한 바퀴가 작업 하나다. 바퀴마다 job_id 를 새로 걸고,
operation 은 round.close_overdue 다. 요청 밖에서 혼자 시작한 작업이라 추적(trace_id)도 바퀴마다 새로 시작한다.
닫거나 마무리한 것이 없으면 debug, 있으면 info 로 한 줄을 남긴다(주기적으로 도는 워커의 규칙).
줄에 닫은 수(closed), 크레딧 기다리기를 마무리한 수(credit_waits), 사라진 서술을 다시 맡긴 수(recovered),
다시 맡기기를 그만둔 수(gave_up)를 싣는다. 실패는 error 와 job.failed 다.
닫은 라운드의 서술은 따로 맡긴 작업(round.narrate)이 하고, 그 맡긴 줄의 spawned_job_id 로 이어진다.
"""

import asyncio
import contextlib
import logging
import time
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.billing import repository as billing_repository
from app.core import loops
from app.core.jobs import JOB_FAILED_ERROR_CODE, elapsed_ms
from app.core.loops import Running
from app.engine.dice import Dice
from app.observability.context import job_scope
from app.observability.identifiers import new_job_id
from app.rounds import credit_waits, recovery, repository, service
from app.rounds.recovery import Recovery
from app.rounds.service import NarrationScheduler

logger = logging.getLogger(__name__)

# 몇 초마다 보는가. 마감이 지나고 이만큼 안에 닫힌다
CLOCK_INTERVAL_SECONDS = 5.0
# 한 바퀴에 닫는 라운드의 수. 밀리면 다음 바퀴에 마저 닫는다
OVERDUE_BATCH = 50
# 로그의 operation. 정해진 이름이다(docs/observability.md)
CLOCK_OPERATION = 'round.close_overdue'


def now_utc() -> datetime:
    """지금 시각(UTC)."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class RoundClock:
    """
    마감이 지난 라운드를 닫는 시계.

    scheduler 와 dice 는 부를 때마다 앱에서 꺼낸다. 테스트가 서술자나 주사위를 바꿔 꽂으면 그 뒤부터 바뀐 것을 쓴다.
    """

    session_factory: async_sessionmaker[AsyncSession]
    scheduler: Callable[[], NarrationScheduler]
    dice: Callable[[], Dice]
    interval: float = CLOCK_INTERVAL_SECONDS
    clock: Callable[[], datetime] = now_utc

    async def overdue(self, now: datetime) -> list[uuid.UUID]:
        """마감이 지난 라운드의 테이블들. 잠그지 않고 고른다."""
        async with self.session_factory() as session:
            return await repository.find_overdue_table_ids(session, now, OVERDUE_BATCH)

    async def close_one(self, table_id: uuid.UUID, now: datetime) -> bool:
        """한 테이블의 라운드를 닫는다. 닫았으면 True. 실패하면 로그에 남기고 False."""
        try:
            async with self.session_factory() as session:
                return await service.close_on_time(session, table_id, now, self.scheduler(), self.dice())
        except Exception:
            logger.exception(
                '마감이 지난 라운드를 닫지 못했습니다',
                extra={
                    'operation': CLOCK_OPERATION,
                    'table_id': str(table_id),
                    'result': 'server_error',
                    'error_code': JOB_FAILED_ERROR_CODE,
                },
            )
            return False

    async def sweep(self) -> int:
        """마감이 지난 라운드를 찾아 하나씩 닫는다. 닫은 수를 돌려준다."""
        now = self.clock()
        closed = 0
        for table_id in await self.overdue(now):
            closed += await self.close_one(table_id, now)
        return closed

    async def waiting(self, now: datetime) -> list[uuid.UUID]:
        """크레딧이 모자란 사람을 기다리는 시간이 지난 라운드의 테이블들. 잠그지 않고 고른다."""
        async with self.session_factory() as session:
            return await billing_repository.find_waiting_table_ids(
                session, now, credit_waits.WAITED_FOR, credit_waits.PAYABLE, OVERDUE_BATCH
            )

    async def settle_wait(self, table_id: uuid.UUID, now: datetime) -> bool:
        """한 테이블의 크레딧 기다리기를 마무리한다. 했으면 True. 실패하면 로그에 남기고 False."""
        try:
            async with self.session_factory() as session:
                return await credit_waits.settle_credit_wait(session, table_id, now, self.scheduler())
        except Exception:
            logger.exception(
                '크레딧을 기다리는 라운드를 마무리하지 못했습니다',
                extra={
                    'operation': CLOCK_OPERATION,
                    'table_id': str(table_id),
                    'result': 'server_error',
                    'error_code': JOB_FAILED_ERROR_CODE,
                },
            )
            return False

    async def sweep_waits(self) -> int:
        """크레딧을 기다리는 시간이 지난 라운드를 찾아 하나씩 마무리한다. 마무리한 수를 돌려준다."""
        now = self.clock()
        settled = 0
        for table_id in await self.waiting(now):
            settled += await self.settle_wait(table_id, now)
        return settled

    async def vanished(self, now: datetime) -> list[uuid.UUID]:
        """서술을 맡은 작업이 사라진 것으로 보이는 라운드의 테이블들. 잠그지 않고 고른다."""
        async with self.session_factory() as session:
            return await repository.find_vanished_table_ids(session, recovery.vanished_before(now), OVERDUE_BATCH)

    async def recover_one(self, table_id: uuid.UUID, now: datetime) -> Recovery:
        """한 테이블의 사라진 서술을 다시 맡기거나 그만둔다. 실패하면 로그에 남기고 NOTHING."""
        try:
            async with self.session_factory() as session:
                return await recovery.recover(session, table_id, now, self.scheduler())
        except Exception:
            logger.exception(
                '서술이 사라진 라운드를 다시 맡기지 못했습니다',
                extra={
                    'operation': CLOCK_OPERATION,
                    'table_id': str(table_id),
                    'result': 'server_error',
                    'error_code': JOB_FAILED_ERROR_CODE,
                },
            )
            return Recovery.NOTHING

    async def sweep_vanished(self) -> Counter[Recovery]:
        """서술을 맡은 작업이 사라진 라운드를 찾아 하나씩 다시 맡긴다. 한 일마다의 수를 돌려준다."""
        now = self.clock()
        done: Counter[Recovery] = Counter()
        for table_id in await self.vanished(now):
            done[await self.recover_one(table_id, now)] += 1
        return done

    async def tick(self) -> int:
        """
        한 바퀴. 제 job_id 를 걸고 쓸어 담은 뒤, 어떻게 끝났는지 한 줄을 남긴다. 닫은 수를 돌려준다.
        서술이 사라진 라운드를 다시 맡긴 뒤, 마감이 지난 라운드를 닫고 크레딧을 기다리는 라운드를 마무리한다.
        사라진 것을 먼저 본다. 이 바퀴에 새로 맡긴 서술을 같은 바퀴에서 견주지 않는다.

        찾는 일이 통째로 실패하면(DB 가 없다) 예외를 그대로 올린다. 그 줄은 도는 쪽(run)이 남긴다.
        """
        with job_scope(new_job_id()):
            started = time.perf_counter()
            recovered = await self.sweep_vanished()
            closed = await self.sweep()
            settled = await self.sweep_waits()
            busy = closed or settled or recovered[Recovery.RETRIED] or recovered[Recovery.GAVE_UP]
            logger.log(
                logging.INFO if busy else logging.DEBUG,
                '시계가 한 바퀴를 돌았습니다',
                extra={
                    'operation': CLOCK_OPERATION,
                    'closed': closed,
                    'credit_waits': settled,
                    'recovered': recovered[Recovery.RETRIED],
                    'gave_up': recovered[Recovery.GAVE_UP],
                    'duration_ms': elapsed_ms(started),
                    'result': 'success',
                },
            )
            return closed

    async def run(self, stop: asyncio.Event) -> None:
        """stop 이 켜질 때까지 interval 마다 한 바퀴씩 돈다. 한 바퀴가 통째로 실패해도 멈추지 않는다."""
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                logger.exception(
                    '라운드의 시계가 한 바퀴를 돌지 못했습니다',
                    extra={'operation': CLOCK_OPERATION, 'result': 'server_error', 'error_code': JOB_FAILED_ERROR_CODE},
                )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.interval)


def start(clock: RoundClock) -> Running:
    """시계를 돌리기 시작한다. 서버가 뜰 때 부른다."""
    return loops.start(clock, 'round-clock')
