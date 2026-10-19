# tools/fill_env.py

"""
여섯 개의 .env(루트와 서버 다섯)를 만들고, 비어 있는 비밀을 난수로 채운다. 표준 라이브러리만 쓴다.

하는 일:
  1. .env 가 없으면 그 폴더의 .env.example 을 복사해 만든다.
  2. 아래 표(SECRETS)의 비밀마다, 비었거나 자리표시자(바꿔야합니다, 여기에비밀번호)인 곳을 난수로 채운다.
     두 파일이 함께 아는 비밀(결제 서버의 AUTH_SERVER_SECRET 과 인증 서버의 BILLING_SECRET 등)은 같은 값을 넣는다.
     DB 계정의 비밀번호는 루트 .env 와 그 서버의 DATABASE_URL(postgres://계정:<여기>@…)에 같은 값을 넣는다.
  3. 이미 적힌 값은 바꾸지 않는다. 짝의 한쪽에만 값이 있으면 그 값을 다른 쪽에 옮겨 적는다.
     양쪽의 값이 서로 다르면 고치지 않고 알린다(어느 쪽이 맞는지 이 스크립트는 모른다).
  4. .env.example 에서 주석으로 막아 둔 줄(# BILLING_SECRET=)은 주석인 채로 값만 채운다. 기능을 켜지 않는다.
     # 를 지워 켤 때 짝의 값이 이미 맞아 있다.
  5. .env 에 그 줄이 아예 없으면(.env.example 에 나중에 생긴 줄) .env.example 의 모양(주석인지)대로 끝에 더한다.

비밀의 값은 화면에 찍지 않는다. 무엇을 채웠는지 이름만 찍는다.
결제 대행사, 메일 서버, AI 의 키, S3 의 접근 키처럼 밖에서 받는 키는 채우지 않는다. 그 이름을 따로 알린다.

DB 의 볼륨이 이미 있으면 루트 .env 의 DB 비밀번호를 새로 만들어도 DB 의 계정은 옛 비밀번호 그대로다.
이 스크립트는 적힌 값을 바꾸지 않으므로 평소에는 문제가 없다. .env 를 잃어버렸을 때만 계정의 비밀번호를 다시 맞춘다.

쓰는 법(저장소 루트에서):
  uv run --no-project python tools/fill_env.py            # 만들고 채운다
  uv run --no-project python tools/fill_env.py --dry-run  # 무엇을 할지만 보이고 쓰지 않는다
"""

import argparse
import re
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# 만드는 .env 들. 저장소 루트에서의 경로다
ENV_FILES = (
    '.env',
    'auth-server/.env',
    'game-server/.env',
    'board-server/.env',
    'billing-server/.env',
    'notification-server/.env',
)

# 아직 채우지 않았다는 값. .env.example 이 일부러 넣어 둔 것이다(짧아서 서버가 뜨지 않는다)
PLACEHOLDERS = frozenset({'', '바꿔야합니다', '여기에비밀번호', '여기에_비밀번호'})

# 난수의 바이트 수. 16진수로 적어 64자가 된다. 서버들이 요구하는 32자를 넘고, 주소(DATABASE_URL)에 넣어도 깨지지 않는다
SECRET_BYTES = 32

# .env 의 한 줄. 주석으로 막아 둔 줄(# NAME=값)도 읽는다
LINE = re.compile(r'^(?P<comment>#\s*)?(?P<key>[A-Z][A-Z0-9_]*)=(?P<value>.*?)(?P<newline>\r?\n)?$')
# 접속 주소의 비밀번호 자리. postgres://계정:<비밀번호>@호스트… 의 <비밀번호>다
URL_PASSWORD = re.compile(r'^(?P<head>[a-z][a-z0-9+]*://[^:/@]+:)(?P<password>[^@]*)(?P<tail>@.*)$')
# 비밀처럼 보이는 이름. 표에 없으면 밖에서 받는 키로 알린다(.github/scripts/secret_scope.py 와 같은 규칙)
SECRET_NAME = re.compile(r'SECRET|PASSWORD|API_KEY|HMAC_KEY')
# 이름이 비밀처럼 보이지만 비밀이 아닌 설정
NOT_SECRETS = frozenset({'PASSWORD_RESET_URL'})


