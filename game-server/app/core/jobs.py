# game-server/app/core/jobs.py

"""
요청과 따로 도는 작업. 요청이 "접수했다"고 바로 답하고, 오래 걸리는 일은 뒤에서 한다.

지금 여기서 도는 것은 GM 의 서술이다(app/rounds/closing.py). AI 를 부르면 몇 초에서 십몇 초가 걸린다.
그동안 요청을 붙잡아 두면, 연결이 끊길 때 서술이 중간에 취소되고 프록시의 제한 시간에도 걸린다.

작업은 이 서버 프로세스 안에서 돈다. 따로 띄우는 워커나 큐가 없다.
그래서 서버가 죽으면 돌던 작업도 사라진다. 작업을 맡기는 쪽은 "하다 말았을 때 다시 시작할 길"을 따로 둬야 한다.
"""

import asyncio
import logging
from collections.abc import Coroutine

logger = logging.getLogger(__name__)

# 서버가 꺼질 때 돌던 작업이 끝나기를 기다리는 시간(초). 지나면 취소한다
SHUTDOWN_GRACE_SECONDS = 10.0


class BackgroundJobs:
    """돌고 있는 작업들을 들고 있다. 앱에 하나만 둔다."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()

    def spawn(self, job: Coroutine, name: str) -> None:
        """
        작업을 시작하고 바로 돌아온다. 끝나기를 기다리지 않는다.

        작업을 집합에 담아 둔다. asyncio 는 작업을 약하게만 붙잡고 있어서,
        아무도 들고 있지 않으면 도는 도중에 치워질 수 있다.
        """
        task = asyncio.create_task(job, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._finished)

    def _finished(self, task: asyncio.Task) -> None:
        """
        작업이 끝났을 때 불린다. 집합에서 빼고, 실패했으면 로그에 남긴다.

        뒤에서 도는 작업의 예외는 받아 줄 요청이 없다. 여기서 적지 않으면 아무도 모른 채 사라진다.
        로그에는 작업의 이름과 예외만 적는다.
        """
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error('뒤에서 돌던 작업이 실패했습니다: %s', task.get_name(), exc_info=task.exception())

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
