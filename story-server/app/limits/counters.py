# story-server/app/limits/counters.py

"""
세는 곳. 키마다 "구간 안에 몇 번"과 "구간이 끝나기까지 남은 초"를 들고 있다.

모양(Counter)만 정해 두고 구현을 바꿔 끼운다.
  - MemoryCounter: 서버 프로세스의 메모리. 서버가 하나일 때만 맞다. 다시 띄우면 지워진다. REDIS_URL 을 비우면 이것이다
  - RedisCounter(redis_counter.py): 서버가 여럿이어도 같은 수를 본다
세는 곳에 닿지 못하면 CounterUnavailable 을 낸다.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol


class CounterUnavailable(Exception):
    """세는 곳에 닿지 못했다(Redis 가 죽었다, 시간이 다 됐다). 까닭의 글은 싣지 않는다."""


@dataclass(frozen=True)
class Tally:
    """키 하나의 지금 수와 구간이 끝나기까지 남은 초."""

    count: int
    seconds_left: int


class Counter(Protocol):
    """세는 곳의 모양."""

    async def hit(self, key: str, window_seconds: int) -> Tally:
        """수를 하나 올리고 올린 뒤의 수를 돌려준다. 처음 올린 것이면 window_seconds 뒤에 사라진다."""
        ...


@dataclass
class MemoryCounter:
    """
    서버 프로세스의 메모리로 센다. 키마다 (수, 사라지는 시각)을 둔다.

    await 가 없어 한 번에 끝난다. 이벤트 루프 하나 안에서는 둘이 섞이지 않는다.
    지난 키는 다시 셀 때 덮어쓴다. 따로 쓸어 담지 않는다(키는 사람 × 제한만큼만 생긴다).
    clock 은 단조 시계다. 테스트가 바꿔 꽂는다.
    """

    clock: Callable[[], float] = time.monotonic
    entries: dict[str, tuple[int, float]] = field(default_factory=dict)

    async def hit(self, key: str, window_seconds: int) -> Tally:
        """수를 하나 올린다. 처음이거나 구간이 지났으면 지금부터 window_seconds 뒤에 사라진다."""
        now = self.clock()
        entry = self.entries.get(key)
        if entry is None or entry[1] <= now:
            entry = (0, now + window_seconds)
        count, ends = entry[0] + 1, entry[1]
        self.entries[key] = (count, ends)
        return Tally(count, max(int(ends - now + 0.999), 0))
