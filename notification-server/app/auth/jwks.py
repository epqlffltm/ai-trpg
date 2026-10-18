# notification-server/app/auth/jwks.py

"""
인증 서버의 공개키(JWKS)를 가져오고 기억한다.

토큰을 검증할 때마다 인증 서버에 묻지 않는다. 한 번 가져온 키를 기억해 두고 쓴다.
인증 서버가 잠깐 죽어 있어도, 기억한 키가 있으면 이미 로그인한 사용자의 요청을 계속 처리한다.

규칙은 다섯이다.
  1. 기억한 지 JWKS_CACHE_SECONDS(5분)가 지나면 다시 가져온다.
  2. 기억에 없는 키 ID(kid)가 오면 다시 가져온다. 인증 서버가 키를 바꾼 경우다.
  3. 다시 가져오기는 REFETCH_INTERVAL_SECONDS 에 한 번만 시도한다.
     가짜 kid 를 계속 보내 인증 서버에 요청이 몰리게 하는 것을 막고, 죽은 인증 서버를 요청마다 기다리지 않는다.
  4. 다시 가져오기에 실패하면 기억하던 키를 계속 쓴다.
  5. 다만 마지막으로 가져온 지 JWKS_MAX_STALE_SECONDS(30분)가 지나면 기억하던 키를 버린다(#274).
     그 뒤로는 다시 가져올 때까지 토큰을 받아들이지 않는다(503).

5 가 없으면 인증 서버에 닿지 못하는 동안 옛 키를 끝없이 믿는다. 서명 키가 새서 인증 서버가 그 키를 빼도(긴급 폐기),
이 서버는 그 키로 만든 토큰을 계속 받는다. 인증 서버를 쓰러뜨리면 그 기간을 원하는 만큼 늘릴 수 있다.
서명 키가 새면 만료 시각도 마음대로 정한 토큰을 만들 수 있으므로, access 토큰의 수명은 막아 주지 못한다.
"이 서버가 그 키를 얼마나 빨리 안 믿게 되나"만이 막는다. 인증 서버가 살아 있으면 5분, 죽어 있어도 30분이다.
대신 인증 서버가 30분 넘게 죽어 있으면 이 서버의 로그인이 필요한 요청도 모두 막힌다.
게임 서버의 app/auth/jwks.py 에서 가져왔다.
게임 서버, 결제 서버, 게시판 서버와 같은 값을 쓴다. 서버마다 다르면 인증 서버가 죽었을 때 어디는 막히고 어디는 통한다.
"""

import asyncio
import logging
import time
from collections.abc import Callable

import httpx
import jwt

from app.observability.context import outgoing_headers

logger = logging.getLogger(__name__)

# 가져온 키를 기억하는 시간. 인증 서버가 뺀 키를 이만큼 더 믿을 수 있다(긴급 폐기에 걸리는 시간)
JWKS_CACHE_SECONDS = 5 * 60
# 다시 가져오지 못해도 기억한 키를 쓰는 가장 긴 시간. 마지막으로 가져온 때부터 센다. 지나면 키를 버린다
JWKS_MAX_STALE_SECONDS = 30 * 60
# 키를 버렸을 때의 오류 코드(docs/observability.md)
JWKS_UNAVAILABLE_ERROR_CODE = 'auth.jwks_unavailable'

# 다시 가져오기를 시도하는 최소 간격
REFETCH_INTERVAL_SECONDS = 60

# 인증 서버의 응답을 기다리는 시간. 이 시간 동안 요청이 멈춰 있으므로 짧게 잡는다
FETCH_TIMEOUT_SECONDS = 5

# 이 서버가 받는 서명 방식. 키의 종류도 이것에 맞는 것만 기억한다
KEY_TYPE = 'RSA'


class JwksFetchError(Exception):
    """인증 서버에서 쓸 수 있는 키 목록을 받지 못했다."""


class JwksUnavailableError(Exception):
    """기억한 키가 하나도 없고, 지금 가져올 수도 없다. 토큰이 맞는지 틀린지 알 수 없다."""


class UnknownKeyError(Exception):
    """키 목록은 있지만 그 안에 이 kid 가 없다. 이 서버가 믿는 키로 서명한 토큰이 아니다."""


def parse_jwks(document: object) -> dict[str, jwt.PyJWK]:
    """
    JWKS 문서에서 서명 검증에 쓸 키를 골라 kid 로 찾을 수 있게 담는다.

    kid 가 없는 키, RSA 가 아닌 키, 읽을 수 없는 키는 건너뛴다.
    하나가 이상하다고 전부를 버리면, 인증 서버가 새 종류의 키를 추가했을 때 검증이 통째로 멈춘다.
    """
    if not isinstance(document, dict) or not isinstance(document.get('keys'), list):
        raise JwksFetchError('JWKS 형식이 아니다')

    keys: dict[str, jwt.PyJWK] = {}
    for entry in document['keys']:
        if not isinstance(entry, dict) or entry.get('kty') != KEY_TYPE or not entry.get('kid'):
            continue
        try:
            keys[entry['kid']] = jwt.PyJWK.from_dict(entry)
        except jwt.PyJWTError:
            continue

    if not keys:
        raise JwksFetchError('쓸 수 있는 키가 없다')
    return keys


