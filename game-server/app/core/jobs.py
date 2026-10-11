# game-server/app/core/jobs.py

"""
요청과 따로 도는 작업. 요청이 "접수했다"고 바로 답하고, 오래 걸리는 일은 뒤에서 한다.

지금 여기서 도는 것은 GM 의 서술이다(app/rounds/closing.py). AI 를 부르면 몇 초에서 십몇 초가 걸린다.
그동안 요청을 붙잡아 두면, 연결이 끊길 때 서술이 중간에 취소되고 프록시의 제한 시간에도 걸린다.

작업은 이 서버 프로세스 안에서 돈다. 따로 띄우는 워커나 큐가 없다.
그래서 서버가 죽으면 돌던 작업도 사라진다. 작업을 맡기는 쪽은 "하다 말았을 때 다시 시작할 길"을 따로 둬야 한다.

작업마다 식별자(job_id)를 하나 준다. 작업이 남기는 로그는 그 식별자로 묶인다.
작업은 맡긴 요청이 끝난 뒤에도 돌므로, 요청의 식별자(request_id)가 아니라 제 식별자를 쓴다.
"""

import asyncio
import logging
import time
from collections.abc import Coroutine

from app.observability.context import job_scope
from app.observability.identifiers import new_job_id

logger = logging.getLogger(__name__)

# 서버가 꺼질 때 돌던 작업이 끝나기를 기다리는 시간(초). 지나면 취소한다
SHUTDOWN_GRACE_SECONDS = 10.0
# 무슨 일인지 적지 않고 맡긴 작업의 이름. 로그의 operation 칸에 들어간다
DEFAULT_OPERATION = 'job.run'
# 실패한 작업의 오류 코드
JOB_FAILED_ERROR_CODE = 'job.failed'


def elapsed_ms(started: float) -> int:
    """started(time.perf_counter 의 값)부터 지금까지 걸린 시간(밀리초)."""
    return round((time.perf_counter() - started) * 1000)


async def run_tracked(job: Coroutine, name: str, operation: str, job_id: str) -> None:
    """
    작업을 돌리고, 끝나면 어떻게 끝났는지 한 줄을 남긴다. 규격은 docs/observability.md 에 있다.

    도는 동안 작업의 식별자(job_id)를 건다. 작업 안에서 남기는 모든 로그에 그 식별자가 붙는다.
    뒤에서 도는 작업의 예외는 받아 줄 요청이 없다. 여기서 적지 않으면 아무도 모른 채 사라진다.
    예외는 적은 뒤에 그대로 올린다. 취소도 그대로 올린다.
    """
    with job_scope(job_id):
        started = time.perf_counter()
        fields = {'operation': operation, 'job_name': name}
        try:
            await job
        except asyncio.CancelledError:
            logger.warning(
                '뒤에서 돌던 작업이 취소됐습니다: %s',
                name,
                extra={**fields, 'duration_ms': elapsed_ms(started), 'result': 'cancelled'},
            )
            raise
        except Exception:
            logger.error(
                '뒤에서 돌던 작업이 실패했습니다: %s',
                name,
                exc_info=True,
                extra={
                    **fields,
                    'duration_ms': elapsed_ms(started),
                    'result': 'server_error',
                    'error_code': JOB_FAILED_ERROR_CODE,
                },
            )
            raise
        logger.info(
            '뒤에서 돌던 작업이 끝났습니다: %s',
            name,
            extra={**fields, 'duration_ms': elapsed_ms(started), 'result': 'success'},
        )


class BackgroundJobs:
    """돌고 있는 작업들을 들고 있다. 앱에 하나만 둔다."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()

    def spawn(self, job: Coroutine, name: str, operation: str = DEFAULT_OPERATION) -> str:
        """
        작업을 시작하고 바로 돌아온다. 끝나기를 기다리지 않는다. 작업의 식별자(job_id)를 돌려준다.

        name 은 이 작업 하나의 이름이다(narrate:테이블:3). operation 은 무슨 종류의 일인지다(round.narrate).
        operation 에는 ID 처럼 작업마다 달라지는 값을 넣지 않는다. 같은 종류의 작업을 묶어 세는 데 쓴다.

        맡긴 사실을 한 줄 남긴다. 그 줄에 맡긴 쪽의 식별자(요청이면 request_id)와 맡긴 작업의 식별자
        (spawned_job_id)가 함께 있다. 요청의 기록에서 작업의 기록으로 넘어가는 고리다.

        작업을 집합에 담아 둔다. asyncio 는 작업을 약하게만 붙잡고 있어서,
        아무도 들고 있지 않으면 도는 도중에 치워질 수 있다.
        """
        job_id = new_job_id()
        logger.info(
            '작업을 뒤에 맡겼습니다: %s',
            name,
            extra={'operation': operation, 'job_name': name, 'spawned_job_id': job_id},
        )
        task = asyncio.create_task(run_tracked(job, name, operation, job_id), name=name)
        self._tasks.add(task)
        task.add_done_callback(self._finished)
        return job_id

    def _finished(self, task: asyncio.Task) -> None:
        """
        작업이 끝났을 때 불린다. 집합에서 뺀다.

        실패는 작업 안에서 이미 적었다(run_tracked). 여기서는 예외를 꺼내 보기만 한다.
        아무도 꺼내 보지 않은 예외는 asyncio 가 "받지 않은 예외"라고 따로 경고한다.
        """
        self._tasks.discard(task)
        if not task.cancelled():
            task.exception()

    def count(self) -> int:
        """지금 돌고 있는 작업의 수."""
        return len(self._tasks)

    async def drain(self) -> None:
        """
        지금 돌고 있는 작업이 모두 끝날 때까지 기다린다. 기다리는 동안 새로 시작된 것도 기다린다.

        테스트가 "작업이 끝난 뒤의 상태"를 보려고 쓴다. 작업이 실패했어도 예외를 올리지 않는다.
        """
        while self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def aclose(self, grace: float = SHUTDOWN_GRACE_SECONDS) -> None:
        """
        서버가 꺼질 때 부른다. 돌던 작업이 끝나기를 잠깐 기다리고, 그래도 남은 것은 취소한다.

        취소된 작업이 하던 일은 끝나지 않은 채로 남는다. 다시 시작하는 것은 그 일을 맡긴 쪽의 몫이다.
        """
        if not self._tasks:
            return
        _, pending = await asyncio.wait(self._tasks, timeout=grace)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
