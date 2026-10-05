# game-server/app/auth/tokens.py

"""
인증 서버가 발급한 access 토큰을 검증한다.

인증 서버의 DB 를 보지 않는다. 공개키로 서명을 확인하고, 토큰 안에 적힌 값만 본다.
그래서 인증 서버에서 로그아웃하거나 계정이 정지돼도, 이미 발급된 access 토큰은 만료될 때까지 통한다.
access 토큰의 수명을 짧게(15분) 잡는 이유다.

확인하는 것:
  - 서명 방식이 RS256 인가. 토큰이 스스로 적어 온 방식을 믿지 않는다.
  - 인증 서버의 키로 서명됐는가.
  - 만료되지 않았는가(exp).
  - 인증 서버가 발급했는가(iss).
  - 이 서버에 쓰라고 발급됐는가(aud).
  - access 토큰인가. refresh 토큰도 같은 키로 서명되므로 종류를 따로 본다.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import jwt

from app.auth.jwks import JwksCache, UnknownKeyError
from app.core.config import Settings

# 이 서버가 받는 서명 방식. 하나만 적는다.
# 토큰 머리말의 alg 를 그대로 믿으면, 서명이 없는 토큰(none)이나
# 공개키를 비밀키처럼 써서 만든 토큰(HS256)이 통과한다
ALGORITHM = 'RS256'

# 토큰에 반드시 있어야 하는 값. 없으면 확인을 건너뛰지 않고 거부한다
REQUIRED_CLAIMS = ['exp', 'iss', 'aud', 'sub']

# access 토큰의 token_type 값. 인증 서버(simplejwt)가 넣는다
ACCESS_TOKEN_TYPE = 'access'

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

    # 인증 서버의 public_id. 게임 서버는 사용자를 이 값으로만 가리킨다
    user_id: uuid.UUID

    # 토큰이 만료되는 시각(exp). 요청 하나는 검증한 순간에 끝나므로 볼 일이 없다.
    # 스트림처럼 오래 열려 있는 응답이 본다. 만료된 뒤에도 계속 보내면 로그아웃한 사람의 연결이 살아 있게 된다
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
    return AccessClaims(user_id=user_id, expires_at=datetime.fromtimestamp(claims['exp'], UTC))


async def verify_access_token(token: str, jwks: JwksCache, settings: Settings) -> AccessClaims:
    """
    access 토큰을 검증하고 그 안의 값을 돌려준다.

    토큰이 틀렸으면 InvalidTokenError.
    키를 구할 수 없어 맞는지 틀린지 알 수 없으면 JwksUnavailableError 가 그대로 올라간다.
    """
    key_id = read_key_id(token)
    try:
        key = await jwks.get_key(key_id)
    except UnknownKeyError as error:
        raise InvalidTokenError from error

    claims = decode_claims(token, key, settings)
    return build_access_claims(claims)
