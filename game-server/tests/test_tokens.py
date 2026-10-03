# game-server/tests/test_tokens.py

"""
access 토큰의 검증을 검증한다. 받아야 할 토큰을 받고, 받으면 안 되는 토큰을 거부하는가.
"""

import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization

from app.auth.jwks import JwksCache, JwksUnavailableError
from app.auth.tokens import CLOCK_SKEW_SECONDS, AccessClaims, InvalidTokenError, verify_access_token
from app.core.config import Settings
from tests.conftest import TEST_JWKS_URL, make_test_settings
from tests.signing import TEST_USER_ID, FakeAuthServer, SigningKey, make_access_claims, make_signing_key, make_token


@pytest.fixture(scope='module')
def key() -> SigningKey:
    """인증 서버의 키."""
    return make_signing_key('key-1')


@pytest.fixture(scope='module')
def attacker_key() -> SigningKey:
    """인증 서버의 것이 아닌 키. 같은 kid 를 자칭한다."""
    return make_signing_key('key-1')


@pytest.fixture
def auth_server(key: SigningKey) -> FakeAuthServer:
    return FakeAuthServer(keys=[key])


@pytest.fixture
def jwks(auth_server: FakeAuthServer) -> JwksCache:
    return JwksCache(auth_server.make_client(), TEST_JWKS_URL)


@pytest.fixture
def settings() -> Settings:
    return make_test_settings()


async def verify(token: str, jwks: JwksCache, settings: Settings) -> AccessClaims:
    return await verify_access_token(token, jwks, settings)


# --- 받아야 하는 토큰 ---


async def test_accepts_a_token_from_the_auth_server(key: SigningKey, jwks: JwksCache, settings: Settings):
    token = make_token(key, make_access_claims())

    claims = await verify(token, jwks, settings)

    assert claims.user_id == TEST_USER_ID


async def test_accepts_a_small_clock_difference(key: SigningKey, jwks: JwksCache, settings: Settings):
    # 인증 서버의 시계가 조금 빨라서, 발급 시각이 이 서버에게는 미래다
    token = make_token(key, make_access_claims(iat=int(time.time()) + CLOCK_SKEW_SECONDS - 5))

    claims = await verify(token, jwks, settings)

    assert claims.user_id == TEST_USER_ID


# --- 서명 ---


async def test_rejects_a_token_signed_with_another_key(attacker_key: SigningKey, jwks: JwksCache, settings: Settings):
    # kid 는 인증 서버의 것과 같게 적었지만 서명한 키가 다르다
    token = make_token(attacker_key, make_access_claims())

    with pytest.raises(InvalidTokenError):
        await verify(token, jwks, settings)


async def test_rejects_a_token_whose_content_was_changed(key: SigningKey, jwks: JwksCache, settings: Settings):
    header, _, signature = make_token(key, make_access_claims()).split('.')
    forged_payload = encode_segment(make_access_claims(sub='99999999-2222-4333-8444-555555555555'))

    with pytest.raises(InvalidTokenError):
        await verify(f'{header}.{forged_payload}.{signature}', jwks, settings)


async def test_rejects_an_unsigned_token(jwks: JwksCache, settings: Settings):
    # 서명 방식을 none 이라고 적고 서명을 비운 토큰
    header = encode_segment({'alg': 'none', 'typ': 'JWT', 'kid': 'key-1'})
    token = f'{header}.{encode_segment(make_access_claims())}.'

    with pytest.raises(InvalidTokenError):
        await verify(token, jwks, settings)


async def test_rejects_a_token_signed_with_the_public_key_as_a_secret(
    key: SigningKey, jwks: JwksCache, settings: Settings
):
    # 공개키는 누구나 가져갈 수 있다. 그것을 비밀키처럼 써서 HS256 으로 서명한 토큰.
    # 서명 방식을 토큰이 적어 온 대로 믿는 서버는 공개키로 이 서명을 확인하고 통과시킨다
    public_key = key.private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    header = encode_segment({'alg': 'HS256', 'typ': 'JWT', 'kid': key.kid})
    signed_part = f'{header}.{encode_segment(make_access_claims())}'
    signature = hmac.new(public_key, signed_part.encode(), hashlib.sha256).digest()
    token = f'{signed_part}.{encode_bytes(signature)}'

    with pytest.raises(InvalidTokenError):
        await verify(token, jwks, settings)


