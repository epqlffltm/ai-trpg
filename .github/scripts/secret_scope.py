# .github/scripts/secret_scope.py

"""
비밀이 그것을 쓰는 프로세스에만 가는지 compose 의 설정으로 본다(#274).

compose 는 서버 폴더의 .env 를 통째로 넘긴다(env_file). 그래서 그 프로세스가 쓰지 않는 비밀은
docker-compose.yml 의 environment 에서 빈 값으로 덮어야 한다. 이 검사는 아래의 표(SECRETS)를 기준으로
  - 비밀을 받으면 안 되는 프로세스가 그 비밀을 빈 값으로 덮었는가
  - 서명 개인키의 폴더(auth-server/keys)를 auth-server 만 붙였는가, 나머지는 키의 경로를 비웠는가
  - 서버 폴더의 .env.example 에 적힌 비밀이 모두 표에 있는가(새 비밀이 표 없이 퍼지지 않게)
  - 루트 .env 의 비밀(${POSTGRES_PASSWORD} 처럼 compose 가 채우는 것)을 표(ROOT_SECRETS)에 적힌 프로세스만 받는가,
    루트 .env.example 의 비밀이 모두 그 표에 있는가
를 본다. 비밀의 값은 읽지도 찍지도 않는다. .env 를 읽지 않는 설정(--no-env-resolution)만 본다.

    사용: docker compose --profile app config --no-interpolate --no-env-resolution --format json \
            | python3 .github/scripts/secret_scope.py

stack-smoke.sh 의 check 가 부른다. .env 가 없어도 돈다.
"""

import json
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# 비밀로 보는 이름. .env.example 에서 이 모양의 이름을 찾아 표에 있는지 본다.
# 웹후크의 주소는 아는 사람이 누구나 글을 쓰므로 비밀이다(ALERT_DISCORD_WEBHOOK_URL 등).
# tools/fill_env.py 와 같은 규칙이다
SECRET_NAME = re.compile(r'SECRET|PASSWORD|API_KEY|HMAC_KEY|TOKEN|WEBHOOK_URL')
# 이름이 비밀처럼 보이지만 비밀이 아닌 설정
NOT_SECRETS = frozenset({'PASSWORD_RESET_URL'})
# .env.example 의 한 줄. 주석으로 막아 둔 것(# NAME=)도 센다. 켜는 법을 알리는 줄이다
EXAMPLE_LINE = re.compile(r'^#?\s*([A-Z][A-Z0-9_]*)=')
# compose 의 값 안에서 루트 .env 를 부르는 자리(${NAME}, ${NAME:-기본}, ${NAME:?알림})
ROOT_REFERENCE = re.compile(r'\$\{([A-Z][A-Z0-9_]*)')

# 서명 개인키가 든 폴더와, 그 경로를 알리는 설정의 이름. 키를 붙여도 되는 프로세스
SIGNING_KEY_FOLDER = 'auth-server/keys'
SIGNING_KEY_PATH = 'JWT_PRIVATE_KEY_PATH'
SIGNING_KEY_HOLDERS = frozenset({'auth-server'})


@dataclass(frozen=True)
class Secret:
    """비밀 하나. 어느 서버 폴더의 .env 에서 오고, 어느 프로세스가 받아도 되는가."""

    server: str
    name: str
    allowed: frozenset[str]


def secrets(server: str, allowed: Iterable[str], *names: str) -> list[Secret]:
    """한 서버의 비밀 여럿을 같은 허용 목록으로 만든다."""
    return [Secret(server, name, frozenset(allowed)) for name in names]


