# story-server/app/turns/settler.py

"""
청구 정리. 몇 초마다 끝나지 않은 청구를 찾아 결제 서버에 마저 맡긴다.
chat 서버의 것(chat-server/app/turns/settler.py)과 같다.

맡기는 것은 둘이다.
  - 확정할 것, 돌려줄 것: 말 한 번이 끝나면 바로 맡기지만, 그때 못 했으면(결제 서버가 잠깐 죽었다) 여기서 마저 한다.
    맡기지 못할수록 늦게 다시 부른다(5초, 10초 … 5분, app/turns/charging.py 의 retry_delay).
  - 도중에 오래 남은 것(pending, held 인 채로 GENERATION_STALE 이 지났다): 서버가 말 한 번의 도중에 꺼진 것이다.
    돌려줄 것으로 바꾸고 돌려준다. 걸린 적 없는 홀드를 돌려주는 것도 결제 서버는 된 것으로 답한다(404).
    결제 서버도 story 서버의 홀드를 CHAT_HOLD_TTL(10분) 뒤에 스스로 돌려준다. 이것은 기록을 맞추는 일이다.

서버가 여럿이면 모두 같은 일을 한다. 같은 청구를 둘이 맡겨도 된다.
결제 서버는 같은 이름표를 한 번만 처리하고,
기록은 "지금 이 상태일 때만" 옮긴다(app/turns/repository.py 의 move_billing).
바퀴마다 job_id 를 걸고 작업의 메트릭(background_jobs_*)을 센다. 한 일이 없으면 debug, 있으면 info 로 한 줄을 남긴다.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from server_core import loops
from server_core.loops import Running
from server_core.observability.context import job_scope
from server_core.observability.identifiers import new_job_id
from server_core.observability.metrics import measured_job
from server_core.observability.spans import JOB_FAILED_ERROR_CODE, add_handled, job_span
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.billing.client import Billing
from app.core.dependencies import utc_now
from app.turns import repository, service
from app.turns.models import DUE_STATUSES, OPEN_STATUSES, BillingStatus, Generation, Outcome

logger = logging.getLogger(__name__)

# 몇 초마다 보는가
SETTLE_INTERVAL_SECONDS = 5.0
# 한 바퀴에 맡기는 청구의 수. 밀리면 다음 바퀴에 마저 맡긴다
SETTLE_BATCH = 50
# 로그의 operation. 게임 서버의 청구 정리와 같은 이름이다(docs/observability.md)
SETTLE_OPERATION = 'charge.settle'
# 도중에 오래 남은 청구의 까닭
ABANDONED = 'abandoned'


def elapsed_ms(started: float) -> int:
    """started(time.perf_counter) 부터 지금까지의 밀리초."""
    return int((time.perf_counter() - started) * 1000)


@dataclass(frozen=True)
class ChargeSettler:
    """
    끝나지 않은 청구를 마저 끝내는 작업.

    billing 은 부를 때마다 앱에서 꺼낸다. 테스트가 결제 서버를 바꿔 꽂으면 그 뒤부터 바뀐 것을 쓴다.
    """

    session_factory: async_sessionmaker[AsyncSession]
    billing: Callable[[], Billing]
    interval: float = SETTLE_INTERVAL_SECONDS
    clock: Callable[[], datetime] = utc_now

    async def due(self, now: datetime) -> list[Generation]:
        """맡길 차례가 된 청구들. 잠그지 않는다."""
        async with self.session_factory() as session:
            return await repository.find_due(session, now, service.GENERATION_STALE, SETTLE_BATCH)

    async def abandon(self, generation: Generation, now: datetime) -> Generation | None:
        """도중에 오래 남은 청구를 돌려줄 것으로 바꾼다. 그사이에 끝났으면 None."""
        values = {
            'billing_status': BillingStatus.RELEASE_DUE,
            'outcome': Outcome.FAILED,
            'error_code': ABANDONED,
            'finished_at': now,
        }
        async with self.session_factory() as session:
            moved = await repository.move_billing(session, generation.id, OPEN_STATUSES, values)
            await session.commit()
            return await repository.get_generation(session, generation.id) if moved else None

    async def settle_one(self, generation: Generation, now: datetime) -> bool:
        """청구 하나를 맡긴다. 맡겼으면 True. 예외가 나면 로그에 남기고 False."""
        try:
            if generation.billing_status in OPEN_STATUSES:
                generation = await self.abandon(generation, now)
            if generation is None or generation.billing_status not in DUE_STATUSES:
                return False
            await service.settle_generation(self.session_factory, self.billing(), generation, now)
        except Exception:
            logger.exception(
                '청구를 정리하지 못했습니다',
                extra={
                    'operation': SETTLE_OPERATION,
                    'generation_id': str(generation.id),
                    'result': 'server_error',
                    'error_code': JOB_FAILED_ERROR_CODE,
                },
            )
            return False
        return True

    async def sweep(self) -> int:
        """한 바퀴의 일. 차례가 된 청구를 맡기고, 맡긴 수를 돌려준다."""
        now = self.clock()
        generations = await self.due(now)
        add_handled(len(generations))
        settled = 0
        for generation in generations:
            settled += await self.settle_one(generation, now)
        return settled

    async def tick(self) -> int:
        """한 바퀴. 제 job_id 를 걸고 쓸어 담은 뒤 한 줄을 남긴다. 찾는 일이 통째로 실패하면 그대로 올린다."""
        job_id = new_job_id()
        with job_span(SETTLE_OPERATION, job_id), job_scope(job_id), measured_job(SETTLE_OPERATION):
            started = time.perf_counter()
            settled = await self.sweep()
            logger.log(
                logging.INFO if settled else logging.DEBUG,
                '청구 정리가 한 바퀴를 돌았습니다',
                extra={
                    'operation': SETTLE_OPERATION,
                    'settled': settled,
                    'duration_ms': elapsed_ms(started),
                    'result': 'success',
                },
            )
            return settled

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
