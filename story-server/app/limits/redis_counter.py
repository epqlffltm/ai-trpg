# story-server/app/limits/redis_counter.py

"""
Redis 로 센다. 서버가 여럿이어도 같은 수를 본다. 게임 서버, chat 서버의 것과 같다.

올리기와 만료 걸기를 Lua 한 덩어리로 보낸다. 따로 보내면 올린 직후 서버가 죽었을 때
만료가 없는 키가 남아 그 사람이 영영 막힌다.

Redis 가 느리면 요청이 그만큼 기다린다. 그래서 연결과 명령에 짧은 시간 제한을 둔다(REDIS_TIMEOUT_SECONDS).
닿지 못하면 CounterUnavailable 이다. 오류의 글에는 주소가 들어 있을 수 있어 싣지 않는다.
"""

from dataclasses import dataclass

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.limits.counters import CounterUnavailable, Tally

# 수를 올리고, 처음 올린 것이면 만료를 건다. 올린 수와 남은 초를 돌려준다
INCREMENT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {count, redis.call('TTL', KEYS[1])}
"""


def connect(url: str, timeout: float) -> redis.Redis:
    """Redis 클라이언트를 만든다. 만드는 것만으로는 연결하지 않는다. 앱이 꺼질 때 닫는다."""
    return redis.Redis.from_url(url, socket_timeout=timeout, socket_connect_timeout=timeout)


@dataclass(frozen=True)
class RedisCounter:
    """Redis 로 세는 것."""

    client: redis.Redis

    async def hit(self, key: str, window_seconds: int) -> Tally:
        """수를 하나 올린다. 처음이면 window_seconds 뒤에 사라진다."""
        try:
            count, seconds_left = await self.client.eval(INCREMENT_SCRIPT, 1, key, window_seconds)
        except (RedisError, OSError, TimeoutError) as error:
            raise CounterUnavailable from error
        return Tally(int(count), max(int(seconds_left), 0))