@dataclass(frozen=True)
class Spot:
    """비밀이 적히는 자리 하나. url 이면 그 값(접속 주소)의 비밀번호 부분이다."""

    file: str
    key: str
    url: bool = False


@dataclass(frozen=True)
class Secret:
    """같은 값이 들어가는 자리들. 하나만 있으면 그 파일만 아는 비밀이다."""

    name: str
    spots: tuple[Spot, ...]


def database(account: str, root_key: str) -> Secret:
    """DB 계정 하나의 비밀번호. 루트 .env 와 그 서버의 DATABASE_URL 에 같은 값이다."""
    return Secret(
        f'DB 계정 {account}', (Spot('.env', root_key), Spot(f'{account}-server/.env', 'DATABASE_URL', url=True))
    )


def shared(name: str, *spots: tuple[str, str]) -> Secret:
    """파일 여럿이 함께 아는 비밀."""
    return Secret(name, tuple(Spot(file, key) for file, key in spots))


# 채우는 비밀. 비밀을 더하면 여기에 적는다. 짝이 있는 비밀은 한 줄에 함께 적는다
SECRETS = (
    shared('DB 관리 계정', ('.env', 'POSTGRES_PASSWORD')),
    database('auth', 'AUTH_DB_PASSWORD'),
    database('game', 'GAME_DB_PASSWORD'),
    database('board', 'BOARD_DB_PASSWORD'),
    database('billing', 'BILLING_DB_PASSWORD'),
    database('notification', 'NOTIFICATION_DB_PASSWORD'),
    shared('DB 메트릭 계정(monitor)', ('.env', 'MONITOR_DB_PASSWORD')),
    shared('Grafana 관리자', ('.env', 'GRAFANA_ADMIN_PASSWORD')),
    shared('인증 서버의 비밀키', ('auth-server/.env', 'SECRET_KEY')),
    shared(
        '인증 서버 ↔ 결제 서버', ('auth-server/.env', 'BILLING_SECRET'), ('billing-server/.env', 'AUTH_SERVER_SECRET')
    ),
    shared(
        '게임 서버 → 결제 서버', ('game-server/.env', 'BILLING_SECRET'), ('billing-server/.env', 'GAME_SERVER_SECRET')
    ),
    shared('결제 대행사의 알림', ('billing-server/.env', 'PG_WEBHOOK_SECRET')),
    shared(
        '게임 서버 → 알림 서버',
        ('game-server/.env', 'NOTIFICATION_SECRET'),
        ('notification-server/.env', 'GAME_SERVER_SECRET'),
    ),
    shared(
        '결제 서버 → 알림 서버',
        ('billing-server/.env', 'NOTIFICATION_SECRET'),
        ('notification-server/.env', 'BILLING_SERVER_SECRET'),
    ),
    shared(
        '게시판 서버 → 알림 서버',
        ('board-server/.env', 'NOTIFICATION_SECRET'),
        ('notification-server/.env', 'BOARD_SERVER_SECRET'),
    ),
    shared('게임 서버의 실시간 신호', ('game-server/.env', 'SIGNAL_SECRET')),
    shared('게임 서버의 AI 기록 지문', ('game-server/.env', 'AI_LOG_HMAC_KEY')),
)


@dataclass
class EnvFile:
    """.env 하나. 줄을 그대로 들고 있다가 고친 줄만 바꿔 쓴다. 주석과 줄의 순서, 줄바꿈 모양은 그대로다."""

    path: Path
    lines: list[str]
    created: bool = False
    changed: bool = False


@dataclass(frozen=True)
class Outcome:
    """비밀 하나를 어떻게 했는가."""

    name: str
    action: str


def read_lines(path: Path) -> list[str]:
    """파일의 줄들. 줄바꿈을 바꾸지 않고(newline='') 붙인 채로 읽는다. Windows 의 CRLF 를 지키려고다."""
    with path.open(encoding='utf-8', newline='') as file:
        return file.read().splitlines(keepends=True)