async def fetch_jwks(client: httpx.AsyncClient, url: str) -> dict[str, jwt.PyJWK]:
    """인증 서버에서 JWKS 를 가져온다. 어떤 이유로든 받지 못하면 JwksFetchError."""
    try:
        # 우리 서버끼리의 호출이다. 추적을 이어 준다(docs/observability.md)
        response = await client.get(url, timeout=FETCH_TIMEOUT_SECONDS, headers=outgoing_headers())
        response.raise_for_status()
        document = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise JwksFetchError(type(error).__name__) from error
    return parse_jwks(document)


class JwksCache:
    """
    가져온 키를 기억한다. 앱 하나에 하나만 만들어 모든 요청이 함께 쓴다.

    시계를 밖에서 받는다. 테스트가 한 시간을 기다리지 않고 시간을 돌릴 수 있다.
    """

    def __init__(self, client: httpx.AsyncClient, url: str, clock: Callable[[], float] = time.monotonic) -> None:
        self._client = client
        self._url = url
        self._clock = clock
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at: float | None = None
        self._last_attempt_at: float | None = None
        # 여러 요청이 동시에 다시 가져오려 할 때 하나만 가져오게 한다
        self._lock = asyncio.Lock()

    async def get_key(self, kid: str) -> jwt.PyJWK:
        """
        kid 에 해당하는 키를 돌려준다.

        키 목록이 아예 없으면 JwksUnavailableError, 목록에 그 kid 가 없으면 UnknownKeyError.
        """
        if self._needs_refetch(kid):
            await self._refetch_once(kid)
        if self._is_too_stale():
            self._forget()

        if not self._keys:
            raise JwksUnavailableError
        if kid not in self._keys:
            raise UnknownKeyError
        return self._keys[kid]

    def _needs_refetch(self, kid: str) -> bool:
        """기억한 것으로는 부족한가. 기억 시간이 지났거나, 모르는 kid 다."""
        return self._is_expired() or kid not in self._keys

    def _is_expired(self) -> bool:
        if self._fetched_at is None:
            return True
        return self._clock() - self._fetched_at >= JWKS_CACHE_SECONDS

    def _is_too_stale(self) -> bool:
        """기억한 키가 너무 낡았나. 키가 있고, 마지막으로 가져온 지 JWKS_MAX_STALE_SECONDS 가 지났다."""
        if not self._keys or self._fetched_at is None:
            return False
        return self._clock() - self._fetched_at >= JWKS_MAX_STALE_SECONDS

    def _forget(self) -> None:
        """
        기억한 키를 버린다. 다시 가져올 때까지 토큰을 받아들이지 않는다.

        로그인이 필요한 요청이 모두 막히는 일이라 사람이 봐야 한다. error 로 남긴다.
        """
        logger.error(
            'JWKS 를 %d초 넘게 다시 가져오지 못해 기억한 키 %d개를 버렸다. 인증 서버를 확인해야 한다',
            JWKS_MAX_STALE_SECONDS,
            len(self._keys),
            extra={'error_code': JWKS_UNAVAILABLE_ERROR_CODE},
        )
        self._keys = {}

    def _may_attempt(self) -> bool:
        """지금 다시 가져오기를 시도해도 되는가. 마지막 시도에서 간격이 지났는가."""
        if self._last_attempt_at is None:
            return True
        return self._clock() - self._last_attempt_at >= REFETCH_INTERVAL_SECONDS

    async def _refetch_once(self, kid: str) -> None:
        """
        여러 요청이 동시에 와도 한 번만 다시 가져온다.

        먼저 온 요청이 가져오는 동안 나머지는 잠금 앞에서 기다린다.
        기다리지 않고 지나가면, 아직 키가 도착하지 않아서 멀쩡한 토큰을 거부하게 된다.
        """
        async with self._lock:
            # 기다리는 동안 먼저 온 요청이 이미 가져왔을 수 있다. 다시 확인한다
            if self._needs_refetch(kid) and self._may_attempt():
                await self._refetch()

    async def _refetch(self) -> None:
        """키 목록을 다시 가져온다. 실패하면 기억하던 키를 그대로 둔다."""
        # 성공하든 실패하든 시도한 시각을 적는다. 실패한 직후에 또 시도하지 않는다
        self._last_attempt_at = self._clock()
        try:
            self._keys = await fetch_jwks(self._client, self._url)
        except JwksFetchError as error:
            # 주소를 적지 않는다. 내부 주소가 로그에 남는다
            logger.warning('JWKS 를 가져오지 못했다: %s. 기억한 키 %d개를 계속 쓴다', error, len(self._keys))
            return
        self._fetched_at = self._clock()
