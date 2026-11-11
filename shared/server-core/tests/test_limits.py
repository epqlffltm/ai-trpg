# shared/server-core/tests/test_limits.py

"""
요청 수 제한의 공통부(server_core/limits/)를 검증한다. 게임, chat, story 의 같은 테스트를 모았다(#1266).

보는 것.
  - 메모리로 세기: 구간 안에서 오르고, 구간이 지나면 처음부터. 읽기는 올리지 않고, 지우면 잊는다. 남은 초를 올림한다
  - Redis 로 세기: 가짜 Redis 로 올리기, 읽기, 지우기. 닿지 못하면 CounterUnavailable(닫힌 포트로도 본다)
  - 규칙: 모든 시도를 세는 것과 실패만 세는 것. 대상과 제한은 따로 센다. 키에 대상이 드러나지 않는다.
    세는 곳에 닿지 못하면 막는 쪽(ensure_not_blocked)과 통과시키는 쪽(count_attempt)이 다르고, 둘 다 경고를 남긴다.
    끄면 아무것도 하지 않는다
  - 응답: 429 too_many_attempts 와 Retry-After, 503 limits_unavailable
실제 Redis 에서 세는 것(만료가 걸리는가, 서버 둘이 같은 수를 보는가)은 게임 서버의 tests/test_attempt_limits.py 가 본다.
"""

import logging
from datetime import timedelta

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError

from server_core.limits.attempts import AttemptLimit, Limiter, LimitsUnavailable, TooManyAttempts, retry_after
from server_core.limits.counters import CounterUnavailable, MemoryCounter, Tally
from server_core.limits.redis_counter import RedisCounter, connect
from server_core.limits.responses import use_limit_errors
from server_core.testing.logs import rendered

LIMIT = AttemptLimit('example', 3, timedelta(seconds=60))
LOGGER = 'server_core.limits.attempts'


