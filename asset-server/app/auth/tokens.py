# asset-server/app/auth/tokens.py

"""
인증 서버가 발급한 access 토큰을 검증한다.

인증 서버의 DB 를 보지 않는다. 공개키로 서명을 확인하고, 토큰 안에 적힌 값만 본다.
인증 서버에서 세션을 끊은 사람(로그아웃, 비밀번호 변경, 계정 정지)의 토큰은 끊긴 세션의 목록으로 거부한다
(app/auth/revocations.py, #274). 목록을 30초마다 받으므로 끊은 뒤 길어야 30초쯤 더 통한다.

확인하는 것:
  - 서명 방식이 RS256 인가. 토큰이 스스로 적어 온 방식을 믿지 않는다.
  - 인증 서버의 키로 서명됐는가.
  - 만료되지 않았는가(exp).
  - 인증 서버가 발급했는가(iss).
  - 이 서버에 쓰라고 발급됐는가(aud).
  - access 토큰인가. refresh 토큰도 같은 키로 서명되므로 종류를 따로 본다.
  - 끊긴 세션의 것이 아닌가. 세션 버전(ver, 없으면 0)이 목록의 min_ver 보다 낮으면 거부한다.

게임 서버의 app/auth/tokens.py 에서 가져왔다. asset 서버는 누구의 것인지(sub)만 쓴다.
성인 등급(adult_content)과 역할(roles)은 읽지 않는다. 쓰게 되면 게임 서버의 것을 그대로 가져온다.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import jwt

from app.auth.jwks import JwksCache, UnknownKeyError
from app.auth.revocations import RevocationList, is_version
from app.core.config import Settings

# 이 서버가 받는 서명 방식. 하나만 적는다.
# 토큰 머리말의 alg 를 그대로 믿으면, 서명이 없는 토큰(none)이나
# 공개키를 비밀키처럼 써서 만든 토큰(HS256)이 통과한다
ALGORITHM = 'RS256'

# 토큰에 반드시 있어야 하는 값. 없으면 확인을 건너뛰지 않고 거부한다
REQUIRED_CLAIMS = ['exp', 'iss', 'aud', 'sub']

# access 토큰의 token_type 값. 인증 서버(simplejwt)가 넣는다
ACCESS_TOKEN_TYPE = 'access'

# 세션 버전이 적힌 칸. 인증 서버가 세션을 끊을 때마다 올린다. 없으면 0 으로 본다(인증 서버 README 의 약속)
SESSION_VERSION_CLAIM = 'ver'

# 서버끼리 시계가 조금 어긋나는 것을 봐주는 시간.
# 0 이면 인증 서버의 시계가 1초만 빨라도 방금 발급한 토큰이 "아직 유효하지 않다"로 거부된다
CLOCK_SKEW_SECONDS = 10


class InvalidTokenError(Exception):
    """
    토큰을 받아들일 수 없다.

    이유를 나누지 않는다. 만료인지 서명이 틀렸는지를 알려 주면 토큰을 꾸며 내는 쪽에 도움이 된다.
    """


@dataclass(frozen=True)
class AccessClaims:
    """검증을 마친 토큰에서 꺼낸 값. 이 객체가 있다는 것이 검증을 통과했다는 뜻이다."""

    # 인증 서버의 public_id. asset 서버는 사용자를 이 값으로만 가리킨다(페르소나와 그림의 주인)
    user_id: uuid.UUID

    # 토큰이 만료되는 시각(exp). 요청 하나는 검증한 순간에 끝나므로 볼 일이 없다.
    # 나중에 실시간 스트림(SSE)이 본다. 만료된 뒤에도 계속 보내면 로그아웃한 사람의 연결이 살아 있게 된다
    expires_at: datetime


def read_key_id(token: str) -> str:
    """
    서명을 확인하기 전에 머리말만 읽어, 어느 키로 확인할지(kid) 알아낸다.

    이 시점의 값은 아직 믿을 수 없다. 키를 고르는 데만 쓴다.
    """
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as error:
        raise InvalidTokenError from error

    key_id = header.get('kid')
    if header.get('alg') != ALGORITHM or not isinstance(key_id, str) or not key_id:
        raise InvalidTokenError
    return key_id


def decode_claims(token: str, key: jwt.PyJWK, settings: Settings) -> dict:
    """서명, 만료, 발급자, 대상을 확인하고 토큰 안의 값을 돌려준다."""
    try:
        return jwt.decode(
            token,
            key,
            algorithms=[ALGORITHM],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            leeway=CLOCK_SKEW_SECONDS,
            options={'require': REQUIRED_CLAIMS},
        )
    except jwt.PyJWTError as error:
        raise InvalidTokenError from error


def build_access_claims(claims: dict) -> AccessClaims:
    """토큰 안의 값에서 이 서버가 쓰는 것만 꺼낸다. access 토큰이 아니면 거부한다."""
    if claims.get('token_type') != ACCESS_TOKEN_TYPE:
        raise InvalidTokenError

    try:
        user_id = uuid.UUID(claims['sub'])
    except (ValueError, TypeError, AttributeError) as error:
        raise InvalidTokenError from error
    # exp 가 숫자라는 것은 decode_claims 가 이미 확인했다
    expires_at = datetime.fromtimestamp(claims['exp'], UTC)
    return AccessClaims(user_id=user_id, expires_at=expires_at)


def read_session_version(claims: dict) -> int:
    """
    토큰의 세션 버전을 읽는다. 없으면 0 이다.

    있는데 0 이상의 정수가 아니면 거부한다. 모양이 틀린 값을 0 으로 읽으면 끊긴 세션이 통할 수 있다.
    """
    version = claims.get(SESSION_VERSION_CLAIM, 0)
    if not is_version(version):
        raise InvalidTokenError
    return version


def ensure_not_revoked(claims: dict, revocations: RevocationList) -> None:
    """끊긴 세션의 토큰이면 InvalidTokenError. sub 는 글자 그대로 견준다(목록이 그 글자의 해시다)."""
    if revocations.is_revoked(claims['sub'], read_session_version(claims)):
        raise InvalidTokenError


async def verify_access_token(
    token: str,
    jwks: JwksCache,
    revocations: RevocationList,
    settings: Settings,
) -> AccessClaims:
    """
    access 토큰을 검증하고 그 안의 값을 돌려준다.

    토큰이 틀렸거나 끊긴 세션의 것이면 InvalidTokenError.
    키를 구할 수 없어 맞는지 틀린지 알 수 없으면 JwksUnavailableError 가 그대로 올라간다.
    """
    key_id = read_key_id(token)
    try:
        key = await jwks.get_key(key_id)
    except UnknownKeyError as error:
        raise InvalidTokenError from error

    claims = decode_claims(token, key, settings)
    access = build_access_claims(claims)
    ensure_not_revoked(claims, revocations)
    return access
