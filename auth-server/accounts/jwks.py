# auth-server/accounts/jwks.py

"""
공개키를 JWKS(JSON Web Key Set) 형식으로 만든다.

다른 서버는 이 목록에서 공개키를 가져가 토큰의 서명을 검증한다.
개인키는 여기에 실리지 않는다.
"""

from cryptography.hazmat.primitives import serialization
from django.conf import settings
from jwt.algorithms import RSAAlgorithm


def build_jwk(public_key_pem: str, key_id: str) -> dict:
    """PEM 형식의 공개키 하나를 JWK 로 바꾼다."""
    public_key = serialization.load_pem_public_key(public_key_pem.encode('ascii'))
    # kty, n, e 를 채워 준다
    jwk = RSAAlgorithm.to_jwk(public_key, as_dict=True)
    jwk.update({
        # 토큰 머리말의 kid 와 같은 값. 검증하는 쪽이 이 값으로 키를 고른다
        'kid': key_id,
        # 이 키는 서명 검증용이다
        'use': 'sig',
        'alg': settings.SIMPLE_JWT['ALGORITHM'],
    })
    return jwk


def build_jwks() -> dict:
    """
    지금 쓰는 공개키를 담은 JWKS 를 돌려준다.

    keys 가 목록인 것은 키를 교체하는 동안 옛 키와 새 키를 함께 내보내기 위해서다.
    지금은 키가 하나다.
    """
    return {
        'keys': [
            build_jwk(settings.JWT_PUBLIC_KEY_PEM, settings.JWT_KEY_ID),
        ],
    }