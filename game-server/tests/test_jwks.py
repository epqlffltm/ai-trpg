# game-server/tests/test_jwks.py

"""
공개키를 가져오고 기억하는 규칙을 검증한다. 실제 인증 서버 없이 가짜 서버와 가짜 시계로 한다.
"""

import asyncio

import pytest

from app.auth.jwks import (
    JWKS_CACHE_SECONDS,
    REFETCH_INTERVAL_SECONDS,
    JwksCache,
    JwksFetchError,
    JwksUnavailableError,
    UnknownKeyError,
    parse_jwks,
)
from tests.conftest import TEST_JWKS_URL
from tests.signing import FakeAuthServer, SigningKey, make_signing_key


class FakeClock:
    """테스트가 마음대로 돌리는 시계."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture(scope='module')
def key() -> SigningKey:
    """인증 서버가 지금 쓰는 키. 만드는 데 시간이 걸려서 이 파일에서 한 번만 만든다."""
    return make_signing_key('key-1')


@pytest.fixture(scope='module')
def new_key() -> SigningKey:
    """인증 서버가 교체한 뒤에 쓰는 키."""
    return make_signing_key('key-2')


@pytest.fixture
def auth_server(key: SigningKey) -> FakeAuthServer:
    return FakeAuthServer(keys=[key])


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def cache(auth_server: FakeAuthServer, clock: FakeClock) -> JwksCache:
    return JwksCache(auth_server.make_client(), TEST_JWKS_URL, clock=clock)


# --- 가져와서 기억한다 ---


async def test_fetches_the_key_on_first_use(cache: JwksCache, auth_server: FakeAuthServer):
    found = await cache.get_key('key-1')

    assert found.key_id == 'key-1'
    assert auth_server.calls == 1


async def test_does_not_fetch_again_while_remembered(cache: JwksCache, auth_server: FakeAuthServer):
    await cache.get_key('key-1')
    await cache.get_key('key-1')

    # 요청마다 인증 서버에 묻지 않는다
    assert auth_server.calls == 1


async def test_fetches_again_after_the_cache_time(cache: JwksCache, auth_server: FakeAuthServer, clock: FakeClock):
    await cache.get_key('key-1')
    clock.advance(JWKS_CACHE_SECONDS)

    await cache.get_key('key-1')

    assert auth_server.calls == 2


# --- 인증 서버가 죽었을 때 ---


async def test_keeps_using_old_keys_when_refetch_fails(cache: JwksCache, auth_server: FakeAuthServer, clock: FakeClock):
    await cache.get_key('key-1')
    clock.advance(JWKS_CACHE_SECONDS)
    auth_server.down = True

    found = await cache.get_key('key-1')

    # 인증 서버가 죽었다고 놀던 사용자를 쫓아내지 않는다
    assert found.key_id == 'key-1'


async def test_does_not_retry_a_dead_server_on_every_request(
    cache: JwksCache, auth_server: FakeAuthServer, clock: FakeClock
):
    await cache.get_key('key-1')
    clock.advance(JWKS_CACHE_SECONDS)
    auth_server.down = True

    await cache.get_key('key-1')
    await cache.get_key('key-1')

    # 처음 가져올 때 1번, 만료된 뒤 1번. 그 뒤로는 간격이 지날 때까지 시도하지 않는다
    assert auth_server.calls == 2


async def test_fetches_again_once_the_server_is_back(cache: JwksCache, auth_server: FakeAuthServer, clock: FakeClock):
    await cache.get_key('key-1')
    clock.advance(JWKS_CACHE_SECONDS)
    auth_server.down = True
    await cache.get_key('key-1')

    auth_server.down = False
    clock.advance(REFETCH_INTERVAL_SECONDS)
    await cache.get_key('key-1')

    assert auth_server.calls == 3


async def test_reports_unavailable_when_there_is_no_key_at_all(cache: JwksCache, auth_server: FakeAuthServer):
    auth_server.down = True

    # 토큰이 틀린 것이 아니다. 맞는지 틀린지 알 수 없는 것이다
    with pytest.raises(JwksUnavailableError):
        await cache.get_key('key-1')


async def test_recovers_after_starting_while_the_server_was_down(
    cache: JwksCache, auth_server: FakeAuthServer, clock: FakeClock
):
    auth_server.down = True
    with pytest.raises(JwksUnavailableError):
        await cache.get_key('key-1')

    auth_server.down = False
    clock.advance(REFETCH_INTERVAL_SECONDS)
    found = await cache.get_key('key-1')

    assert found.key_id == 'key-1'


# --- 인증 서버가 키를 바꿨을 때 ---


async def test_fetches_again_for_an_unknown_kid(
    cache: JwksCache, auth_server: FakeAuthServer, clock: FakeClock, key: SigningKey, new_key: SigningKey
):
    await cache.get_key('key-1')
    auth_server.keys = [key, new_key]
    clock.advance(REFETCH_INTERVAL_SECONDS)

    found = await cache.get_key('key-2')

    # 기억 시간이 끝나기를 기다리지 않는다
    assert found.key_id == 'key-2'
    assert auth_server.calls == 2


async def test_rejects_a_kid_the_auth_server_does_not_have(cache: JwksCache):
    with pytest.raises(UnknownKeyError):
        await cache.get_key('forged')


async def test_unknown_kids_cannot_flood_the_auth_server(cache: JwksCache, auth_server: FakeAuthServer):
    for attempt in range(20):
        with pytest.raises(UnknownKeyError):
            await cache.get_key(f'forged-{attempt}')

    # 가짜 kid 를 아무리 보내도 인증 서버로 가는 요청은 간격마다 한 번이다
    assert auth_server.calls == 1


async def test_forgets_a_key_the_auth_server_removed(
    cache: JwksCache, auth_server: FakeAuthServer, clock: FakeClock, new_key: SigningKey
):
    await cache.get_key('key-1')
    auth_server.keys = [new_key]
    clock.advance(JWKS_CACHE_SECONDS)

    with pytest.raises(UnknownKeyError):
        await cache.get_key('key-1')


# --- 동시에 여러 요청이 올 때 ---


async def test_concurrent_requests_fetch_only_once(cache: JwksCache, auth_server: FakeAuthServer):
    found = await asyncio.gather(*(cache.get_key('key-1') for _ in range(50)))

    assert len(found) == 50
    # 50개가 각자 가져오지 않는다. 하나가 가져오고 나머지는 그 결과를 쓴다
    assert auth_server.calls == 1


# --- 키 목록 읽기 ---


def test_parse_skips_keys_it_cannot_use(key: SigningKey):
    without_kid = {name: value for name, value in key.jwk.items() if name != 'kid'}
    other_type = {'kty': 'EC', 'kid': 'ec-key', 'crv': 'P-256', 'x': 'AA', 'y': 'AA'}
    broken = {'kty': 'RSA', 'kid': 'broken', 'n': '!!', 'e': 'AQAB'}

    keys = parse_jwks({'keys': [without_kid, other_type, broken, 'not-a-key', key.jwk]})

    # 하나가 이상하다고 전부를 버리지 않는다
    assert list(keys) == ['key-1']


@pytest.mark.parametrize('document', [None, [], {}, {'keys': 'nope'}, {'keys': []}])
def test_parse_rejects_a_document_without_usable_keys(document: object):
    # 빈 목록을 받아들이면 기억하던 키를 전부 잃는다
    with pytest.raises(JwksFetchError):
        parse_jwks(document)


async def test_an_empty_key_list_does_not_wipe_remembered_keys(
    cache: JwksCache, auth_server: FakeAuthServer, clock: FakeClock
):
    await cache.get_key('key-1')
    auth_server.keys = []
    clock.advance(JWKS_CACHE_SECONDS)

    found = await cache.get_key('key-1')

    assert found.key_id == 'key-1'
