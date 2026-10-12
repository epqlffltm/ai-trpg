# game-server/app/limits/counters.py

"""
세는 곳. 키마다 "구간 안에 몇 번"과 "구간이 끝나기까지 남은 초"를 들고 있다.

모양(Counter)만 정해 두고 구현을 바꿔 끼운다.
  - MemoryCounter: 서버 프로세스의 메모리. 서버가 하나일 때만 맞다. 다시 띄우면 지워진다. REDIS_URL 을 비우면 이것이다
  - RedisCounter(redis_counter.py): 서버가 여럿이어도 같은 수를 본다
세는 곳에 닿지 못하면 CounterUnavailable 을 낸다. 막을지 통과시킬지는 부르는 쪽(attempts.py)이 정한다.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol


class CounterUnavailable(Exception):
    """세는 곳에 닿지 못했다(Redis 가 죽었다, 시간이 다 됐다). 까닭의 글은 싣지 않는다."""


@dataclass(frozen=True)
class Tally:
    """키 하나의 지금 수. 센 적이 없으면 (0, 0) 이다."""

    count: int
    seconds_left: int


class Counter(Protocol):
    """세는 곳의 모양."""

    async def read(self, key: str) -> Tally:
        """수를 올리지 않고 읽는다."""
        ...

    async def hit(self, key: str, window_seconds: int) -> Tally:
        """수를 하나 올리고 올린 뒤의 수를 돌려준다. 처음 올린 것이면 window_seconds 뒤에 사라진다."""
        ...

    async def clear(self, key: str) -> None:
        """수를 지운다."""
        ...


@dataclass
class MemoryCounter:
    """
    서버 프로세스의 메모리로 센다. 키마다 (수, 사라지는 시각)을 둔다.

    await 가 없어 한 번에 끝난다. 이벤트 루프 하나 안에서는 둘이 섞이지 않는다.
    지난 키는 읽을 때 지운다. 따로 쓸어 담지 않는다(키는 사람 × 테이블만큼만 생긴다).
    clock 은 단조 시계다. 테스트가 바꿔 꽂는다.
    """

    clock: Callable[[], float] = time.monotonic
    entries: dict[str, tuple[int, float]] = field(default_factory=dict)

    def live(self, key: str) -> tuple[int, float] | None:
        """살아 있는 수. 사라질 시각이 지났으면 지우고 None."""
        entry = self.entries.get(key)
        if entry is not None and entry[1] <= self.clock():
            del self.entries[key]
            return None
        return entry

    def tally(self, entry: tuple[int, float] | None) -> Tally:
        """들고 있는 것을 Tally 로. 남은 초는 올림한다."""
        if entry is None:
            return Tally(0, 0)
        return Tally(entry[0], max(int(entry[1] - self.clock() + 0.999), 0))

    async def read(self, key: str) -> Tally:
        """수를 올리지 않고 읽는다."""
        return self.tally(self.live(key))

    async def hit(self, key: str, window_seconds: int) -> Tally:
        """수를 하나 올린다. 처음이면 지금부터 window_seconds 뒤에 사라진다."""
        entry = self.live(key)
        updated = (1, self.clock() + window_seconds) if entry is None else (entry[0] + 1, entry[1])
        self.entries[key] = updated
        return self.tally(updated)

    async def clear(self, key: str) -> None:
        """수를 지운다."""
        self.entries.pop(key, None)
