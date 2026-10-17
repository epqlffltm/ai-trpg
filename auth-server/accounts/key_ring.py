# auth-server/accounts/key_ring.py

"""
JWT 를 서명하고 검증하는 키들(#21). 토큰을 만드는 곳(tokens.py)과 JWKS(jwks.py)는 키를 이 모듈에서만 얻는다.

지금은 설정(파일)에서 읽는다. 서명 키 하나와, 검증만 하는 공개키 여럿이다.
키를 DB 에 두고 다시 띄우지 않고 바꾸는 방식으로 옮기게 되면 current_key_ring 하나만 바꾼다.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class SigningKeyUnavailableError(ImproperlyConfigured):
    """
    이 프로세스에는 서명 키가 없다(JWT_PRIVATE_KEY_PATH 가 비었다).

    워커와 마이그레이션은 서명하지 않으므로 키를 받지 않는다(#274).
    그런 프로세스가 토큰을 만들거나 JWKS 를 내려 하면 이 오류다.
    설정이 틀린 것이라 ImproperlyConfigured 로 둔다.
    """


@dataclass(frozen=True)
class KeyRing:
    """지금 쓰는 키들."""

    # 새 토큰에 서명하는 키의 ID 와 개인키 PEM
    signing_key_id: str
    signing_key_pem: str
    # 받은 토큰을 검증할 수 있는 공개키들. 키 ID → 공개키 PEM. 서명 키가 맨 앞이다
    verification_keys: Mapping[str, str]

    def verification_key(self, key_id: str | None) -> str | None:
        """그 키 ID 의 공개키. 모르는 ID 면 None 이다."""
        if key_id is None:
            return None
        return self.verification_keys.get(key_id)


def has_signing_key() -> bool:
    """이 프로세스가 서명 키를 가졌는지 본다."""
    return settings.JWT_SIGNING_KEY_PEM is not None


def require_signing_key() -> None:
    """
    서명 키가 없으면 SigningKeyUnavailableError 를 낸다.
    요청을 받는 서버의 입구(config/wsgi.py, config/asgi.py)가 뜰 때 부른다.

    키 없이 뜬 서버는 첫 로그인에서야 실패한다. 뜰 때 막아 설정이 틀린 것을 바로 드러낸다.
    """
    if not has_signing_key():
        raise SigningKeyUnavailableError(
            'JWT 서명 키가 없습니다. 요청을 받는 서버는 JWT_PRIVATE_KEY_PATH 에 개인키의 경로가 있어야 합니다.'
        )


def current_key_ring() -> KeyRing:
    """
    지금 쓰는 키들을 설정에서 읽는다. 부를 때마다 읽으므로 테스트가 설정을 바꿔 교체를 흉내 낼 수 있다.

    서명 키가 없는 프로세스면 SigningKeyUnavailableError 다. 키 없이 서명하거나 빈 JWKS 를 내지 않는다.
    """
    require_signing_key()
    return KeyRing(
        signing_key_id=settings.JWT_KEY_ID,
        signing_key_pem=settings.JWT_SIGNING_KEY_PEM,
        verification_keys=settings.JWT_VERIFICATION_KEYS,
    )