class FakeClock:
    """테스트가 돌리는 단조 시계."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class DeadCounter:
    """늘 닿지 못하는 세는 곳. Redis 가 죽은 것과 같다."""

    async def read(self, key: str) -> Tally:
        raise CounterUnavailable

    async def hit(self, key: str, window_seconds: int) -> Tally:
        raise CounterUnavailable

    async def clear(self, key: str) -> None:
        raise CounterUnavailable


class FakePipeline:
    """get 과 ttl 을 모아 한 번에 돌려주는 가짜 파이프라인."""

    def __init__(self, redis: 'FakeRedis') -> None:
        self.redis = redis
        self.calls: list[tuple[str, str]] = []

    async def __aenter__(self) -> 'FakePipeline':
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    def get(self, key: str) -> 'FakePipeline':
        self.calls.append(('get', key))
        return self

    def ttl(self, key: str) -> 'FakePipeline':
        self.calls.append(('ttl', key))
        return self

    async def execute(self) -> list:
        self.redis.require_alive()
        values = {'get': lambda key: self.redis.counts.get(key), 'ttl': lambda key: self.redis.ttls.get(key, -2)}
        return [values[name](key) for name, key in self.calls]


class FakeRedis:
    """RedisCounter 가 쓰는 명령만 받는 가짜 Redis. broken 이면 닿지 못한다."""

    def __init__(self, broken: bool = False) -> None:
        self.broken = broken
        self.counts: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    def require_alive(self) -> None:
        if self.broken:
            raise RedisConnectionError('닿지 못함')

    async def eval(self, script: str, keys: int, key: str, window_seconds: int) -> list[int]:
        self.require_alive()
        self.counts[key] = self.counts.get(key, 0) + 1
        self.ttls.setdefault(key, window_seconds)
        return [self.counts[key], self.ttls[key]]

    def pipeline(self, transaction: bool) -> FakePipeline:
        return FakePipeline(self)

    async def delete(self, key: str) -> None:
        self.require_alive()
        self.counts.pop(key, None)
        self.ttls.pop(key, None)


# --- 메모리로 세기 ---


async def test_memory_counts_up_within_the_window():
    counter = MemoryCounter(clock=FakeClock())

    first = await counter.hit('k', 60)
    second = await counter.hit('k', 60)

    assert (first, second) == (Tally(1, 60), Tally(2, 60))


async def test_memory_starts_over_after_the_window():
    clock = FakeClock()
    counter = MemoryCounter(clock=clock)
    await counter.hit('k', 60)
    clock.now += 30.5
    second = await counter.hit('k', 60)

    clock.now += 30
    after = await counter.read('k')
    again = await counter.hit('k', 60)

    # 구간은 첫 시도에서 시작한다. 지나면 처음부터 다시 센다
    assert second == Tally(2, 30)
    assert (after, again) == (Tally(0, 0), Tally(1, 60))


async def test_memory_reading_does_not_count_and_clearing_forgets():
    clock = FakeClock()
    counter = MemoryCounter(clock=clock)
    await counter.hit('k', 60)
    clock.now += 20.5

    read = await counter.read('k')
    await counter.clear('k')

    # 남은 초는 올림한다. 그 시간 뒤에는 반드시 된다
    assert read == Tally(1, 40)
    assert await counter.read('k') == Tally(0, 0)


# --- Redis 로 세기 ---


async def test_redis_counts_reads_and_clears():
    counter = RedisCounter(FakeRedis())

    first = await counter.hit('k', 60)
    second = await counter.hit('k', 60)
    read = await counter.read('k')
    await counter.clear('k')

    assert (first, second, read) == (Tally(1, 60), Tally(2, 60), Tally(2, 60))
    # 없는 키는 TTL 이 -2 다. 0 으로 읽는다
    assert await counter.read('k') == Tally(0, 0)


@pytest.mark.parametrize('command', ['hit', 'read', 'clear'])
async def test_a_broken_redis_is_unavailable(command: str):
    counter = RedisCounter(FakeRedis(broken=True))
    calls = {
        'hit': lambda: counter.hit('k', 60),
        'read': lambda: counter.read('k'),
        'clear': lambda: counter.clear('k'),
    }

    with pytest.raises(CounterUnavailable):
        await calls[command]()


async def test_an_unreachable_redis_is_unavailable():
    # 아무도 듣지 않는 포트다. 실제 클라이언트가 닿지 못한 것을 CounterUnavailable 로 바꾸는지 본다
    client = connect('redis://127.0.0.1:1/0', 0.2)
    counter = RedisCounter(client)

    try:
        with pytest.raises(CounterUnavailable):
            await counter.hit('k', 60)
        with pytest.raises(CounterUnavailable):
            await counter.read('k')
    finally:
        await client.aclose()


# --- 세고 막는 규칙 ---


async def test_every_attempt_counts_and_the_one_over_is_refused():
    limiter = Limiter(MemoryCounter(clock=FakeClock()), 'p')

    for _ in range(LIMIT.max_attempts):
        await limiter.count_attempt(LIMIT, 'someone')
    with pytest.raises(TooManyAttempts) as refused:
        await limiter.count_attempt(LIMIT, 'someone')

    assert refused.value.retry_after == 60


async def test_failures_block_from_the_limit_until_cleared():
    limiter = Limiter(MemoryCounter(clock=FakeClock()), 'p')

    for _ in range(LIMIT.max_attempts - 1):
        await limiter.count_failure(LIMIT, 'someone')
    await limiter.ensure_not_blocked(LIMIT, 'someone')
    await limiter.count_failure(LIMIT, 'someone')
    with pytest.raises(TooManyAttempts):
        await limiter.ensure_not_blocked(LIMIT, 'someone')
    await limiter.clear(LIMIT, 'someone')

    # 허용된 횟수만큼 실패하면 다음부터 막힌다. 지우면 풀린다
    await limiter.ensure_not_blocked(LIMIT, 'someone')


async def test_subjects_and_limits_are_counted_apart():
    limiter = Limiter(MemoryCounter(clock=FakeClock()), 'p')
    other = AttemptLimit('other', LIMIT.max_attempts, LIMIT.window)

    for _ in range(LIMIT.max_attempts):
        await limiter.count_failure(LIMIT, 'someone')

    await limiter.ensure_not_blocked(LIMIT, 'someone else')
    await limiter.ensure_not_blocked(other, 'someone')


def test_the_key_does_not_show_the_subject():
    key = Limiter(MemoryCounter(), 'chat:limit').key(LIMIT, 'person-1234')

    # 키는 Redis 의 도구에 그대로 보인다. 누구의 수인지 드러나지 않게 해시한다
    assert key.startswith('chat:limit:example:')
    assert 'person-1234' not in key


def test_a_window_just_ending_still_asks_to_wait_a_second():
    assert retry_after(Tally(5, 0)) == 1


async def test_a_disabled_limiter_never_counts_or_blocks():
    counter = MemoryCounter()
    limiter = Limiter(counter, 'p', enabled=False)
    dead = Limiter(DeadCounter(), 'p', enabled=False)

    for _ in range(10):
        await limiter.count_attempt(LIMIT, 'someone')
        await dead.count_attempt(LIMIT, 'someone')
        await dead.count_failure(LIMIT, 'someone')
    await dead.ensure_not_blocked(LIMIT, 'someone')
    await dead.clear(LIMIT, 'someone')

    assert counter.entries == {}


async def test_unavailable_counting_lets_attempts_through(caplog: pytest.LogCaptureFixture):
    limiter = Limiter(DeadCounter(), 'p')

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        await limiter.count_attempt(LIMIT, 'someone')

    # 막지 않는다. 대신 제한이 꺼져 있다는 것을 남긴다
    [line] = rendered(caplog.records, LOGGER)
    assert (line['level'], line['error_code'], line['limit'], line['blocked']) == (
        'warning',
        'limits.unavailable',
        'example',
        False,
    )


async def test_unavailable_checking_blocks(caplog: pytest.LogCaptureFixture):
    limiter = Limiter(DeadCounter(), 'p')

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        with pytest.raises(LimitsUnavailable):
            await limiter.ensure_not_blocked(LIMIT, 'someone')
        # 실패를 세지 못하거나 지우지 못해도 예외를 내지 않는다. 다음 확인이 막는다
        await limiter.count_failure(LIMIT, 'someone')
        await limiter.clear(LIMIT, 'someone')

    assert [line['blocked'] for line in rendered(caplog.records, LOGGER)] == [True, False, False]


# --- 응답 ---


def limited_app() -> FastAPI:
    """막히는 주소 둘을 가진 앱."""
    app = FastAPI()
    use_limit_errors(app)

    @app.get('/over', status_code=status.HTTP_200_OK)
    async def over() -> None:
        raise TooManyAttempts(42)

    @app.get('/unavailable', status_code=status.HTTP_200_OK)
    async def unavailable() -> None:
        raise LimitsUnavailable

    return app


async def test_too_many_attempts_is_429_with_the_wait():
    async with AsyncClient(transport=ASGITransport(app=limited_app()), base_url='http://test') as client:
        response = await client.get('/over')

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.headers['retry-after'] == '42'
    assert (response.json()['code'], response.json()['retry_after']) == ('too_many_attempts', 42)


async def test_unavailable_limits_are_503():
    async with AsyncClient(transport=ASGITransport(app=limited_app()), base_url='http://test') as client:
        response = await client.get('/unavailable')

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json()['code'] == 'limits_unavailable'
    assert 'retry-after' not in response.headers