def load(root: Path, relative: str) -> EnvFile:
    """.env 를 읽는다. 없으면 .env.example 의 내용으로 만든다(아직 쓰지는 않는다)."""
    path = root / relative
    if path.exists():
        return EnvFile(path, read_lines(path))
    example = path.with_name('.env.example')
    return EnvFile(path, read_lines(example), created=True, changed=True)


def find_line(lines: list[str], key: str) -> int | None:
    """그 이름의 줄의 자리. 주석이 아닌 줄을 먼저 찾고, 없으면 주석으로 막힌 줄을 찾는다."""
    commented = None
    for index, line in enumerate(lines):
        match = LINE.match(line)
        if not match or match['key'] != key:
            continue
        if not match['comment']:
            return index
        if commented is None:
            commented = index
    return commented


def raw_value(env: EnvFile, key: str) -> str | None:
    """그 이름의 줄의 값. 줄이 없으면 None 이다."""
    index = find_line(env.lines, key)
    if index is None:
        return None
    return LINE.match(env.lines[index])['value']


def secret_of(value: str | None, spot: Spot) -> str | None:
    """자리에 적힌 비밀. 주소면 비밀번호 부분이다. 주소의 모양이 아니면 None 이다(손대지 않는다)."""
    if value is None or not spot.url:
        return value
    match = URL_PASSWORD.match(value)
    return match['password'] if match else None


def is_filled(secret: str | None) -> bool:
    """이미 채운 값인가."""
    return secret is not None and secret not in PLACEHOLDERS


def with_secret(value: str, spot: Spot, secret: str) -> str:
    """그 자리에 비밀을 넣은 값. 주소면 비밀번호 부분만 바꾼다."""
    if not spot.url:
        return secret
    match = URL_PASSWORD.match(value)
    return f'{match["head"]}{secret}{match["tail"]}'


def example_line(root: Path, spot: Spot) -> str | None:
    """.env.example 에 있는 그 이름의 줄. .env 에 그 줄이 없을 때 이 모양으로 더한다."""
    example = (root / spot.file).with_name('.env.example')
    if not example.exists():
        return None
    lines = read_lines(example)
    index = find_line(lines, spot.key)
    return None if index is None else lines[index]


def newline_of(env: EnvFile) -> str:
    """그 파일의 줄바꿈. Windows 에서 만든 파일(CRLF)이면 더하는 줄도 CRLF 로 맞춘다."""
    return '\r\n' if any(line.endswith('\r\n') for line in env.lines) else '\n'


def write_value(env: EnvFile, index: int, value: str) -> None:
    """그 줄의 값만 바꾼다. 주석인 줄은 주석인 채로 둔다."""
    match = LINE.match(env.lines[index])
    env.lines[index] = f'{match["comment"] or ""}{match["key"]}={value}{match["newline"] or newline_of(env)}'
    env.changed = True


def append_line(env: EnvFile, template: str, value: str) -> None:
    """.env 끝에 줄을 더한다. 모양(주석인지)은 .env.example 의 그 줄을 따른다."""
    newline = newline_of(env)
    if env.lines and not env.lines[-1].endswith('\n'):
        env.lines[-1] += newline
    match = LINE.match(template)
    env.lines.append(f'{match["comment"] or ""}{match["key"]}={value}{newline}')
    env.changed = True


def place(root: Path, env: EnvFile, spot: Spot, secret: str) -> bool:
    """자리 하나에 비밀을 적는다. 이미 채운 자리면 그대로 둔다. 적었으면 True 다."""
    index = find_line(env.lines, spot.key)
    if index is None:
        template = example_line(root, spot)
        if template is None or spot.url:
            return False
        append_line(env, template, secret)
        return True
    value = LINE.match(env.lines[index])['value']
    current = secret_of(value, spot)
    if current is None or is_filled(current):
        return False
    write_value(env, index, with_secret(value, spot, secret))
    return True


