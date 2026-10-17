# auth-server/config/jwt_keys.py

"""
JWT 서명 키를 읽고, 거기서 공개키와 키 ID 를 만든다. 검증에만 쓰는 공개키(옛 키, 다음 키)도 읽는다(#21).

settings.py 가 기동할 때 한 번 호출한다. Django 모델이나 설정을 import 하지 않는다.
설정을 읽는 도중에 불리는 코드가 설정에 의존하면 순환 참조가 생긴다.
"""

import hashlib
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from django.core.exceptions import ImproperlyConfigured

# 키 ID 로 쓸 해시의 길이. 키를 구별하는 이름표라서 전체 해시가 필요하지 않다
KEY_ID_LENGTH = 16


def read_private_key_pem(path: Path) -> str:
    """개인키 파일을 읽는다. 없으면 만드는 방법과 함께 기동을 거부한다."""
    try:
        return path.read_text(encoding='ascii')
    except FileNotFoundError as exc:
        raise ImproperlyConfigured(
            f'JWT 개인키 파일이 없습니다: {path}\n다음 명령으로 만드세요: uv run python scripts/generate_jwt_key.py'
        ) from exc


def derive_public_key_pem(private_key_pem: str) -> str:
    """
    개인키에서 공개키를 계산한다.

    서명 키의 공개키를 파일로 따로 두지 않는다. 두 파일이 서로 다른 키 쌍이 되는 실수가 생기지 않는다.
    """
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode('ascii'),
        password=None,
    )
    return canonical_public_key_pem(private_key.public_key())


def canonical_public_key_pem(public_key) -> str:
    """
    공개키를 늘 같은 모양의 PEM 으로 쓴다. 키 ID 는 이 글자에서 계산한다.

    파일에서 읽은 글자를 그대로 쓰지 않는다. 같은 키라도 줄바꿈(윈도우의 CRLF)이나 빈 줄이 다르면
    키 ID 가 달라져, 그 키로 서명한 토큰을 알아보지 못한다.
    """
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode('ascii')


def read_public_key_pem(path: Path) -> str:
    """
    검증에만 쓰는 공개키 파일을 읽어 늘 같은 모양의 PEM 으로 돌려준다.

    없거나 공개키가 아니면(개인키를 잘못 넣은 것도) 기동을 거부한다.
    옛 개인키를 남겨 두지 않으려고 공개키만 받는다.
    """
    try:
        text = path.read_text(encoding='ascii')
    except FileNotFoundError as exc:
        raise ImproperlyConfigured(f'JWT 공개키 파일이 없습니다: {path}') from exc
    try:
        public_key = serialization.load_pem_public_key(text.encode('ascii'))
    except ValueError as exc:
        raise ImproperlyConfigured(
            f'JWT 공개키 파일이 아닙니다(개인키이거나 다른 형식): {path}\n'
            '개인키에서 공개키를 꺼내려면: uv run python scripts/export_jwt_public_key.py <개인키> <공개키>'
        ) from exc
    return canonical_public_key_pem(public_key)


def build_verification_keys(signing_public_key_pem: str, extra_paths: list[Path]) -> dict[str, str]:
    """
    토큰을 검증할 수 있는 공개키들을 키 ID → 공개키 PEM 으로 모은다. 서명 키가 맨 앞이다.

    extra_paths 는 서명하지 않고 검증만 하는 공개키다. 교체하는 동안의 옛 키와 미리 알릴 다음 키가 여기에 든다.
    같은 키가 두 번 들어 있으면(서명 키와 같은 것도) 기동을 거부한다. 설정을 잘못 고친 것이다.
    """
    keys = {compute_key_id(signing_public_key_pem): signing_public_key_pem}
    for path in extra_paths:
        pem = read_public_key_pem(path)
        key_id = compute_key_id(pem)
        if key_id in keys:
            raise ImproperlyConfigured(f'같은 JWT 키가 두 번 들어 있습니다: {path} (kid {key_id})')
        keys[key_id] = pem
    return keys


def compute_key_id(public_key_pem: str) -> str:
    """
    공개키의 해시로 키 ID(kid)를 만든다.

    이름을 사람이 정하지 않고 키 내용에서 계산한다.
    키를 바꾸면 ID 도 자동으로 바뀌어, 옛 키와 새 키가 같은 ID 를 갖는 일이 없다.
    """
    digest = hashlib.sha256(public_key_pem.encode('ascii')).hexdigest()
    return digest[:KEY_ID_LENGTH]
