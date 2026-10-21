# tools/export_openapi.py

"""
서버마다의 OpenAPI(서버가 받는 요청과 돌려주는 응답의 목록)를 뽑아 docs/api/ 에 파일로 둔다(#557).
표준 라이브러리만 쓴다.

화면의 타입과 디자인 도구(Stitch)에 넘길 API 목록이 이 파일들이다(docs/api/README.md).
운영 서버는 /docs 와 /openapi.json 을 열지 않는다. 목록은 저장소의 파일로만 나간다.

하는 일:
  1. 서버마다 OpenAPI 를 JSON 으로 받는다. 서버를 띄우지 않고 DB 에도 닿지 않는다.
     FastAPI 서버는 그 서버의 환경(uv 의 가상 환경)에서 앱을 불러 받는다.
     결제 서버(Go)는 손으로 쓴 목록(billing-server/api/openapi.yaml)을 그 서버의 명령이 읽고 검사해 JSON 으로 낸다.
     게시판 서버(NestJS)는 빌드한 뒤 앱을 미리 보기로 만들어 낸다(npm run openapi). npm ci 를 먼저 해 두어야 한다.
  2. 주소마다 누가 부르는 것인지를 적는다(x-audience: user, service, operator, webhook, infra).
     화면은 user 만 부른다. 서버끼리만 부르는 주소(/service/)를 화면이 부르지 않게 하려고다.
     서버가 이미 적은 표시는 그대로 둔다.
     게시판의 운영자 API(신고 처리, 글 고정)는 주소에 /admin/ 이 없어서 서버가 적는다.
  3. 키의 차례를 정해 같은 내용이면 늘 같은 글이 되게 쓴다. CI 가 글을 견주어 본다.

쓰는 법(저장소 루트에서):
  uv run --no-project python tools/export_openapi.py              # 모든 서버의 파일을 새로 쓴다
  uv run --no-project python tools/export_openapi.py trpg         # 한 서버만
  uv run --no-project python tools/export_openapi.py --check      # 쓰지 않고 파일이 지금의 서버와 같은지만 본다(CI)

서버를 더할 때는 아래의 표(SOURCES)에 그 서버의 폴더와 OpenAPI 를 표준 출력에 내는 명령을 적는다.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# 파일을 두는 곳. 서버마다 <이름>.openapi.json 하나다
API_DIR = Path('docs/api')

# FastAPI 서버의 앱을 불러 OpenAPI 를 표준 출력에 내는 코드. app.main 이 불릴 때 앱을 만든다.
# 로그는 표준 에러로 간다(docs/observability.md). 표준 출력에는 JSON 만 나간다
FASTAPI_SNIPPET = 'import json, sys; from app.main import app; json.dump(app.openapi(), sys.stdout)'

# 앱을 불러오는 데 꼭 있어야 하는 설정. 값이 없으면 설정을 읽다가 멈춘다.
# 앱을 만들기만 하고 띄우지 않으므로 이 주소로는 아무 요청도 가지 않는다. 개발자가 적어 둔 값이 있으면 그대로 쓴다
FASTAPI_REQUIRED_ENV = {
    'DATABASE_URL': 'postgresql+asyncpg://openapi:openapi@127.0.0.1:1/openapi',
    'AUTH_JWKS_URL': 'http://127.0.0.1:1/api/v1/auth/jwks',
}

# 인증 서버(Django REST framework)가 뷰에 적은 모양으로 목록을 만들어 표준 출력에 내는 명령(drf-spectacular).
# 경고가 하나라도 있으면(모양을 적지 않은 뷰) 실패한다. 목록의 모양도 OpenAPI 의 규칙으로 검사한다
DJANGO_COMMAND = (
    'uv',
    'run',
    '--frozen',
    '--quiet',
    'python',
    'manage.py',
    'spectacular',
    '--format',
    'openapi-json',
    '--validate',
    '--fail-on-warn',
)

# 인증 서버의 설정을 읽는 데 꼭 있어야 하는 값. 목록을 만들기만 하므로 DB 에 닿지 않고 서명하지 않는다.
# 서명 키의 경로를 비워 키 없이 뜬다(서명하지 않는 프로세스와 같다). CI 에는 키가 없다.
# DEBUG 를 끈다. 개발자의 .env 가 켜 둬도 운영과 같은 목록이 나온다(.env 는 이미 있는 환경 변수를 덮지 않는다)
DJANGO_REQUIRED_ENV = {
    'SECRET_KEY': 'openapi-export-only-not-a-secret',
    'DATABASE_URL': 'postgres://openapi:openapi@127.0.0.1:1/openapi',
    'JWT_PRIVATE_KEY_PATH': '',
    'DEBUG': 'false',
}

# 결제 서버가 손으로 쓴 목록을 읽고 검사해 OpenAPI 를 표준 출력에 내는 명령(billing-server/cmd/openapi).
# 파이썬의 표준 라이브러리로는 YAML 을 읽지 못해서 서버의 Go 로 읽는다. 목록의 검사도 서버의 테스트와 같은 것을 쓴다
GO_COMMAND = ('go', 'run', './cmd/openapi')

# 게시판 서버를 빌드하고 OpenAPI 를 표준 출력에 내는 명령(board-server/src/openapi/export.ts).
# 응답의 칸은 빌드할 때 @nestjs/swagger 의 플러그인이 읽어 두므로 빌드가 먼저다.
# --silent 는 npm 의 머리글이 표준 출력에 섞이지 않게 한다
NEST_COMMAND = ('npm', 'run', '--silent', 'openapi')

# 게시판 서버가 설정을 읽는 데 꼭 있어야 하는 값. FastAPI 와 같은 생각이다. 주소의 모양만 Node 의 pg 에 맞다
NEST_REQUIRED_ENV = {
    'DATABASE_URL': 'postgresql://openapi:openapi@127.0.0.1:1/openapi',
    'AUTH_JWKS_URL': 'http://127.0.0.1:1/api/v1/auth/jwks',
}

# 주소의 모양으로 누가 부르는지를 정한다. 위에서부터 맞춰 보고, 맞는 것이 없으면 사용자(화면)다
AUDIENCE_RULES = (
    ('/health', 'infra'),
    ('/service/', 'service'),
    ('/admin/', 'operator'),
    ('/webhooks/', 'webhook'),
)
DEFAULT_AUDIENCE = 'user'

# 주소 한 칸 아래에서 요청의 방식(operation)인 키
HTTP_METHODS = frozenset({'get', 'put', 'post', 'delete', 'patch', 'head', 'options', 'trace'})


@dataclass(frozen=True)
class Source:
    """서버 하나의 OpenAPI 를 어디서 어떻게 뽑는가. command 는 folder 에서 돌리고, 표준 출력이 OpenAPI 의 JSON 이다."""

    folder: str
    command: tuple[str, ...]
    env: tuple[tuple[str, str], ...] = ()


def fastapi_source(folder: str) -> Source:
    """FastAPI 서버의 Source. 그 서버의 uv 가상 환경에서 앱을 불러온다(uv.lock 그대로, --frozen)."""
    return Source(
        folder=folder,
        command=('uv', 'run', '--frozen', '--quiet', 'python', '-c', FASTAPI_SNIPPET),
        env=tuple(FASTAPI_REQUIRED_ENV.items()),
    )


def django_source(folder: str) -> Source:
    """Django 서버의 Source. 그 서버의 uv 가상 환경에서 manage.py spectacular 를 돌린다."""
    return Source(folder=folder, command=DJANGO_COMMAND, env=tuple(DJANGO_REQUIRED_ENV.items()))


def go_source(folder: str) -> Source:
    """Go 서버의 Source. 그 서버의 go.mod 그대로 명령을 돌린다. 설정은 읽지 않는다."""
    return Source(folder=folder, command=GO_COMMAND)


def nest_source(folder: str) -> Source:
    """NestJS 서버의 Source. 그 서버의 npm 명령으로 빌드하고 목록을 낸다. 의존성(npm ci)은 받아 두었어야 한다."""
    return Source(folder=folder, command=NEST_COMMAND, env=tuple(NEST_REQUIRED_ENV.items()))


# OpenAPI 를 내는 서버들
SOURCES: dict[str, Source] = {
    'trpg': fastapi_source('trpg-server'),
    'notification': fastapi_source('notification-server'),
    'billing': go_source('billing-server'),
    'asset': fastapi_source('asset-server'),
    'auth': django_source('auth-server'),
    'board': nest_source('board-server'),
}


def audience_of(path: str) -> str:
    """주소 하나를 누가 부르는가."""
    for marker, audience in AUDIENCE_RULES:
        if marker in path:
            return audience
    return DEFAULT_AUDIENCE


def mark_audience(spec: dict) -> dict:
    """주소마다의 요청 방식에 x-audience 를 적는다. 서버가 적어 둔 것은 그대로 둔다. 받은 것을 고쳐 돌려준다."""
    for path, operations in spec.get('paths', {}).items():
        audience = audience_of(path)
        for method, operation in operations.items():
            if method in HTTP_METHODS:
                operation.setdefault('x-audience', audience)
    return spec


def render(spec: dict) -> str:
    """파일에 쓸 글. 키를 정렬하고 들여쓰고 한글을 그대로 둔다. 끝에 줄바꿈 하나."""
    return json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def command_env(source: Source) -> dict[str, str]:
    """명령을 돌릴 환경 변수. 지금의 환경에, 비어 있는 꼭 필요한 설정만 채운다."""
    env = dict(os.environ)
    for name, value in source.env:
        env.setdefault(name, value)
    return env


def resolve_command(command: tuple[str, ...]) -> tuple[str, ...]:
    """명령의 첫 이름을 실행 파일의 경로로 바꾼다. 찾지 못하면 그대로 둔다.

    Windows 의 npm 은 npm.cmd 다. 경로 없이 'npm' 만 주면 subprocess 가 찾지 못한다.
    """
    program, *rest = command
    return (shutil.which(program) or program, *rest)


def failure_output(result: subprocess.CompletedProcess) -> str:
    """실패한 명령이 남긴 글. 표준 에러를 먼저, 그다음 표준 출력이다.

    게시판 서버의 빌드(tsc)는 타입 오류를 표준 출력에 낸다. 표준 에러만 실으면 까닭이 빠진다.
    """
    parts = (result.stderr.strip(), result.stdout.strip())
    return '\n'.join(part for part in parts if part)


def fetch_spec(source: Source, root: Path) -> dict:
    """서버의 환경에서 명령을 돌려 OpenAPI 를 받는다. 실패하면 그 서버가 남긴 글을 실어 멈춘다."""
    result = subprocess.run(
        resolve_command(source.command),
        cwd=root / source.folder,
        env=command_env(source),
        capture_output=True,
        text=True,
        encoding='utf-8',
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f'{source.folder} 의 OpenAPI 를 뽑지 못했다:\n{failure_output(result)}')
    return json.loads(result.stdout)


def target_path(root: Path, name: str) -> Path:
    """서버 하나의 파일 경로."""
    return root / API_DIR / f'{name}.openapi.json'


def build(name: str, root: Path, fetch: Callable[[Source, Path], dict] = fetch_spec) -> str:
    """서버 하나의 파일에 쓸 글을 만든다."""
    return render(mark_audience(fetch(SOURCES[name], root)))


def is_current(path: Path, text: str) -> bool:
    """파일이 있고 그 글이 지금 만든 것과 같은가."""
    return path.exists() and path.read_text(encoding='utf-8') == text


def write(path: Path, text: str) -> None:
    """파일을 쓴다. 줄바꿈은 어느 PC 에서나 LF 다(CI 가 견줄 때 CRLF 가 섞이지 않게)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='\n') as file:
        file.write(text)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """명령줄의 인자."""
    parser = argparse.ArgumentParser(description='서버마다의 OpenAPI 를 docs/api/ 에 파일로 둔다')
    parser.add_argument('servers', nargs='*', help=f'뽑을 서버({", ".join(SOURCES)}). 비우면 모두')
    parser.add_argument('--check', action='store_true', help='쓰지 않고 파일이 지금의 서버와 같은지만 본다')
    args = parser.parse_args(argv)
    unknown = [name for name in args.servers if name not in SOURCES]
    if unknown:
        parser.error(f'모르는 서버: {", ".join(unknown)}. 아는 서버: {", ".join(SOURCES)}')
    return args


def run(names: list[str], root: Path, check: bool, fetch: Callable[[Source, Path], dict] = fetch_spec) -> int:
    """서버마다 만들어 쓰거나(check 가 거짓) 견준다(참). 다른 것이 있으면 1 을 돌려준다."""
    stale = []
    for name in names:
        text = build(name, root, fetch)
        path = target_path(root, name)
        if is_current(path, text):
            print(f'같다     {path.relative_to(root).as_posix()}')
        elif check:
            stale.append(name)
            print(f'다르다   {path.relative_to(root).as_posix()}')
        else:
            write(path, text)
            print(f'썼다     {path.relative_to(root).as_posix()}')
    if stale:
        print(
            '\n서버의 API 가 바뀌었는데 목록을 새로 뽑지 않았다. 저장소 루트에서 이것을 돌리고 함께 커밋한다:\n'
            f'  uv run --no-project python tools/export_openapi.py {" ".join(stale)}'
        )
        return 1
    return 0


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    names = args.servers or list(SOURCES)
    try:
        return run(names, REPO_ROOT, args.check)
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
