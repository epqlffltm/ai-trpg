# auth-server/scripts/export_jwt_public_key.py

"""
JWT 개인키에서 공개키를 꺼내 파일로 저장하고, 두 키의 키 ID(kid)를 찍는다(#21).

키를 교체할 때 쓴다. 옛 개인키의 공개키만 남겨 검증에 쓰고, 옛 개인키는 지울 수 있게 한다.
새 키를 미리 알릴 때도 새 개인키의 공개키를 이것으로 꺼낸다.
Django 설정을 읽지 않는다. 설정이 키 파일을 필요로 하므로, 키를 다루는 도구가 설정에 의존하면 키가 없을 때 쓸 수 없다.

    uv run python scripts/export_jwt_public_key.py keys/jwt-private.pem keys/jwt-public-2026-10-17.pem
"""

import sys
from pathlib import Path

# config 패키지(키 ID 의 계산)를 읽으려고 auth-server 폴더를 찾는 길에 넣는다. 서버와 같은 계산을 써야 kid 가 맞는다
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.jwt_keys import compute_key_id, derive_public_key_pem  # noqa: E402


def write_new_file(path: Path, content: str) -> None:
    """파일을 새로 만든다. 이미 있으면 실패한다. 다른 키를 덮어쓰면 그 키로 서명한 토큰을 검증할 수 없게 된다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='ascii', newline='\n') as public_file:
        public_file.write(content)


def main() -> int:
    if len(sys.argv) != 3:
        print('쓰는 법: uv run python scripts/export_jwt_public_key.py <개인키 파일> <공개키 파일>', file=sys.stderr)
        return 2
    private_path, public_path = Path(sys.argv[1]), Path(sys.argv[2])
    try:
        public_key_pem = derive_public_key_pem(private_path.read_text(encoding='ascii'))
        write_new_file(public_path, public_key_pem)
    except FileNotFoundError:
        print(f'개인키 파일이 없습니다: {private_path}', file=sys.stderr)
        return 1
    except FileExistsError:
        print(f'이미 파일이 있습니다: {public_path}. 다른 경로를 지정하세요.', file=sys.stderr)
        return 1
    except ValueError:
        print(f'개인키 파일이 아닙니다: {private_path}', file=sys.stderr)
        return 1
    print(f'공개키를 저장했습니다: {public_path} (kid {compute_key_id(public_key_pem)})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