async def test_rejects_a_token_without_a_kid(key: SigningKey, jwks: JwksCache, settings: Settings):
    token = jwt.encode(make_access_claims(), key.private_key, algorithm='RS256')

    with pytest.raises(InvalidTokenError):
        await verify(token, jwks, settings)


async def test_rejects_a_token_with_an_unknown_kid(key: SigningKey, jwks: JwksCache, settings: Settings):
    token = make_token(key, make_access_claims(), headers={'kid': 'no-such-key'})

    with pytest.raises(InvalidTokenError):
        await verify(token, jwks, settings)


@pytest.mark.parametrize('token', ['', 'not-a-token', 'a.b', 'a.b.c', '....'])
async def test_rejects_text_that_is_not_a_token(token: str, jwks: JwksCache, settings: Settings):
    with pytest.raises(InvalidTokenError):
        await verify(token, jwks, settings)


# --- 토큰 안의 값 ---


async def test_rejects_an_expired_token(key: SigningKey, jwks: JwksCache, settings: Settings):
    token = make_token(key, make_access_claims(exp=int(time.time()) - CLOCK_SKEW_SECONDS - 1))

    with pytest.raises(InvalidTokenError):
        await verify(token, jwks, settings)


async def test_rejects_a_token_from_another_issuer(key: SigningKey, jwks: JwksCache, settings: Settings):
    token = make_token(key, make_access_claims(iss='someone-else'))

    with pytest.raises(InvalidTokenError):
        await verify(token, jwks, settings)


async def test_rejects_a_token_meant_for_another_server(key: SigningKey, jwks: JwksCache, settings: Settings):
    # 서명도 발급자도 맞지만, 이 서버에 쓰라고 발급한 토큰이 아니다
    token = make_token(key, make_access_claims(aud=['ai-trpg-auth']))

    with pytest.raises(InvalidTokenError):
        await verify(token, jwks, settings)


async def test_rejects_a_refresh_token(key: SigningKey, jwks: JwksCache, settings: Settings):
    # refresh 토큰도 같은 키로 서명된다. 수명이 14일이라, 받아 주면 access 토큰을 짧게 잡은 의미가 없다
    token = make_token(key, make_access_claims(token_type='refresh'))

    with pytest.raises(InvalidTokenError):
        await verify(token, jwks, settings)


@pytest.mark.parametrize('missing', ['exp', 'iss', 'aud', 'sub', 'token_type'])
async def test_rejects_a_token_missing_a_required_value(
    missing: str, key: SigningKey, jwks: JwksCache, settings: Settings
):
    claims = make_access_claims()
    del claims[missing]

    # 값이 없으면 확인을 건너뛰는 것이 아니라 거부한다
    with pytest.raises(InvalidTokenError):
        await verify(make_token(key, claims), jwks, settings)


@pytest.mark.parametrize('subject', ['not-a-uuid', '', 123])
async def test_rejects_a_subject_that_is_not_a_user_id(
    subject: object, key: SigningKey, jwks: JwksCache, settings: Settings
):
    token = make_token(key, make_access_claims(sub=subject))

    with pytest.raises(InvalidTokenError):
        await verify(token, jwks, settings)


# --- 인증 서버가 죽었을 때 ---


async def test_unavailable_is_not_reported_as_an_invalid_token(
    key: SigningKey, auth_server: FakeAuthServer, jwks: JwksCache, settings: Settings
):
    auth_server.down = True
    token = make_token(key, make_access_claims())

    # 토큰이 틀린 것과 확인할 수 없는 것은 다르다. 앞의 것은 401, 뒤의 것은 503 이 된다
    with pytest.raises(JwksUnavailableError):
        await verify(token, jwks, settings)


def encode_segment(value: dict) -> str:
    """토큰의 한 부분을 손으로 만든다. 라이브러리가 만들어 주지 않는 이상한 토큰을 꾸밀 때 쓴다."""
    return encode_bytes(json.dumps(value).encode())


def encode_bytes(raw: bytes) -> str:
    """토큰이 쓰는 방식(끝의 = 를 뗀 base64url)으로 바꾼다."""
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()
