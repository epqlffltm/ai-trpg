# game-server/tests/signing.py

"""
테스트가 인증 서버 흉내를 낼 때 쓰는 도구. 서명 키를 만들고, 키 목록(JWKS)을 내주는 가짜 서버를 만든다.

실제 인증 서버를 띄우지 않는다. 인증 서버가 죽었을 때, 키를 바꿨을 때 같은 상황을 마음대로 만들 수 있다.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from app.auth.tokens import AccessClaims

# 테스트용 키의 길이. 짧을수록 빨리 만들어진다. 실제 서비스의 키는 인증 서버가 만든다
TEST_KEY_BITS = 2048

# 테스트용 토큰의 주인
TEST_USER_ID = uuid.UUID('11111111-2222-4333-8444-555555555555')

# 인증 서버의 access 토큰 수명과 같다
ACCESS_TOKEN_SECONDS = 15 * 60


@dataclass
class SigningKey:
    """서명 키 하나. 개인키로 토큰에 서명하고, jwk 는 키 목록에 싣는 공개키다."""

    kid: str
    private_key: rsa.RSAPrivateKey
    jwk: dict


def make_signing_key(kid: str) -> SigningKey:
    """새 서명 키를 만든다. 인증 서버가 내보내는 것과 같은 모양의 JWK 를 함께 만든다."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=TEST_KEY_BITS)
    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk.update({'kid': kid, 'use': 'sig', 'alg': 'RS256'})
    return SigningKey(kid=kid, private_key=private_key, jwk=jwk)


def make_token(key: SigningKey, claims: dict, headers: dict | None = None) -> str:
    """주어진 키로 서명한 토큰을 만든다. 인증 서버처럼 머리말에 kid 를 넣는다."""
    token_headers = {'kid': key.kid}
    token_headers.update(headers or {})
    return jwt.encode(claims, key.private_key, algorithm='RS256', headers=token_headers)


def make_access_claims(**overrides) -> dict:
    """인증 서버가 access 토큰에 넣는 것과 같은 값. 테스트가 일부만 바꿔서 쓴다."""
    now = int(time.time())
    claims = {
        'token_type': 'access',
        'sub': str(TEST_USER_ID),
        'iss': 'ai-trpg-auth',
        'aud': ['ai-trpg-auth', 'ai-trpg-game'],
        'iat': now,
        'exp': now + ACCESS_TOKEN_SECONDS,
        'jti': uuid.uuid4().hex,
    }
    claims.update(overrides)
    return claims


def make_viewer(user_id: uuid.UUID, seconds: float = ACCESS_TOKEN_SECONDS) -> AccessClaims:
    """
    검증을 마친 토큰의 값을 직접 만든다. 서비스를 API 없이 부르는 테스트가 쓴다.

    seconds 는 지금부터 만료까지의 시간이다. 음수를 주면 이미 만료된 것이 된다.
    """
    return AccessClaims(user_id=user_id, expires_at=datetime.now(UTC) + timedelta(seconds=seconds))


@dataclass
class FakeAuthServer:
    """
    키 목록을 내주는 가짜 인증 서버.

    keys 를 바꾸면 키를 교체한 것이고, down 을 켜면 죽은 것이다. 몇 번 불렸는지 센다.
    """

    keys: list[SigningKey] = field(default_factory=list)
    down: bool = False
    calls: int = 0

    async def handle(self, request: httpx.Request) -> httpx.Response:
        """요청 하나에 답한다. httpx 가 네트워크 대신 이 함수를 부른다."""
        self.calls += 1
        # 실제 네트워크처럼 응답을 기다리는 틈을 만든다. 이 틈에 다른 요청이 끼어든다.
        # 틈이 없으면 요청이 하나씩 차례로 끝나서, 동시에 올 때의 문제가 드러나지 않는다
        await asyncio.sleep(0)
        if self.down:
            raise httpx.ConnectError('연결할 수 없다', request=request)
        return httpx.Response(200, json={'keys': [key.jwk for key in self.keys]})

    def make_client(self) -> httpx.AsyncClient:
        """이 가짜 서버로 요청이 가는 클라이언트를 만든다."""
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))
