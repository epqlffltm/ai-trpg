# game-server/tests/streaming.py

"""
스트림을 받는 테스트가 함께 쓰는 도구. 브라우저 노릇을 하는 Reader 가 여기 있다.

스트림을 여는 fixture(connect)는 tests/conftest.py 에 있다.
"""

import asyncio
from collections.abc import AsyncIterator

from app.realtime.sse import Comment, Frame

# 신호로 온 것이라면 이 시간(초) 안에 온다
SOON = 2.0
# 오지 않는 것을 확인할 때 기다리는 시간(초)
QUIET = 0.3
# 스트림이 스스로 깨어나는 간격(초). 길게 잡는다.
# 이 시간보다 빨리 왔다면 주기적으로 읽어서가 아니라 신호를 받아서 온 것이다
LONG_HEARTBEAT = 60.0


class Reader:
    """
    스트림을 받는 쪽. 브라우저 노릇을 한다.

    스트림을 뒤에서 계속 돌리며 나온 것을 줄 세워 둔다. 테스트는 줄에서 하나씩 꺼낸다.
    스트림에 직접 시간 제한을 걸어 기다리면, 시간이 다 됐을 때 스트림이 취소되어 끝나 버린다.
    """

    def __init__(self, items: AsyncIterator[Frame | Comment]) -> None:
        self._items = items
        self._queue: asyncio.Queue[Frame | Comment | None] = asyncio.Queue()
        self._task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        """스트림이 내놓는 것을 줄에 넣는다. 스트림이 끝나면 None 을 넣는다."""
        async for item in self._items:
            self._queue.put_nowait(item)
        self._queue.put_nowait(None)

    async def next(self, timeout: float = SOON) -> Frame | None:
        """다음 메시지를 꺼낸다. 주석은 건너뛴다. 스트림이 끝났으면 None. 시간 안에 오지 않으면 실패한다."""
        while True:
            item = await asyncio.wait_for(self._queue.get(), timeout)
            if not isinstance(item, Comment):
                return item

    async def next_comment(self, timeout: float = SOON) -> str:
        """다음 주석을 꺼낸다."""
        item = await asyncio.wait_for(self._queue.get(), timeout)
        assert isinstance(item, Comment), item
        return item.text

    async def take(self, count: int) -> list[Frame]:
        """메시지를 count 개 꺼낸다."""
        return [await self.next() for _ in range(count)]

    async def is_quiet(self) -> bool:
        """잠깐 기다려도 메시지가 오지 않는지 본다."""
        try:
            await self.next(timeout=QUIET)
        except TimeoutError:
            return True
        return False

    async def settle(self) -> None:
        """
        스트림이 처음 읽기를 마치고 기다리는 상태가 될 때까지 둔다. 그사이에 온 것이 있으면 실패한다.

        이 뒤에 생긴 것이 도착했다면, 처음 읽기에 딸려 온 것이 아니라 신호를 받아서 온 것이다.
        """
        assert await self.is_quiet()

    async def close(self) -> None:
        """받는 쪽이 연결을 끊는다. 서버에서는 스트림이 취소된다."""
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)


class DeafSource:
    """신호를 듣지 못하는 것. 듣는 연결을 맺지 못한 상황을 만든다."""

    async def ensure_listening(self) -> bool:
        return False

    async def stop(self) -> None:
        return None


class QuietSource:
    """신호를 듣고 있다고 하지만 아무 신호도 전하지 않는 것. DB 의 신호를 놓친 상황을 만든다."""

    async def ensure_listening(self) -> bool:
        return True

    async def stop(self) -> None:
        return None


class FakeClock:
    """테스트가 손으로 흘리는 시계. 스트림의 박자를 실제로 기다리지 않고 재게 한다."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds
