# trpg-server/app/ai_log/retention.py

"""
AI 호출의 기록에 남은 원문(모델이 쓴 글)을 보관 기간이 지나면 비우는 정리 작업(#274).

원문은 서술이 이상하다는 말이 들어왔을 때 무엇을 받았는지 되짚어 보려고 남긴다. 그 뒤에는 필요 없다.
원문에는 플레이어가 쓴 글이 섞인 장면과 GM 만 아는 설정을 따른 글이 들어 있다. 오래 쥐고 있을수록 샐 때 잃는 것이 크다.
  - 보관 기간은 AI_LOG_TEXT_RETENTION_DAYS(기본 30일)다. 외부 AI API 가 남용 감시용 기록을 두는 기간과 비슷하다.
  - 원문만 비운다. 줄과 그 밖의 칸(모델, 토큰 수, 걸린 시간, 결과, 넣은 로어북·지난 일, 보낸 메시지의 지문)은 남긴다.
    모델마다의 실제 원가를 재는 근거다. 지문(HMAC)으로는 보낸 글을 되살릴 수 없다.
  - 게임의 기록(라운드의 장면, 이벤트)은 건드리지 않는다. 그것은 플레이어가 보는 이야기다.
  - 보는 사람: API 로 내보내지 않는다. DB 에 닿는 운영자만 본다.

한 시간마다 한 바퀴 돈다. 한 바퀴에 PRUNE_BATCH 줄씩, 많아야 PRUNE_MAX_BATCHES 번 비운다. 묶음마다 저장한다.
한 번에 몇십만 줄을 고치면 그동안 그 줄들을 잠그고 트랜잭션이 길어진다. 밀린 것은 다음 바퀴에 마저 비운다.
서버가 뜨자마자 첫 바퀴가 돈다. 서버가 여럿이어도 된다. 다른 서버가 잠근 줄은 건너뛴다.

로그는 라운드의 시계와 같은 규칙이다(app/rounds/clock.py). 바퀴마다 job_id 를 걸고, operation 은 ai_log.prune 이다.
비운 것이 없으면 debug, 있으면 info 로 한 줄을 남긴다(cleared: 비운 수).
바퀴마다 작업의 메트릭(background_jobs_*)을 센다(app/observability/metrics.py 의 measured_job).
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai_log import repository
from app.core import loops
from app.core.jobs import JOB_FAILED_ERROR_CODE, elapsed_ms
from app.core.loops import Running
from app.observability.context import job_scope
from app.observability.identifiers import new_job_id
from app.observability.metrics import measured_job
from app.observability.spans import job_span

logger = logging.getLogger(__name__)

# 몇 초마다 보는가
PRUNE_INTERVAL_SECONDS = 60 * 60
# 한 묶음에 비우는 줄의 수
PRUNE_BATCH = 500
# 한 바퀴에 비우는 묶음의 수. 넘게 밀렸으면 다음 바퀴에 마저 비운다
PRUNE_MAX_BATCHES = 20
# 로그의 operation. 정해진 이름이다(docs/observability.md)
PRUNE_OPERATION = 'ai_log.prune'


def now_utc() -> datetime:
    """지금 시각(UTC)."""
    return datetime.now(UTC)


def cutoff(now: datetime, retention_days: int) -> datetime:
    """이 시각보다 먼저 남긴 원문을 비운다."""
    return now - timedelta(days=retention_days)


@dataclass(frozen=True)
class AiLogPruner:
    """보관 기간이 지난 원문을 비우는 정리 작업. 앱에 하나 둔다(app/main.py)."""

    session_factory: async_sessionmaker[AsyncSession]
    retention_days: int
    interval: float = PRUNE_INTERVAL_SECONDS
    clock: Callable[[], datetime] = now_utc

    async def clear_batch(self, before: datetime) -> int:
        """한 묶음을 비우고 저장한다. 비운 수를 돌려준다."""
        async with self.session_factory() as session:
            cleared = await repository.clear_old_texts(session, before, PRUNE_BATCH)
            await session.commit()
            return cleared

    async def sweep(self) -> int:
        """한 바퀴의 일. 묶음이 덜 찰 때까지, 많아야 PRUNE_MAX_BATCHES 번 비운다. 비운 수를 돌려준다."""
        before = cutoff(self.clock(), self.retention_days)
        total = 0
        for _ in range(PRUNE_MAX_BATCHES):
            cleared = await self.clear_batch(before)
            total += cleared
            if cleared < PRUNE_BATCH:
                break
        return total

    async def tick(self) -> int:
        """
        한 바퀴. 제 job_id 를 걸고 비운 뒤, 어떻게 끝났는지 한 줄을 남긴다. 비운 수를 돌려준다.

        비우는 일이 통째로 실패하면(DB 가 없다) 예외를 그대로 올린다. 그 줄은 도는 쪽(run)이 남긴다.
        """
        job_id = new_job_id()
        with job_span(PRUNE_OPERATION, job_id), job_scope(job_id), measured_job(PRUNE_OPERATION):
            started = time.perf_counter()
            cleared = await self.sweep()
            logger.log(
                logging.INFO if cleared else logging.DEBUG,
                'AI 호출 기록의 원문 정리가 한 바퀴를 돌았습니다',
                extra={
                    'operation': PRUNE_OPERATION,
                    'cleared': cleared,
                    'retention_days': self.retention_days,
                    'duration_ms': elapsed_ms(started),
                    'result': 'success',
                },
            )
            return cleared

    async def run(self, stop: asyncio.Event) -> None:
        """stop 이 켜질 때까지 interval 마다 한 바퀴씩 돈다. 한 바퀴가 통째로 실패해도 멈추지 않는다."""
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                logger.exception(
                    'AI 호출 기록의 원문 정리가 한 바퀴를 돌지 못했습니다',
                    extra={'operation': PRUNE_OPERATION, 'result': 'server_error', 'error_code': JOB_FAILED_ERROR_CODE},
                )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.interval)


def start(pruner: AiLogPruner) -> Running:
    """원문 정리를 돌리기 시작한다. 서버가 뜰 때 부른다."""
    return loops.start(pruner, 'ai-log-pruner')
