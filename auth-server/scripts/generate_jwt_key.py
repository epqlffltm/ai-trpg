# auth-server/scripts/generate_jwt_key.py

"""
JWT 서명용 RSA 개인키를 만들어 파일로 저장한다.

Django 설정을 읽지 않는 독립 스크립트다. 설정이 이 키 파일을 필요로 하므로,
키를 만드는 도구가 설정에 의존하면 처음에는 실행할 수 없다.

    uv run python scripts/generate_jwt_key.py
    uv run python scripts/generate_jwt_key.py keys/other.pem
"""

import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

DEFAULT_KEY_PATH = Path('keys/jwt-private.pem')

# 2048비트는 RS256 에서 쓰는 최소 권장 길이다
KEY_SIZE_BITS = 2048
PUBLIC_EXPONENT = 65537


def generate_private_key_pem() -> bytes:
    """RSA 개인키를 만들어 PEM 형식의 바이트로 돌려준다."""
    private_key = rsa.generate_private_key(
        public_exponent=PUBLIC_EXPONENT,
        key_size=KEY_SIZE_BITS,
    )
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def write_new_file(path: Path, content: bytes) -> None:
    """
    파일을 새로 만든다. 이미 있으면 실패한다.

    키를 덮어쓰면 그 키로 서명한 토큰이 전부 무효가 된다. 실수로 덮어쓰지 못하게 한다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # 'x' 모드는 파일이 이미 있으면 FileExistsError 를 낸다
    with path.open('xb') as key_file:
        key_file.write(content)


def main() -> int:
    key_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_KEY_PATH
    try:
        write_new_file(key_path, generate_private_key_pem())
    except FileExistsError:
        print(f'이미 키 파일이 있습니다: {key_path}', file=sys.stderr)
        print('새로 만들려면 기존 파일을 직접 지우거나 다른 경로를 지정하세요.', file=sys.stderr)
        return 1
    print(f'개인키를 만들었습니다: {key_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())