def fill(root: Path, files: dict[str, EnvFile], secret: Secret) -> Outcome:
    """비밀 하나를 채운다. 짝의 한쪽에 값이 있으면 그 값을, 없으면 새 난수를 쓴다."""
    known = {secret_of(raw_value(files[spot.file], spot.key), spot) for spot in secret.spots}
    filled = {value for value in known if is_filled(value)}
    if len(filled) > 1:
        names = ', '.join(f'{spot.file} 의 {spot.key}' for spot in secret.spots)
        return Outcome(secret.name, f'값이 서로 다르다. 고치지 않았다. 손으로 맞춘다: {names}')
    copied = bool(filled)
    value = filled.pop() if copied else secrets.token_hex(SECRET_BYTES)
    written = [spot for spot in secret.spots if place(root, files[spot.file], spot, value)]
    if not written:
        return Outcome(secret.name, '이미 채워져 있다')
    where = ', '.join(f'{spot.file} 의 {spot.key}' for spot in written)
    return Outcome(secret.name, f'{"맞췄다" if copied else "새로 만들었다"}: {where}')


def external_keys(files: dict[str, EnvFile]) -> list[str]:
    """비밀처럼 보이지만 표에 없는 이름들. 밖에서 받는 키다. 채우지 않는다."""
    listed = {(spot.file, spot.key) for secret in SECRETS for spot in secret.spots}
    names = []
    for relative, env in files.items():
        for line in env.lines:
            match = LINE.match(line)
            if not match or match['key'] in NOT_SECRETS or not SECRET_NAME.search(match['key']):
                continue
            if (relative, match['key']) not in listed:
                names.append(f'{relative} 의 {match["key"]}')
    return sorted(set(names))


def save(env: EnvFile) -> None:
    """바뀐 파일만 쓴다. 새로 만든 파일은 주인만 읽게 한다(Windows 에서는 효과가 없다)."""
    if not env.changed:
        return
    env.path.write_text(''.join(env.lines), encoding='utf-8', newline='')
    if env.created:
        env.path.chmod(0o600)


def run(root: Path, dry_run: bool) -> tuple[dict[str, EnvFile], list[Outcome], list[str]]:
    """파일을 읽고 비밀을 채운다. dry_run 이면 쓰지 않는다."""
    files = {relative: load(root, relative) for relative in ENV_FILES}
    outcomes = [fill(root, files, secret) for secret in SECRETS]
    if not dry_run:
        for env in files.values():
            save(env)
    return files, outcomes, external_keys(files)


def report(files: dict[str, EnvFile], outcomes: list[Outcome], external: list[str], dry_run: bool) -> str:
    """한 일을 사람이 읽을 글로. 비밀의 값은 넣지 않는다."""
    lines = ['(--dry-run: 아무것도 쓰지 않았다)'] if dry_run else []
    lines += [f'만들었다: {relative}' for relative, env in files.items() if env.created]
    lines += [f'- {outcome.name}: {outcome.action}' for outcome in outcomes]
    if external:
        lines.append('밖에서 받는 키라 채우지 않았다. 쓸 때 직접 적는다:')
        lines += [f'  {name}' for name in external]
    return '\n'.join(lines)


def conflicted(outcomes: list[Outcome]) -> bool:
    """값이 서로 달라 고치지 못한 비밀이 있는가."""
    return any(outcome.action.startswith('값이 서로 다르다') for outcome in outcomes)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """명령 줄을 읽는다."""
    parser = argparse.ArgumentParser(description='.env 를 만들고 비어 있는 비밀을 난수로 채운다')
    parser.add_argument('--dry-run', action='store_true', help='무엇을 할지만 보이고 쓰지 않는다')
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    """채우고 한 일을 찍는다. 값이 서로 달라 고치지 못한 것이 있으면 1 로 끝난다."""
    args = parse_args(argv)
    files, outcomes, external = run(REPO_ROOT, args.dry_run)
    print(report(files, outcomes, external, args.dry_run))
    return 1 if conflicted(outcomes) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
