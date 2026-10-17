# game-server/app/core/jobs.py

"""
요청과 따로 도는 작업. 요청이 "접수했다"고 바로 답하고, 오래 걸리는 일은 뒤에서 한다.

지금 여기서 도는 것은 GM 의 서술이다(app/rounds/closing.py). AI 를 부르면 몇 초에서 십몇 초가 걸린다.
그동안 요청을 붙잡아 두면, 연결이 끊길 때 서술이 중간에 취소되고 프록시의 제한 시간에도 걸린다.

작업은 이 서버 프로세스 안에서 돈다. 따로 띄우는 워커나 큐가 없다.
그래서 서버가 죽으면 돌던 작업도 사라진다. 작업을 맡기는 쪽은 "하다 말았을 때 다시 시작할 길"을 따로 둬야 한다.
서술은 라운드가 DB 에 "닫는 중"으로 남아 있으므로 서버의 시계가 찾아 다시 맡긴다(app/rounds/recovery.py).
색인은 다음에 검색할 때 벡터가 모자란 것을 보고 다시 맡긴다.

작업의 종류(operation)마다 한도(Limit)가 있다(#275).
  - 동시에 도는 수(concurrency). 넘으면 맡기는 하되 차례를 기다린다. 서술이 몰려도 모델을 한꺼번에 부르지 않는다.
    종류마다 따로 센다. 색인이 몰려도 사람이 기다리는 서술의 차례를 빼앗지 못한다.
  - 돌거나 기다리는 수의 상한(capacity). 넘으면 맡지 않는다(refused). 기다리는 줄이 끝없이 길어지지 않는다.
    맡지 않은 일은 위의 "다시 시작할 길"이 다시 맡긴다. 그래서 거절해도 일이 사라지지 않는다.
같은 이름의 작업이 이미 돌거나 기다리면 맡지 않는 길(spawn_once)도 있다. 같은 판의 색인을 겹쳐 돌리지 않는다.

작업마다 식별자(job_id)를 하나 준다. 작업이 남기는 로그는 그 식별자로 묶인다.
작업은 맡긴 요청이 끝난 뒤에도 돌므로, 요청의 식별자(request_id)가 아니라 제 식별자를 쓴다.
"""

import asyncio
import logging
import time
from collections.abc import Coroutine, Mapping
from dataclasses import dataclass

from app.observability.context import job_scope
from app.observability.identifiers import new_job_id

logger = logging.getLogger(__name__)

# 서버가 꺼질 때 돌던 작업이 끝나기를 기다리는 시간(초). 지나면 취소한다
SHUTDOWN_GRACE_SECONDS = 10.0
# 무슨 일인지 적지 않고 맡긴 작업의 이름. 로그의 operation 칸에 들어간다
DEFAULT_OPERATION = 'job.run'
# 실패한 작업의 오류 코드
JOB_FAILED_ERROR_CODE = 'job.failed'
# 자리가 다 차서 맡지 않은 작업의 오류 코드
JOB_REFUSED_ERROR_CODE = 'job.refused'


@dataclass(frozen=True)
class Limit:
    """작업 한 종류(operation)의 한도."""

    # 동시에 도는 수. 넘으면 차례를 기다린다
    concurrency: int
    # 돌거나 기다리는 수의 상한. 넘으면 맡지 않는다
    capacity: int

    def __post_init__(self) -> None:
        if self.concurrency < 1:
            raise ValueError('동시에 도는 수는 1 이상이어야 합니다')
        if self.capacity < self.concurrency:
            raise ValueError('돌거나 기다리는 수의 상한은 동시에 도는 수보다 작을 수 없습니다')


# 한도를 따로 정하지 않은 종류의 한도
DEFAULT_LIMIT = Limit(concurrency=8, capacity=100)


def elapsed_ms(started: float) -> int:
    """started(time.perf_counter 의 값)부터 지금까지 걸린 시간(밀리초)."""
    return round((time.perf_counter() - started) * 1000)


