# trpg-server/tests/test_attempt_limits.py

"""
시도 횟수 제한(#56)을 검증한다.

보는 것.
  - 세는 곳: 메모리(구간이 지나면 사라진다, 읽기는 올리지 않는다, 지운다)와 Redis(같은 것,
    그리고 서버 둘이 같은 수를 본다).
    Redis 에 닿지 못하면 CounterUnavailable.
  - 규칙: 모든 시도를 세는 것과 실패만 세는 것. 넘으면 기다릴 초를 알린다. 키에 대상이 그대로 드러나지 않는다.
    세는 곳에 닿지 못하면 막는 쪽(ensure_not_blocked)과 통과시키는 쪽(count_attempt)이 다르다.
    끄면 아무것도 하지 않는다.
  - 로비의 비밀번호: 다섯 번 틀리면 맞는 비밀번호도 받지 않는다(확인 자체를 하지 않는다). 429 와 Retry-After.
    맞히면 그 사람의 수만 지운다. 테이블 하나에 모두가 틀린 수도 센다. 비밀번호가 없는 테이블은 세지 않는다.
    Redis 에 닿지 못하면 503.
  - 채팅: 한 사람이 한 테이블에 짧은 시간 안에 다섯 줄까지. 다른 사람은 따로 센다. Redis 에 닿지 못해도 쓴다.
Redis 를 쓰는 테스트는 실제 Redis 에서 돈다(TEST_REDIS_URL, 기본 같은 PC 의 15 번 DB).
테스트마다 키의 앞부분이 달라 섞이지 않는다.
"""

import logging
import os
import uuid
from datetime import timedelta

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.logs import rendered
from server_core.testing.tokens import SigningKey

from app.limits.attempts import AttemptLimit, Limiter, LimitsUnavailable, TooManyAttempts
from app.limits.counters import CounterUnavailable, MemoryCounter, Tally
from app.limits.redis_counter import RedisCounter, connect
from app.limits.setup import Limiting, build_limiting, limits_from
from app.main import create_app
from app.tables import passwords
from tests.conftest import make_test_settings
from tests.test_chat_api import open_duo
from tests.test_lobby_api import PASSWORD, bearer, join_url, open_table

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
THIRD = uuid.UUID('33333333-2222-4333-8444-555555555555')

REDIS_URL = os.environ.get('TEST_REDIS_URL', 'redis://127.0.0.1:6379/15')
WRONG = '열려라 들깨'
LIMIT = AttemptLimit('example', 3, timedelta(seconds=60))
# 테이블을 만드는 테스트. 끝나면 테이블을 지운다
needs_tables = pytest.mark.usefixtures('clean_tables')


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


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """들어오려는 사람."""
    return bearer(signing_key, FRIEND)


@pytest.fixture
def third(signing_key: SigningKey) -> dict[str, str]:
    """또 한 사람."""
    return bearer(signing_key, THIRD)


@pytest.fixture
def limited(app: FastAPI) -> Limiting:
    """앱의 제한을 켠다. 메모리로 센다. 값은 기본값이다(비밀번호 다섯 번, 채팅 다섯 줄)."""
    limiting = build_limiting(make_test_settings(limits_enabled=True), None)
    app.state.limiting = limiting
    return limiting


@pytest.fixture
async def redis_client():
    """테스트용 Redis 의 클라이언트. 끝나면 닫는다."""
    client = connect(REDIS_URL, 1.0)
    yield client
    await client.aclose()


def a_prefix() -> str:
    """테스트마다 다른 키의 앞부분. 다른 테스트의 수와 섞이지 않는다(키는 구간이 지나면 사라진다)."""
    return f'game_test:limit:{uuid.uuid4().hex}'


