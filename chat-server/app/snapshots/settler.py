# chat-server/app/snapshots/settler.py

"""
장면 그림의 청구 정리(#983). 몇 초마다 끝나지 않은 청구를 찾아 결제 서버에 마저 맡긴다.
말 한 번의 청구 정리(app/turns/settler.py)와 같은 일을 snapshots 의 줄에 한다.

  - 확정할 것, 돌려줄 것: 한 장이 끝나면 바로 맡기지만, 그때 못 했으면 여기서 마저 한다(5초, 10초 … 5분)
  - 그리는 도중에 오래 남은 것(pending, held 인 채로 SNAPSHOT_STALE 이 지났다): 서버가 꺼진 것이다.
    실패로 적고 돌려준다. 그러면 그 대화에서 다시 그릴 수 있다(그리는 중인 것은 하나다)
서버가 여럿이면 모두 같은 일을 한다. 결제 서버는 같은 이름표를 한 번만 처리하고, 기록은 "지금 이 상태일 때만" 옮긴다.
"""

import asyncio
import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from server_core import loops
from server_core.loops import Running
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.billing.client import Billing
from app.core.dependencies import utc_now
from app.snapshots import repository, service
from app.snapshots.models import Snapshot, SnapshotOutcome
from app.turns.models import DUE_STATUSES, OPEN_STATUSES, BillingStatus

logger = logging.getLogger(__name__)

# 몇 초마다 보는가
SETTLE_INTERVAL_SECONDS = 5.0
# 한 바퀴에 맡기는 청구의 수
SETTLE_BATCH = 50
# 로그의 operation
SETTLE_OPERATION = 'snapshot.settle'
# 도중에 오래 남은 것의 까닭
ABANDONED = 'abandoned'


@dataclass(frozen=True)
class SnapshotSettler:
    """끝나지 않은 장면 그림의 청구를 마저 끝내는 작업. billing 은 부를 때마다 앱에서 꺼낸다."""

    session_factory: async_sessionmaker[AsyncSession]
    billing: Callable[[], Billing]
    interval: float = SETTLE_INTERVAL_SECONDS
    clock: Callable[[], datetime] = utc_now

    async def due(self, now: datetime) -> list[Snapshot]:
        """맡길 차례가 된 청구들."""
        async with self.session_factory() as session:
            return await repository.find_due(session, now, service.SNAPSHOT_STALE, SETTLE_BATCH)

    async def abandon(self, snapshot: Snapshot, now: datetime) -> Snapshot | None:
        """도중에 오래 남은 것을 실패로 적고 돌려줄 것으로 바꾼다. 그사이 끝났으면 None."""
        values = {
            'billing_status': BillingStatus.RELEASE_DUE,
            'outcome': SnapshotOutcome.FAILED,
            'error_code': ABANDONED,
            'finished_at': now,
        }
        async with self.session_factory() as session:
            moved = await repository.move_billing(session, snapshot.id, OPEN_STATUSES, values)
            await session.commit()
            return await repository.get(session, snapshot.id) if moved else None

    async def settle_one(self, snapshot: Snapshot, now: datetime) -> bool:
        """하나를 맡긴다. 맡겼으면 True. 예외가 나면 로그에 남기고 False."""
        try:
            if snapshot.billing_status in OPEN_STATUSES:
                snapshot = await self.abandon(snapshot, now)
            if snapshot is None or snapshot.billing_status not in DUE_STATUSES:
                return False
            await service.settle_snapshot(self.session_factory, self.billing(), snapshot, now)
        except Exception:
            logger.exception(
                '장면 그림의 청구를 정리하지 못했습니다',
                extra={'operation': SETTLE_OPERATION, 'snapshot_id': str(snapshot.id), 'result': 'server_error'},
            )
            return False
        return True

    async def tick(self) -> int:
        """한 바퀴. 차례가 된 청구를 맡기고 맡긴 수를 돌려준다."""
        now = self.clock()
        settled = 0
        for snapshot in await self.due(now):
            settled += await self.settle_one(snapshot, now)
        if settled:
            logger.info(
                '장면 그림의 청구 정리가 한 바퀴를 돌았습니다',
                extra={'operation': SETTLE_OPERATION, 'settled': settled, 'result': 'success'},
            )
        return settled

    async def run(self, stop: asyncio.Event) -> None:
        """stop 이 켜질 때까지 interval 마다 한 바퀴씩 돈다. 한 바퀴가 통째로 실패해도 멈추지 않는다."""
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                logger.exception(
                    '장면 그림의 청구 정리가 한 바퀴를 돌지 못했습니다',
                    extra={'operation': SETTLE_OPERATION, 'result': 'server_error'},
                )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.interval)


def start(settler: SnapshotSettler) -> Running:
    """청구 정리를 돌리기 시작한다. 서버가 뜰 때 부른다."""
    return loops.start(settler, 'snapshot-settler')
