# notification-server/app/notifications/retention.py

"""
보관 기간이 지난 알림을 지우는 정리 작업(#385).

알림은 지나간 일을 알리는 것이다. 오래 쥐고 있을 까닭이 없고, 쌓이면 알림함과 색인이 커진다.
  - 보관 기간은 NOTIFICATION_RETENTION_DAYS(기본 30일)다. 받은 시각(created_at)부터 센다. 읽었는지는 보지 않는다
  - 원문은 그 일을 맡은 서버에 있다(시나리오, 결제). 알림을 지워도 일 자체의 기록은 남는다

한 시간마다 한 바퀴 돈다. 한 바퀴에 PRUNE_BATCH 줄씩, 많아야 PRUNE_MAX_BATCHES 번 지운다. 묶음마다 저장한다.
한 번에 몇십만 줄을 지우면 그동안 그 줄들을 잠그고 트랜잭션이 길어진다. 밀린 것은 다음 바퀴에 마저 지운다.
서버가 뜨자마자 첫 바퀴가 돈다. 서버가 여럿이어도 된다. 다른 서버가 잠근 줄은 건너뛴다.

게임 서버의 AI 호출 기록 정리(game-server/app/ai/retention.py)와 같은 모양이다.
바퀴마다 job_id 를 걸고, operation 은 notification.prune 이다. 지운 것이 없으면 debug, 있으면 info 로 한 줄을 남긴다.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import loops
from app.core.loops import Running
from app.notifications.models import Notification
from app.observability.context import job_scope
from app.observability.identifiers import new_job_id

logger = logging.getLogger(__name__)

# 몇 초마다 보는가
PRUNE_INTERVAL_SECONDS = 60 * 60
# 한 묶음에 지우는 줄의 수
PRUNE_BATCH = 1000
# 한 바퀴에 지우는 묶음의 수. 넘게 밀렸으면 다음 바퀴에 마저 지운다
PRUNE_MAX_BATCHES = 20
# 로그의 operation 과, 한 바퀴가 통째로 실패했을 때의 error_code(docs/observability.md)
PRUNE_OPERATION = 'notification.prune'
JOB_FAILED_ERROR_CODE = 'job.failed'


def now_utc() -> datetime:
    """지금 시각(UTC)."""
    return datetime.now(UTC)


def cutoff(now: datetime, retention_days: int) -> datetime:
    """이 시각보다 먼저 받은 알림을 지운다."""
    return now - timedelta(days=retention_days)


def elapsed_ms(started: float) -> int:
    """started(time.perf_counter 의 값)부터 지금까지 걸린 밀리초."""
    return round((time.perf_counter() - started) * 1000)


async def delete_older_than(session: AsyncSession, before: datetime, limit: int) -> int:
    """
    before 보다 먼저 받은 알림을 오래된 것부터 limit 개 지운다. 지운 수를 돌려준다.

    고르고(잠그고) 지우는 것을 두 문장으로 나눈다. 한 문장(DELETE … WHERE id IN (SELECT … LIMIT … FOR UPDATE))으로 쓰면
    PostgreSQL 이 안쪽 SELECT 를 바깥 줄마다 다시 돌리는 계획(Nested Loop Semi Join)을 고를 때가 있다.
    그러면 LIMIT 이 지켜지지 않고 묶음보다 많이 지운다(테이블이 작을 때 실제로 그랬다).
    같은 트랜잭션이라 고른 줄의 잠금은 지울 때까지 남는다.
    고를 때 다른 서버가 잠근 줄은 건너뛴다(SKIP LOCKED). 서버가 여럿이어도 같은 줄을 두고 기다리지 않는다.
    색인(ix_notifications_created_at)을 따라 오래된 것부터 찾는다.
    """
    chosen = (
        select(Notification.id)
        .where(Notification.created_at < before)
        .order_by(Notification.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    ids = list(await session.scalars(chosen))
    if not ids:
        return 0
    result = await session.execute(delete(Notification).where(Notification.id.in_(ids)))
    return result.rowcount


@dataclass(frozen=True)
class NotificationPruner:
    """보관 기간이 지난 알림을 지우는 정리 작업. 앱에 하나 둔다(app/main.py)."""

    session_factory: async_sessionmaker[AsyncSession]
    retention_days: int
    interval: float = PRUNE_INTERVAL_SECONDS
    clock: Callable[[], datetime] = now_utc

    async def delete_batch(self, before: datetime) -> int:
        """한 묶음을 지우고 저장한다. 지운 수를 돌려준다."""
        async with self.session_factory() as session:
            deleted = await delete_older_than(session, before, PRUNE_BATCH)
            await session.commit()
            return deleted

    async def sweep(self) -> int:
        """한 바퀴의 일. 묶음이 덜 찰 때까지, 많아야 PRUNE_MAX_BATCHES 번 지운다. 지운 수를 돌려준다."""
        before = cutoff(self.clock(), self.retention_days)
        total = 0
        for _ in range(PRUNE_MAX_BATCHES):
            deleted = await self.delete_batch(before)
            total += deleted
            if deleted < PRUNE_BATCH:
                break
        return total

    async def tick(self) -> int:
        """
        한 바퀴. 제 job_id 를 걸고 지운 뒤, 어떻게 끝났는지 한 줄을 남긴다. 지운 수를 돌려준다.

        지우는 일이 통째로 실패하면(DB 가 없다) 예외를 그대로 올린다. 그 줄은 도는 쪽(run)이 남긴다.
        """
        with job_scope(new_job_id()):
            started = time.perf_counter()
            deleted = await self.sweep()
            logger.log(
                logging.INFO if deleted else logging.DEBUG,
                '보관 기간이 지난 알림을 지웠다',
                extra={
                    'operation': PRUNE_OPERATION,
                    'deleted': deleted,
                    'retention_days': self.retention_days,
                    'duration_ms': elapsed_ms(started),
                    'result': 'success',
                },
            )
            return deleted

    async def run(self, stop: asyncio.Event) -> None:
        """stop 이 켜질 때까지 interval 마다 한 바퀴씩 돈다. 한 바퀴가 통째로 실패해도 멈추지 않는다."""
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                logger.exception(
                    '보관 기간이 지난 알림을 지우지 못했다',
                    extra={'operation': PRUNE_OPERATION, 'result': 'server_error', 'error_code': JOB_FAILED_ERROR_CODE},
                )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.interval)


def start(pruner: NotificationPruner) -> Running:
    """정리 작업을 돌리기 시작한다. 서버가 뜰 때 부른다."""
    return loops.start(pruner, 'notification-pruner')