def counting_verifications(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """비밀번호를 확인한(scrypt 를 돌린) 횟수를 세게 한다. 확인한 비밀번호들을 돌려준다."""
    seen: list[str] = []
    original = passwords.verify_password

    def verify(password: str, stored: str) -> bool:
        seen.append(password)
        return original(password, stored)

    monkeypatch.setattr(passwords, 'verify_password', verify)
    return seen


async def join(client: AsyncClient, headers: dict, table: dict, password: str):
    """로비에서 비밀번호로 들어가 본다. 응답을 그대로 돌려준다."""
    return await client.post(join_url(table), json={'password': password}, headers=headers)


async def say(client: AsyncClient, headers: dict, table: dict, content: str = '안녕'):
    """채팅을 쓴다. 응답을 그대로 돌려준다."""
    return await client.post(f'/api/v1/game/tables/{table["id"]}/messages', json={'content': content}, headers=headers)


# --- 메모리로 세기 ---


async def test_memory_counts_up_within_the_window():
    counter = MemoryCounter(clock=FakeClock())

    first = await counter.hit('k', 60)
    second = await counter.hit('k', 60)

    assert (first, second) == (Tally(1, 60), Tally(2, 60))


async def test_memory_forgets_after_the_window():
    clock = FakeClock()
    counter = MemoryCounter(clock=clock)
    await counter.hit('k', 60)

    clock.now += 60
    after = await counter.read('k')
    again = await counter.hit('k', 60)

    # 구간이 지나면 처음부터 다시 센다
    assert after == Tally(0, 0)
    assert again == Tally(1, 60)


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


async def test_redis_counts_up_and_sets_the_window(redis_client):
    counter = RedisCounter(redis_client)
    key = f'{a_prefix()}:k'

    first = await counter.hit(key, 60)
    second = await counter.hit(key, 60)
    read = await counter.read(key)

    assert (first.count, second.count, read.count) == (1, 2, 2)
    assert 0 < read.seconds_left <= 60


async def test_redis_clears(redis_client):
    counter = RedisCounter(redis_client)
    key = f'{a_prefix()}:k'
    await counter.hit(key, 60)

    await counter.clear(key)

    assert await counter.read(key) == Tally(0, 0)


async def test_two_servers_see_the_same_count(redis_client):
    other = connect(REDIS_URL, 1.0)
    prefix = a_prefix()
    one = Limiter(RedisCounter(redis_client), prefix)
    two = Limiter(RedisCounter(other), prefix)

    try:
        for _ in range(LIMIT.max_attempts):
            await one.count_failure(LIMIT, 'someone')
        # 다른 서버(다른 연결)에서 센 실패로 막힌다
        with pytest.raises(TooManyAttempts):
            await two.ensure_not_blocked(LIMIT, 'someone')
    finally:
        await other.aclose()


async def test_an_unreachable_redis_is_unavailable():
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
    key = Limiter(MemoryCounter(), 'game:limit').key(LIMIT, f'{ME}')

    # 키는 Redis 의 도구에 그대로 보인다. 누구의 수인지 드러나지 않게 해시한다
    assert key.startswith('game:limit:example:')
    assert str(ME) not in key


async def test_a_disabled_limiter_never_blocks():
    limiter = Limiter(DeadCounter(), 'p', enabled=False)

    for _ in range(10):
        await limiter.count_attempt(LIMIT, 'someone')
        await limiter.count_failure(LIMIT, 'someone')
    await limiter.ensure_not_blocked(LIMIT, 'someone')


async def test_unavailable_counting_lets_attempts_through(caplog: pytest.LogCaptureFixture):
    limiter = Limiter(DeadCounter(), 'p')

    with caplog.at_level(logging.WARNING, logger='app.limits.attempts'):
        await limiter.count_attempt(LIMIT, 'someone')

    # 막지 않는다. 대신 제한이 꺼져 있다는 것을 남긴다
    [line] = rendered(caplog.records, 'app.limits.attempts')
    assert (line['level'], line['error_code'], line['limit'], line['blocked']) == (
        'warning',
        'limits.unavailable',
        'example',
        False,
    )


async def test_unavailable_checking_blocks(caplog: pytest.LogCaptureFixture):
    limiter = Limiter(DeadCounter(), 'p')

    with caplog.at_level(logging.WARNING, logger='app.limits.attempts'):
        with pytest.raises(LimitsUnavailable):
            await limiter.ensure_not_blocked(LIMIT, 'someone')
        # 실패를 세지 못하거나 지우지 못해도 예외를 내지 않는다. 다음 확인이 막는다
        await limiter.count_failure(LIMIT, 'someone')
        await limiter.clear(LIMIT, 'someone')

    assert [line['blocked'] for line in rendered(caplog.records, 'app.limits.attempts')] == [True, False, False]


def test_the_limits_come_from_the_settings():
    limits = limits_from(
        make_test_settings(
            password_attempts_per_user=2,
            password_attempts_per_table=9,
            password_attempt_window_seconds=30,
            chat_messages_per_window=7,
            chat_window_seconds=3,
        )
    )

    assert (limits.password_per_user.max_attempts, limits.password_per_user.window) == (2, timedelta(seconds=30))
    assert (limits.password_per_table.max_attempts, limits.password_per_table.window) == (9, timedelta(seconds=30))
    assert (limits.chat.max_attempts, limits.chat.window) == (7, timedelta(seconds=3))


def test_the_defaults_follow_the_issue():
    limits = limits_from(make_test_settings())

    # 비밀번호는 10 분에 한 사람 다섯 번, 테이블 하나에 서른 번. 채팅은 10 초에 다섯 줄
    assert (limits.password_per_user.max_attempts, limits.password_per_table.max_attempts) == (5, 30)
    assert limits.password_per_user.window == timedelta(minutes=10)
    assert (limits.chat.max_attempts, limits.chat.window) == (5, timedelta(seconds=10))


# --- 로비의 비밀번호 ---


@needs_tables
async def test_after_five_wrong_guesses_even_the_right_password_is_refused(
    client: AsyncClient, me: dict, friend: dict, limited, monkeypatch: pytest.MonkeyPatch
):
    table = await open_table(client, me, password=PASSWORD)
    seen = counting_verifications(monkeypatch)

    wrong = [(await join(client, friend, table, WRONG)).status_code for _ in range(5)]
    refused = await join(client, friend, table, PASSWORD)

    # 다섯 번은 확인하고 틀렸다. 여섯 번째는 확인하지 않고 막았다(scrypt 를 돌리지 않는다)
    assert wrong == [status.HTTP_403_FORBIDDEN] * 5
    assert refused.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert len(seen) == 5
    body = refused.json()
    assert (body['code'], 0 < body['retry_after'] <= 600) == ('too_many_attempts', True)
    assert refused.headers['Retry-After'] == str(body['retry_after'])


@needs_tables
async def test_a_right_guess_forgets_the_mistakes(client: AsyncClient, me: dict, friend: dict, limited):
    table = await open_table(client, me, password=PASSWORD, capacity=3)
    for _ in range(4):
        await join(client, friend, table, WRONG)

    joined = await join(client, friend, table, PASSWORD)
    await client.delete(f'/api/v1/game/tables/{table["id"]}/members/me', headers=friend)
    again = [(await join(client, friend, table, WRONG)).status_code for _ in range(5)]

    # 맞혔으니 그 사람의 틀린 수는 지웠다. 나간 뒤 다시 다섯 번 틀릴 수 있다
    assert joined.status_code == status.HTTP_200_OK, joined.text
    assert again == [status.HTTP_403_FORBIDDEN] * 5


@needs_tables
async def test_guesses_from_many_accounts_add_up_for_the_table(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, third: dict
):
    app.state.limiting = build_limiting(make_test_settings(limits_enabled=True, password_attempts_per_table=3), None)
    table = await open_table(client, me, password=PASSWORD, capacity=3)

    for _ in range(3):
        await join(client, friend, table, WRONG)
    refused = await join(client, third, table, PASSWORD)

    # 다른 계정도 막힌다. 계정을 돌려 가며 맞히지 못한다
    assert refused.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@needs_tables
async def test_a_table_without_a_password_is_not_counted(client: AsyncClient, me: dict, friend: dict, limited):
    table = await open_table(client, me)

    responses = [(await join(client, friend, table, WRONG)).status_code for _ in range(6)]

    # 비밀번호가 없으면 무엇을 보내든 들어간다(두 번째부터는 이미 앉았다). 막지 않는다
    assert status.HTTP_429_TOO_MANY_REQUESTS not in responses
    assert responses[0] == status.HTTP_200_OK


@needs_tables
async def test_without_the_counter_a_password_cannot_be_tried(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, monkeypatch: pytest.MonkeyPatch
):
    table = await open_table(client, me, password=PASSWORD)
    app.state.limiting = Limiting(Limiter(DeadCounter(), 'p'), limits_from(make_test_settings()))
    seen = counting_verifications(monkeypatch)

    response = await join(client, friend, table, PASSWORD)

    # 실패를 셀 수 없으면 무한히 시도할 수 있다. 막는다
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json()['code'] == 'limits_unavailable'
    assert seen == []


@needs_tables
async def test_a_table_without_a_password_does_not_need_the_counter(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict
):
    table = await open_table(client, me)
    app.state.limiting = Limiting(Limiter(DeadCounter(), 'p'), limits_from(make_test_settings()))

    response = await join(client, friend, table, '')

    # 비밀번호가 없으면 세지 않으니 Redis 가 죽어도 들어온다
    assert response.status_code == status.HTTP_200_OK, response.text


# --- 채팅 ---


@needs_tables
async def test_the_sixth_line_in_ten_seconds_is_refused(client: AsyncClient, me: dict, friend: dict, limited):
    table = await open_duo(client, me, friend)

    mine = [(await say(client, me, table)).status_code for _ in range(6)]
    theirs = await say(client, friend, table)

    # 사람마다 따로 센다. 도배한 사람만 막힌다
    assert mine == [status.HTTP_201_CREATED] * 5 + [status.HTTP_429_TOO_MANY_REQUESTS]
    assert theirs.status_code == status.HTTP_201_CREATED


@needs_tables
async def test_chat_goes_on_without_the_counter(client: AsyncClient, app: FastAPI, me: dict, friend: dict):
    table = await open_duo(client, me, friend)
    app.state.limiting = Limiting(Limiter(DeadCounter(), 'p'), limits_from(make_test_settings()))

    responses = [(await say(client, me, table)).status_code for _ in range(7)]

    # 세지 못하면 막지 않는다. 채팅이 멈추는 것이 더 크다
    assert responses == [status.HTTP_201_CREATED] * 7


# --- 앱 ---


def test_the_app_counts_in_memory_without_redis():
    app = make_app()

    assert app.state.redis is None
    assert isinstance(app.state.limiting.limiter.counter, MemoryCounter)


def test_the_app_counts_in_redis_when_given_one():
    app = make_app(redis_url=REDIS_URL)

    assert isinstance(app.state.limiting.limiter.counter, RedisCounter)
    assert app.state.limiting.limiter.prefix == 'game:limit'


def make_app(**overrides) -> FastAPI:
    """설정을 바꾼 앱."""
    return create_app(make_test_settings(**overrides))
