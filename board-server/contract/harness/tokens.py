# board-server/contract/harness/tokens.py

"""
인증 서버가 발급하는 access 토큰과 같은 모양의 토큰을 만든다(auth-server/accounts/tokens.py).

머리말에 kid, 안에는 iss, aud(목록), sub(public_id), exp, token_type, ver, roles 가 있다.
시험은 한 가지씩만 틀리게 바꿔, 그 하나 때문에 거부되는지 본다.
"""

import base64
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

# 서명 방식. 인증 서버와 같다
ALGORITHM = 'RS256'
# 인증 서버의 이름(iss). 게시판 서버의 기본 설정과 같다
ISSUER = 'ai-trpg-auth'
# 게시판 서버의 이름(aud). 게시판 서버의 기본 설정과 같다
AUDIENCE = 'ai-trpg-board'
# 인증 서버가 토큰에 싣는 대상의 목록
AUDIENCES = ['ai-trpg-auth', 'ai-trpg-game', AUDIENCE]
# 운영자의 역할 이름
OPERATOR_ROLE = 'operator'
# 토큰의 수명(초). 인증 서버의 access 토큰과 같다
LIFETIME_SECONDS = 900
# 적지 않았다는 뜻. None 을 일부러 싣는 시험과 가른다
UNSET: Any = object()


@dataclass(frozen=True)
class SigningKey:
    """서명에 쓰는 키 한 벌. 개인키로 서명하고 공개키(JWK)를 공개키 목록에 싣는다."""

    kid: str
    private_key: rsa.RSAPrivateKey

    def jwk(self) -> dict[str, Any]:
        """공개키 목록에 싣는 모양."""
        public = json.loads(RSAAlgorithm.to_jwk(self.private_key.public_key()))
        return {**public, 'kid': self.kid, 'use': 'sig', 'alg': ALGORITHM}


def make_signing_key(kid: str) -> SigningKey:
    """새 RSA 키 한 벌."""
    return SigningKey(kid=kid, private_key=rsa.generate_private_key(public_exponent=65537, key_size=2048))


def new_user_id() -> str:
    """새 사람의 public_id. 시험마다 새 사람을 쓴다(서버가 닉네임을 기억해 두는 것과 섞이지 않게)."""
    return str(uuid.uuid4())


def make_token(
    key: SigningKey,
    subject: str,
    *,
    nickname: str | None = None,
    operator: bool = False,
    roles: Any = UNSET,
    issuer: str = ISSUER,
    audience: Any = UNSET,
    token_type: str = 'access',
    version: int = 1,
    expires_in: int = LIFETIME_SECONDS,
    kid: str | None = None,
) -> str:
    """인증 서버가 발급한 것과 같은 토큰. 적지 않은 것은 맞는 값이다."""
    claims: dict[str, Any] = {
        'token_type': token_type,
        'ver': version,
        'roles': ([OPERATOR_ROLE] if operator else []) if roles is UNSET else roles,
        'iss': issuer,
        'aud': AUDIENCES if audience is UNSET else audience,
        'sub': subject,
        'exp': int(time.time()) + expires_in,
        'jti': uuid.uuid4().hex,
    }
    if nickname is not None:
        claims['nickname'] = nickname
    headers = {'kid': key.kid if kid is None else kid, 'typ': 'JWT'}
    return jwt.encode(claims, key.private_key, algorithm=ALGORITHM, headers=headers)


def forge_token(header: dict[str, Any], claims: dict[str, Any], signature: str = '') -> str:
    """서명 없이 손으로 짠 토큰. 라이브러리가 만들어 주지 않는 틀린 토큰(alg: none 같은 것)을 만든다."""

    def segment(value: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b'=').decode()

    return f'{segment(header)}.{segment(claims)}.{signature}'


def valid_claims(subject: str) -> dict[str, Any]:
    """맞는 토큰의 내용. forge_token 에 넘긴다."""
    return {
        'token_type': 'access',
        'ver': 1,
        'roles': [],
        'iss': ISSUER,
        'aud': AUDIENCES,
        'sub': subject,
        'exp': int(time.time()) + LIFETIME_SECONDS,
    }


def bearer(token: str) -> dict[str, str]:
    """토큰을 싣는 머리말."""
    return {'Authorization': f'Bearer {token}'}
