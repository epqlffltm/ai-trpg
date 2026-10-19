# trpg-server/app/auth/revocations.py

"""
인증 서버에서 끊긴 세션의 목록을 받아 기억한다(#274).

인증 서버에서 세션을 끊으면(비밀번호 변경과 재설정, 모든 기기 로그아웃, 계정 정지, 운영자 역할 빼기 뒤의 세션 끊기)
그 사용자의 세션 버전(ver)이 오르고 목록에 실린다. 목록의 min_ver 보다 ver 가 낮은 access 토큰은
끊기기 전에 발급된 것이라 거부한다. 목록이 없으면 그 토큰은 만료(15분)까지 통한다.
목록의 모양은 인증 서버 README 의 "다른 서버에서 토큰을 검증하는 방법" 5단계에 있다.

규칙(결제 서버, 게시판 서버와 같다):
  1. 서버가 뜨자마자 받고, 그 뒤 REFRESH_INTERVAL_SECONDS(30초)마다 다시 받는다.
     요청과 따로 받으므로 요청이 인증 서버를 기다리지 않는다
  2. 받지 못하면 마지막으로 받은 목록을 그대로 쓴다. 한 번도 받지 못했으면 아무 세션도 끊긴 것으로 보지 않는다
     (공개키도 없으면 어차피 503 이다). 줄은 access 토큰의 수명이 지나면 무의미해지므로 버리는 상한을 두지 않는다
  3. 한 줄이라도 모양이 틀린 문서는 통째로 받지 않는다. 틀린 줄만 건너뛰면 그 사용자의 끊긴 세션이 조용히 통한다
  4. 받지 못할 때마다 warning 한 줄(auth.revocations_unavailable)을 남긴다
  5. 문서는 MAX_DOCUMENT_BYTES(8MB)까지만 읽고, 인증 서버의 답은 FETCH_TIMEOUT_SECONDS(5초)까지만 기다린다
"""

import asyncio
import contextlib
import hashlib
import logging
import re

import httpx

from app.core import loops
from app.core.loops import Running
from app.observability.context import outgoing_headers

logger = logging.getLogger(__name__)

# 다시 받는 간격. 세션을 끊은 뒤 이 서버가 그 토큰을 막기까지 걸리는 가장 긴 시간이다
REFRESH_INTERVAL_SECONDS = 30
# 인증 서버의 답을 기다리는 시간
FETCH_TIMEOUT_SECONDS = 5
# 읽는 문서의 상한. 줄은 15분이 지나면 빠지므로 목록은 늘 작다. 이보다 크면 무언가 틀린 것이다
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024

# 로그의 operation 과 error_code(docs/observability.md)
FETCH_OPERATION = 'auth.revocations_fetch'
FETCH_ERROR_CODE = 'auth.revocations_unavailable'

# sub_sha256 의 모양. 소문자 16진수 64자
DIGEST_PATTERN = re.compile(r'[0-9a-f]{64}')


class RevocationsFetchError(Exception):
    """인증 서버에서 쓸 수 있는 목록을 받지 못했다. 까닭(reason)을 싣는다."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def digest_subject(subject: str) -> str:
    """토큰의 sub 를 목록의 sub_sha256 과 견줄 모양으로 바꾼다. 글자 그대로를 UTF-8 로 해시한다."""
    return hashlib.sha256(subject.encode()).hexdigest()


def is_version(value: object) -> bool:
    """세션 버전으로 쓸 수 있는 값인가. 0 이상의 정수다. JSON 의 true 는 정수가 아니다."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def parse_entry(entry: object) -> tuple[str, int]:
    """목록의 한 줄을 (sub_sha256, min_ver) 로 읽는다. 모양이 틀리면 RevocationsFetchError."""
    if not isinstance(entry, dict):
        raise RevocationsFetchError('invalid_entry')
    digest = entry.get('sub_sha256')
    min_version = entry.get('min_ver')
    if not isinstance(digest, str) or DIGEST_PATTERN.fullmatch(digest) is None or not is_version(min_version):
        raise RevocationsFetchError('invalid_entry')
    return digest, min_version


def parse_revocations(document: object) -> dict[str, int]:
    """
    문서에서 끊긴 세션을 sub_sha256 으로 찾을 수 있게 담는다.

    한 줄이라도 틀리면 통째로 거부한다(규칙 3). 같은 사람이 두 줄이면 높은 min_ver 를 쓴다.
    """
    if not isinstance(document, dict) or not isinstance(document.get('revocations'), list):
        raise RevocationsFetchError('invalid_document')
    revoked: dict[str, int] = {}
    for entry in document['revocations']:
        digest, min_version = parse_entry(entry)
        revoked[digest] = max(min_version, revoked.get(digest, 0))
    return revoked


async def fetch_revocations(client: httpx.AsyncClient, url: str) -> dict[str, int]:
    """인증 서버에서 목록을 받는다. 어떤 이유로든 받지 못하면 RevocationsFetchError."""
    try:
        # 우리 서버끼리의 호출이다. 추적을 이어 준다(docs/observability.md)
        response = await client.get(url, timeout=FETCH_TIMEOUT_SECONDS, headers=outgoing_headers())
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise RevocationsFetchError(type(error).__name__) from error
    if len(response.content) > MAX_DOCUMENT_BYTES:
        raise RevocationsFetchError('too_large')
    try:
        document = response.json()
    except ValueError as error:
        raise RevocationsFetchError('invalid_json') from error
    return parse_revocations(document)


class RevocationList:
    """
    받은 목록을 기억한다. 앱 하나에 하나만 만들어 모든 요청이 함께 쓴다.

    요청은 is_revoked 로 읽기만 한다. 받기는 뒤에서 도는 run 만 한다.
    """

    def __init__(self, client: httpx.AsyncClient, url: str, interval: float = REFRESH_INTERVAL_SECONDS) -> None:
        self._client = client
        self._url = url
        self.interval = interval
        self._revoked: dict[str, int] = {}

    def is_revoked(self, subject: str, version: int) -> bool:
        """이 사람의 이 세션 버전이 끊겼는가. 목록에 있으면서 버전이 min_ver 보다 낮다."""
        min_version = self._revoked.get(digest_subject(subject))
        return min_version is not None and version < min_version

    async def refresh(self) -> bool:
        """
        목록을 한 번 다시 받는다. 받았으면 True 다.

        받지 못하면 기억하던 목록을 그대로 두고 warning 을 남긴다(규칙 2, 4). 주소는 적지 않는다(내부 주소다).
        """
        try:
            self._revoked = await fetch_revocations(self._client, self._url)
        except RevocationsFetchError as error:
            logger.warning(
                '끊긴 세션의 목록을 받지 못했다. 기억한 %d줄을 계속 쓴다',
                len(self._revoked),
                extra={
                    'operation': FETCH_OPERATION,
                    'result': 'server_error',
                    'error_code': FETCH_ERROR_CODE,
                    'reason': error.reason,
                },
            )
            return False
        return True

    async def run(self, stop: asyncio.Event) -> None:
        """stop 이 켜질 때까지 바로 한 번, 그 뒤 interval 마다 받는다(규칙 1)."""
        while not stop.is_set():
            await self.refresh()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.interval)


def start(revocations: RevocationList) -> Running:
    """목록 받기를 돌리기 시작한다. 서버가 뜰 때 부른다."""
    return loops.start(revocations, 'session-revocations')