async def wait_turn(gate: asyncio.Semaphore, job: Coroutine, name: str, fields: dict, queued: float) -> None:
    """
    이 종류의 작업이 돌 차례를 기다린다.

    기다리다 취소되면(서버가 꺼진다) 한 줄을 남기고, 시작하지 못한 작업을 닫고, 취소를 그대로 올린다.
    닫지 않으면 asyncio 가 "한 번도 기다리지 않은 코루틴"이라고 따로 경고한다.
    """
    try:
        await gate.acquire()
    except asyncio.CancelledError:
        job.close()
        logger.warning(
            '차례를 기다리던 작업이 취소됐습니다: %s',
            name,
            extra={**fields, 'queue_ms': elapsed_ms(queued), 'result': 'cancelled'},
        )
        raise


async def run_tracked(job: Coroutine, name: str, operation: str, job_id: str, gate: asyncio.Semaphore) -> None:
    """
    차례를 기다렸다가 작업을 돌린다. 규격은 docs/observability.md 에 있다.

    gate 는 이 종류의 작업이 동시에 도는 수를 세는 문이다. 끝나면(실패해도, 취소돼도) 문을 연다.
    기다린 시간(queue_ms)과 돈 시간(duration_ms)을 따로 적는다. 서술이 늦을 때 모델이 느린지 줄이 긴지 가른다.

    기다리는 동안에도 작업의 식별자(job_id)를 건다. 작업 안에서 남기는 모든 로그에 그 식별자가 붙는다.
    """
    with job_scope(job_id):
        queued = time.perf_counter()
        fields = {'operation': operation, 'job_name': name}
        await wait_turn(gate, job, name, fields, queued)
        try:
            await run_logged(job, name, {**fields, 'queue_ms': elapsed_ms(queued)})
        finally:
            gate.release()


async def run_logged(job: Coroutine, name: str, fields: dict) -> None:
    """
    작업을 돌리고, 끝나면 어떻게 끝났는지 한 줄을 남긴다.

    뒤에서 도는 작업의 예외는 받아 줄 요청이 없다. 여기서 적지 않으면 아무도 모른 채 사라진다.
    예외는 적은 뒤에 그대로 올린다. 취소도 그대로 올린다.
    """
    started = time.perf_counter()
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


@dataclass(frozen=True)
class Spawned:
    """맡은 작업 하나의 이름과 종류. 같은 이름을 겹쳐 맡지 않고, 종류마다 센다."""

    name: str
    operation: str


