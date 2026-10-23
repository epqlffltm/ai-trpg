# chat-server/tests/test_limits.py

"""
요청 수 제한(app/limits/, #671)을 검증한다. 세는 곳은 메모리와 가짜 Redis 다. API 는 실제 DB(chat_test)에서 돈다.

보는 것.
  - 메모리로 세기: 구간 안에서 오르고, 구간이 지나면 처음부터. 남은 초를 올림한다
  - Redis 로 세기: 올린 수와 남은 초를 읽는다. 닿지 못하면 CounterUnavailable
  - 규칙: 꺼져 있으면 세지 않는다. 넘으면 429(기다릴 초). 세는 곳에 닿지 못하면 막지 않고 경고를 남긴다.
    키에는 사람의 번호를 그대로 넣지 않는다
  - API: 모델을 부르는 요청과 쓰기를 사람마다 따로 센다. 넘으면 429 too_many_attempts 와 Retry-After
"""

import asyncio
import logging
import uuid
from datetime import timedelta

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from server_core.testing.tokens import SigningKey
from sqlalchemy.ext.asyncio import AsyncSession

from app.limits.attempts import AttemptLimit, Limiter, TooManyAttempts, retry_after
from app.limits.counters import CounterUnavailable, MemoryCounter, Tally
from app.limits.redis_counter import RedisCounter
from app.limits.setup import build_limiting
from tests.assets import FakeAsset
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, bearer, start_with_luna, turn_on_luna

LIMIT = AttemptLimit('generations', 2, timedelta(seconds=60))
SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')


class Clock:
    """바꿀 수 있는 단조 시계."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeRedis:
    """eval 만 받는 가짜 Redis. 올린 수를 들고 있거나, broken 이면 닿지 못한다."""

    def __init__(self, broken: bool = False) -> None:
        self.broken = broken
        self.counts: dict[str, int] = {}

    async def eval(self, script, keys, key, window_seconds):
        if self.broken:
            raise RedisConnectionError('닿지 못함')
        self.counts[key] = self.counts.get(key, 0) + 1
        return [self.counts[key], window_seconds]


class Unreachable:
    async def hit(self, key: str, window_seconds: int) -> Tally:
        raise CounterUnavailable


# --- 세는 곳 ---


async def test_memory_counts_within_the_window_and_starts_over_after():
    clock = Clock()
    counter = MemoryCounter(clock=clock)

    first = await counter.hit('k', 60)
    clock.now += 30.5
    second = await counter.hit('k', 60)
    clock.now += 30
    third = await counter.hit('k', 60)

    assert (first, second, third) == (Tally(1, 60), Tally(2, 30), Tally(1, 60))


async def test_redis_counts_and_reports_when_unreachable():
    counter = RedisCounter(FakeRedis())

    assert (await counter.hit('k', 60), await counter.hit('k', 60)) == (Tally(1, 60), Tally(2, 60))
    with pytest.raises(CounterUnavailable):
        await RedisCounter(FakeRedis(broken=True)).hit('k', 60)


# --- 규칙 ---


async def test_attempts_over_the_limit_are_refused_with_the_wait():
    limiter = Limiter(MemoryCounter(clock=Clock()), 'chat:limit')

    await limiter.count_attempt(LIMIT, 'me')
    await limiter.count_attempt(LIMIT, 'me')
    with pytest.raises(TooManyAttempts) as refused:
        await limiter.count_attempt(LIMIT, 'me')
    await limiter.count_attempt(LIMIT, 'you')

    assert refused.value.retry_after == 60


async def test_a_disabled_limiter_counts_nothing():
    counter = MemoryCounter()
    limiter = Limiter(counter, 'chat:limit', enabled=False)

    for _ in range(5):
        await limiter.count_attempt(LIMIT, 'me')

    assert counter.entries == {}


async def test_an_unreachable_counter_lets_it_through_with_a_warning(caplog: pytest.LogCaptureFixture):
    limiter = Limiter(Unreachable(), 'chat:limit')

    with caplog.at_level(logging.WARNING, logger='app.limits.attempts'):
        for _ in range(5):
            await limiter.count_attempt(LIMIT, 'me')

    assert caplog.records[-1].error_code == 'limits.unavailable'


def test_a_window_just_ending_still_asks_to_wait_a_second():
    assert retry_after(Tally(5, 0)) == 1


async def test_generations_and_writes_do_not_share_a_count(app: FastAPI):
    settings = app.state.settings.model_copy(update={'limits_enabled': True, 'generation_limit': 2, 'write_limit': 1})
    limiting = build_limiting(settings, None)

    await limiting.limiter.count_attempt(limiting.limits.generations, 'me')
    await limiting.limiter.count_attempt(limiting.limits.generations, 'me')
    await limiting.limiter.count_attempt(limiting.limits.writes, 'me')


def test_the_key_hides_the_person():
    key = Limiter(MemoryCounter(), 'chat:limit').key(LIMIT, 'person-1234')

    assert key.startswith('chat:limit:generations:')
    assert 'person-1234' not in key


# --- API ---


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def limited(app: FastAPI) -> None:
    """제한을 켠다. 모델을 부르는 요청은 둘, 쓰기는 하나까지(1 분)."""
    settings = app.state.settings.model_copy(update={'limits_enabled': True, 'generation_limit': 2, 'write_limit': 1})
    app.state.limiting = build_limiting(settings, None)


@pytest.fixture
async def conversation(clean_tables: None, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict):
    await turn_on_luna(session)
    return await start_with_luna(client, asset, mine)


@pytest.mark.usefixtures('clean_tables')
async def test_generations_over_the_limit_are_429(
    client: AsyncClient,
    app: FastAPI,
    conversation: dict,
    mine: dict,
    signing_key: SigningKey,
    asset: FakeAsset,
    limited: None,
):
    app.state.model_router = FakeRouter()
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    answers = []
    for _ in range(3):
        answers.append(await client.post(url, json={'content': '안녕'}, headers=mine))
        await asyncio.gather(*list(app.state.turns))

    assert [answer.status_code for answer in answers] == [200, 200, status.HTTP_429_TOO_MANY_REQUESTS]
    assert answers[-1].json()['code'] == 'too_many_attempts'
    assert int(answers[-1].headers['Retry-After']) >= 1
    # 다른 사람은 따로 센다(대화는 남의 것이라 404 지만 막히지는 않았다)
    other = await client.post(url, json={'content': '안녕'}, headers=bearer(signing_key, SOMEONE_ELSE))
    assert other.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.usefixtures('clean_tables')
async def test_writes_are_counted_apart_from_generations(
    client: AsyncClient, conversation: dict, mine: dict, limited: None
):
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/notes'

    first = await client.post(url, json={'text': '하나'}, headers=mine)
    second = await client.post(url, json={'text': '둘'}, headers=mine)
    read = await client.get(url, headers=mine)

    assert (first.status_code, second.status_code) == (status.HTTP_201_CREATED, status.HTTP_429_TOO_MANY_REQUESTS)
    # 읽기는 세지 않는다
    assert read.status_code == status.HTTP_200_OK
