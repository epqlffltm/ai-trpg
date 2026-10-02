# auth-server/config/jwt_keys.py

"""
JWT 서명 키를 읽고, 거기서 공개키와 키 ID 를 만든다.

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
            f'JWT 개인키 파일이 없습니다: {path}\n'
            '다음 명령으로 만드세요: uv run python scripts/generate_jwt_key.py'
        ) from exc


def derive_public_key_pem(private_key_pem: str) -> str:
    """
    개인키에서 공개키를 계산한다.

    공개키를 파일로 따로 두지 않는다. 두 파일이 서로 다른 키 쌍이 되는 실수가 생기지 않는다.
    """
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode('ascii'),
        password=None,
    )
    public_key_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return public_key_bytes.decode('ascii')


def compute_key_id(public_key_pem: str) -> str:
    """
    공개키의 해시로 키 ID(kid)를 만든다.

    이름을 사람이 정하지 않고 키 내용에서 계산한다.
    키를 바꾸면 ID 도 자동으로 바뀌어, 옛 키와 새 키가 같은 ID 를 갖는 일이 없다.
    """
    digest = hashlib.sha256(public_key_pem.encode('ascii')).hexdigest()
    return digest[:KEY_ID_LENGTH]