# 프로세스마다 받아도 되는 비밀. 새 비밀을 더하면 여기에 적는다. 표에 없으면 이 검사가 실패한다
SECRETS = [
    # Django 의 비밀키. 발송함의 암호화, 요약 메일, 인증 코드의 해시에 쓴다. 인증의 프로세스 모두가 쓴다
    *secrets(
        'auth-server',
        ['auth-migrate', 'auth-server', 'auth-mail', 'auth-welcome-credits', 'auth-cron'],
        'SECRET_KEY',
    ),
    # 메일 서버의 비밀번호. 발송함의 워커가 보낸다. 바로 보내는 설정(MAIL_DELIVERY=inline)에서는 서버와 cron 도 보낸다
    *secrets('auth-server', ['auth-server', 'auth-mail', 'auth-cron'], 'SMTP_PASSWORD'),
    # 결제 서버와 함께 아는 비밀. 환영 크레딧의 워커가 결제 서버를 부르고,
    # 서버가 결제 서버의 보호자 알림(#352)의 서명을 확인한다
    *secrets('auth-server', ['auth-server', 'auth-welcome-credits'], 'BILLING_SECRET'),
    # 게임 서버의 비밀. 마이그레이션은 DB 만 쓴다
    *secrets(
        'game-server',
        ['game-server'],
        'BILLING_SECRET',
        'NOTIFICATION_SECRET',
        'OPENAI_API_KEY',
        'ANTHROPIC_API_KEY',
        'GEMINI_API_KEY',
        'ZAI_API_KEY',
        'SIGNAL_SECRET',
        'AI_LOG_HMAC_KEY',
    ),
    # 게시판 서버가 알림 서버에 댓글의 알림을 넣는 비밀(#385). 서버만 쓴다. 마이그레이션에는 주지 않는다
    *secrets('board-server', ['board-server'], 'NOTIFICATION_SECRET'),
    # 결제 서버가 요청의 서명을 확인하는 비밀. 요청을 받는 서버만 쓴다
    *secrets('billing-server', ['billing-server'], 'PG_WEBHOOK_SECRET', 'GAME_SERVER_SECRET'),
    # 인증 서버와 함께 아는 비밀. 서버가 인증 서버의 요청을 확인하고, 정리 작업이 보호자 알림(#352)에 서명한다
    *secrets('billing-server', ['billing-server', 'billing-sweeper'], 'AUTH_SERVER_SECRET'),
    # 결제 대행사의 키. 서버와 대사(cron)가 결제 대행사를 부른다. 정리 작업(sweeper)은 부르지 않는다(config.LoadSweeper)
    *secrets('billing-server', ['billing-server', 'billing-cron'], 'TOSS_SECRET_KEY'),
    # 알림 서버와 함께 아는 비밀. 정리 작업이 사용자에게 알릴 일을 알림 서버에 넣는다(#385). 서버와 대사는 부르지 않는다
    *secrets('billing-server', ['billing-sweeper'], 'NOTIFICATION_SECRET'),
    # 알림 서버가 알림을 넣는 요청의 서명을 확인하는 비밀. 넣는 서버마다 하나다. 요청을 받는 서버만 쓴다.
    # 마이그레이션(notification-migrate)에는 주지 않는다
    *secrets(
        'notification-server',
        ['notification-server'],
        'GAME_SERVER_SECRET',
        'BILLING_SERVER_SECRET',
        'BOARD_SERVER_SECRET',
    ),
]


# 루트 .env 의 비밀마다 받아도 되는 프로세스. compose 가 environment 의 값에 채워 넘긴다.
# DB 의 계정마다의 비밀번호는 DB(초기화 스크립트가 계정을 만든다)와 그 서버의 프로세스만 받는다
ROOT_SECRETS: dict[str, frozenset[str]] = {
    # DB 의 관리용 슈퍼유저. DB 와 백업만 쓴다. 바깥 백업(staging 의 backup-offsite)도 풀어 볼 빈 DB 를 만들고 지운다
    'POSTGRES_PASSWORD': frozenset({'db', 'db-backup', 'backup-offsite'}),
    'AUTH_DB_PASSWORD': frozenset(
        {'db', 'auth-migrate', 'auth-server', 'auth-mail', 'auth-welcome-credits', 'auth-cron'}
    ),
    'GAME_DB_PASSWORD': frozenset({'db', 'game-migrate', 'game-server'}),
    'BILLING_DB_PASSWORD': frozenset({'db', 'billing-migrate', 'billing-server', 'billing-sweeper', 'billing-cron'}),
    'BOARD_DB_PASSWORD': frozenset({'db', 'board-migrate', 'board-server'}),
    'NOTIFICATION_DB_PASSWORD': frozenset({'db', 'notification-migrate', 'notification-server'}),
    # DB 의 메트릭을 읽는 계정(monitor). DB 가 계정을 만들고, 수집기(Alloy)가 그 계정으로 붙는다
    'MONITOR_DB_PASSWORD': frozenset({'db', 'alloy'}),
    'GRAFANA_ADMIN_PASSWORD': frozenset({'grafana'}),
    # 바깥 백업이 S3 에 올리고 받는 접근 키(staging). 그 컨테이너만 쓴다
    'BACKUP_AWS_SECRET_ACCESS_KEY': frozenset({'backup-offsite'}),
    # 경보를 보내는 곳(Discord, Slack, Telegram, 메일)의 비밀. 경보를 보내는 Alertmanager 만 쓴다
    'ALERT_DISCORD_WEBHOOK_URL': frozenset({'alertmanager'}),
    'ALERT_SLACK_WEBHOOK_URL': frozenset({'alertmanager'}),
    'ALERT_TELEGRAM_BOT_TOKEN': frozenset({'alertmanager'}),
    'ALERT_SMTP_PASSWORD': frozenset({'alertmanager'}),
}


def env_file_servers(service: dict) -> set[str]:
    """그 프로세스가 통째로 받는 .env 의 서버 폴더 이름들(auth-server 등)."""
    servers = set()
    for entry in service.get('env_file') or []:
        path = Path(entry['path'] if isinstance(entry, dict) else entry)
        servers.add(path.parent.name)
    return servers


def environment_of(service: dict) -> dict[str, str | None]:
    """
    그 프로세스의 environment 를 이름과 값의 표로. compose 는 이것을 표로도, "이름=값"의 목록으로도 낸다.
    파일을 둘 겹치면(docker-compose.staging.yml) 목록으로 낸다. 목록에서 "=" 가 없는 줄은 값이 없는 것(None)이다
    """
    environment = service.get('environment') or {}
    if isinstance(environment, dict):
        return environment
    pairs = {}
    for entry in environment:
        name, separator, value = str(entry).partition('=')
        pairs[name] = value if separator else None
    return pairs