class BackgroundJobs:
    """
    돌고 있는 작업들을 들고 있다. 앱에 하나만 둔다.

    limits 는 종류(operation)마다의 한도다. 적지 않은 종류는 default 를 쓴다.
    """

    def __init__(self, limits: Mapping[str, Limit] | None = None, default: Limit = DEFAULT_LIMIT) -> None:
        self._tasks: dict[asyncio.Task, Spawned] = {}
        self._limits = dict(limits or {})
        self._default = default
        self._gates: dict[str, asyncio.Semaphore] = {}

    def limit_of(self, operation: str) -> Limit:
        """이 종류의 한도."""
        return self._limits.get(operation, self._default)

    def gate_of(self, operation: str) -> asyncio.Semaphore:
        """이 종류의 작업이 동시에 도는 수를 세는 문. 처음 맡길 때 만든다."""
        if operation not in self._gates:
            self._gates[operation] = asyncio.Semaphore(self.limit_of(operation).concurrency)
        return self._gates[operation]

    def is_full(self, operation: str) -> bool:
        """이 종류의 작업이 돌거나 기다리는 수가 상한에 닿았나."""
        return self.count(operation) >= self.limit_of(operation).capacity

    def is_running(self, name: str) -> bool:
        """이 이름의 작업이 돌거나 기다리고 있나."""
        return any(running.name == name for running in self._tasks.values())

    def spawn(self, job: Coroutine, name: str, operation: str = DEFAULT_OPERATION) -> str | None:
        """
        작업을 맡기고 바로 돌아온다. 끝나기를 기다리지 않는다. 작업의 식별자(job_id)를 돌려준다.

        name 은 이 작업 하나의 이름이다(narrate:테이블:3). operation 은 무슨 종류의 일인지다(round.narrate).
        operation 에는 ID 처럼 작업마다 달라지는 값을 넣지 않는다. 같은 종류의 작업을 묶어 세는 데 쓴다.

        이 종류가 상한에 닿았으면 맡지 않고 None 을 돌려준다(refuse). 맡긴 쪽은 다시 맡길 길을 따로 가진다.
        """
        if self.is_full(operation):
            self.refuse(job, name, operation)
            return None
        return self.start(job, name, operation)

    def spawn_once(self, job: Coroutine, name: str, operation: str = DEFAULT_OPERATION) -> str | None:
        """
        같은 이름의 작업이 돌거나 기다리지 않을 때만 맡긴다. 이미 있으면 맡지 않고 None 을 돌려준다.

        같은 일을 두 번 하면 결과는 같고 값(모델 호출)만 두 번 드는 작업에 쓴다(색인).
        """
        if self.is_running(name):
            job.close()
            logger.debug(
                '같은 작업이 이미 있어 맡지 않았습니다: %s', name, extra={'operation': operation, 'job_name': name}
            )
            return None
        return self.spawn(job, name, operation)

    def refuse(self, job: Coroutine, name: str, operation: str) -> None:
        """맡지 않는다. 작업을 닫고 한 줄을 남긴다. 사람이 볼 일이라 warning 이다."""
        job.close()
        logger.warning(
            '작업의 자리가 다 차서 맡지 않았습니다: %s',
            name,
            extra={
                'operation': operation,
                'job_name': name,
                'capacity': self.limit_of(operation).capacity,
                'error_code': JOB_REFUSED_ERROR_CODE,
            },
        )

    def start(self, job: Coroutine, name: str, operation: str) -> str:
        """
        작업을 시작한다. 작업의 식별자를 돌려준다.

        맡긴 사실을 한 줄 남긴다. 그 줄에 맡긴 쪽의 식별자(요청이면 request_id)와 맡긴 작업의 식별자
        (spawned_job_id)가 함께 있다. 요청의 기록에서 작업의 기록으로 넘어가는 고리다.

        작업을 들고 있는다. asyncio 는 작업을 약하게만 붙잡고 있어서,
        아무도 들고 있지 않으면 도는 도중에 치워질 수 있다.
        """
        job_id = new_job_id()
        logger.info(
            '작업을 뒤에 맡겼습니다: %s',
            name,
            extra={'operation': operation, 'job_name': name, 'spawned_job_id': job_id},
        )
        tracked = run_tracked(job, name, operation, job_id, self.gate_of(operation))
        task = asyncio.create_task(tracked, name=name)
        self._tasks[task] = Spawned(name, operation)
        task.add_done_callback(self._finished)
        return job_id

    def _finished(self, task: asyncio.Task) -> None:
        """
        작업이 끝났을 때 불린다. 집합에서 뺀다.

        실패는 작업 안에서 이미 적었다(run_tracked). 여기서는 예외를 꺼내 보기만 한다.
        아무도 꺼내 보지 않은 예외는 asyncio 가 "받지 않은 예외"라고 따로 경고한다.
        """
        self._tasks.pop(task, None)
        if not task.cancelled():
            task.exception()

    def count(self, operation: str | None = None) -> int:
        """돌거나 기다리는 작업의 수. operation 을 주면 그 종류만 센다."""
        if operation is None:
            return len(self._tasks)
        return sum(1 for running in self._tasks.values() if running.operation == operation)

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