def mounts_signing_keys(service: dict) -> bool:
    """그 프로세스가 서명 개인키의 폴더를 붙였는가."""
    return any(
        str(volume.get('source', '')).rstrip('/').endswith(SIGNING_KEY_FOLDER)
        for volume in service.get('volumes') or []
    )


def leaked_secrets(services: dict[str, dict], table: list[Secret]) -> list[str]:
    """받으면 안 되는 비밀을 빈 값으로 덮지 않은 프로세스들. "프로세스: 비밀" 모양의 글이다."""
    problems = []
    for name, service in sorted(services.items()):
        environment = environment_of(service)
        servers = env_file_servers(service)
        for secret in table:
            if secret.server not in servers or name in secret.allowed:
                continue
            if environment.get(secret.name) != '':
                problems.append(f'{name}: {secret.name} 를 받는다. environment 에서 빈 값으로 덮는다')
    return problems


def misplaced_signing_keys(services: dict[str, dict]) -> list[str]:
    """서명 개인키를 받으면 안 되는 인증 프로세스가 키를 붙였거나, 키의 경로를 비우지 않은 것들."""
    problems = []
    for name, service in sorted(services.items()):
        if name in SIGNING_KEY_HOLDERS:
            continue
        if mounts_signing_keys(service):
            problems.append(f'{name}: 서명 개인키의 폴더({SIGNING_KEY_FOLDER})를 붙였다')
        if 'auth-server' in env_file_servers(service) and environment_of(service).get(SIGNING_KEY_PATH) != '':
            problems.append(f'{name}: {SIGNING_KEY_PATH} 를 비우지 않았다')
    return problems


def example_secret_names(example: Path) -> set[str]:
    """.env.example 에 적힌 비밀의 이름들. 주석으로 막아 둔 줄도 센다."""
    names = set()
    for line in example.read_text(encoding='utf-8').splitlines():
        match = EXAMPLE_LINE.match(line)
        if match and SECRET_NAME.search(match.group(1)) and match.group(1) not in NOT_SECRETS:
            names.add(match.group(1))
    return names


def root_references(service: dict) -> set[str]:
    """그 프로세스의 environment 가 부르는 루트 .env 의 이름들. 비밀처럼 보이는 것만 센다."""
    names = set()
    for value in environment_of(service).values():
        for name in ROOT_REFERENCE.findall(str(value or '')):
            if SECRET_NAME.search(name) and name not in NOT_SECRETS:
                names.add(name)
    return names


def leaked_root_secrets(services: dict[str, dict], table: dict[str, frozenset[str]]) -> list[str]:
    """루트 .env 의 비밀을 받으면 안 되는 프로세스가 받는 것과, 표에 없는 루트의 비밀을 부르는 것."""
    problems = []
    for name, service in sorted(services.items()):
        for secret in sorted(root_references(service)):
            if secret not in table:
                problems.append(
                    f'{name}: 루트 .env 의 {secret} 를 받는데 표에 없다. secret_scope.py 의 ROOT_SECRETS 에 적는다'
                )
            elif name not in table[secret]:
                problems.append(f'{name}: 루트 .env 의 {secret} 를 받는다. 받을 프로세스가 아니다')
    return problems


def unlisted_root_secrets(repo_root: Path, table: dict[str, frozenset[str]]) -> list[str]:
    """루트 .env.example 에 있는데 표에 없는 비밀들. 파일이 없으면(작은 시험) 보지 않는다."""
    example = repo_root / '.env.example'
    if not example.exists():
        return []
    return [
        f'.env.example 의 {name} 가 표에 없다. secret_scope.py 의 ROOT_SECRETS 에 적는다'
        for name in sorted(example_secret_names(example))
        if name not in table
    ]


def unlisted_secrets(repo_root: Path, table: list[Secret]) -> list[str]:
    """서버 폴더의 .env.example 에 있는데 표에 없는 비밀들."""
    listed = {(secret.server, secret.name) for secret in table}
    problems = []
    for example in sorted(repo_root.glob('*-server/.env.example')):
        server = example.parent.name
        for name in sorted(example_secret_names(example)):
            if (server, name) not in listed:
                problems.append(f'{server}/.env.example 의 {name} 가 표에 없다. secret_scope.py 의 SECRETS 에 적는다')
    return problems


def check(
    config: dict,
    repo_root: Path,
    table: list[Secret],
    root_table: dict[str, frozenset[str]] = ROOT_SECRETS,
) -> list[str]:
    """모든 검사의 문제들. 비어 있으면 통과다."""
    services = config.get('services') or {}
    return [
        *leaked_secrets(services, table),
        *misplaced_signing_keys(services),
        *unlisted_secrets(repo_root, table),
        *leaked_root_secrets(services, root_table),
        *unlisted_root_secrets(repo_root, root_table),
    ]


def main() -> int:
    problems = check(json.load(sys.stdin), REPO_ROOT, SECRETS)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print('비밀은 그것을 쓰는 프로세스에만 간다')
    return 0


if __name__ == '__main__':
    sys.exit(main())
