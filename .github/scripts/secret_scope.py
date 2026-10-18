# .github/scripts/secret_scope.py

"""
비밀이 그것을 쓰는 프로세스에만 가는지 compose 의 설정으로 본다(#274).

compose 는 서버 폴더의 .env 를 통째로 넘긴다(env_file). 그래서 그 프로세스가 쓰지 않는 비밀은
docker-compose.yml 의 environment 에서 빈 값으로 덮어야 한다. 이 검사는 아래의 표(SECRETS)를 기준으로
  - 비밀을 받으면 안 되는 프로세스가 그 비밀을 빈 값으로 덮었는가
  - 서명 개인키의 폴더(auth-server/keys)를 auth-server 만 붙였는가, 나머지는 키의 경로를 비웠는가
  - 서버 폴더의 .env.example 에 적힌 비밀이 모두 표에 있는가(새 비밀이 표 없이 퍼지지 않게)
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

# 비밀로 보는 이름. .env.example 에서 이 모양의 이름을 찾아 표에 있는지 본다
SECRET_NAME = re.compile(r'SECRET|PASSWORD|API_KEY|HMAC_KEY')
# 이름이 비밀처럼 보이지만 비밀이 아닌 설정
NOT_SECRETS = frozenset({'PASSWORD_RESET_URL'})
# .env.example 의 한 줄. 주석으로 막아 둔 것(# NAME=)도 센다. 켜는 법을 알리는 줄이다
EXAMPLE_LINE = re.compile(r'^#?\s*([A-Z][A-Z0-9_]*)=')

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
        'OPENAI_API_KEY',
        'ANTHROPIC_API_KEY',
        'GEMINI_API_KEY',
        'ZAI_API_KEY',
        'SIGNAL_SECRET',
        'AI_LOG_HMAC_KEY',
    ),
    # 결제 서버가 요청의 서명을 확인하는 비밀. 요청을 받는 서버만 쓴다
    *secrets('billing-server', ['billing-server'], 'PG_WEBHOOK_SECRET', 'GAME_SERVER_SECRET'),
    # 인증 서버와 함께 아는 비밀. 서버가 인증 서버의 요청을 확인하고, 정리 작업이 보호자 알림(#352)에 서명한다
    *secrets('billing-server', ['billing-server', 'billing-sweeper'], 'AUTH_SERVER_SECRET'),
    # 결제 대행사의 키. 서버와 대사(cron)가 결제 대행사를 부른다. 정리 작업(sweeper)은 부르지 않는다(config.LoadSweeper)
    *secrets('billing-server', ['billing-server', 'billing-cron'], 'TOSS_SECRET_KEY'),
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


def env_file_servers(service: dict) -> set[str]:
    """그 프로세스가 통째로 받는 .env 의 서버 폴더 이름들(auth-server 등)."""
    servers = set()
    for entry in service.get('env_file') or []:
        path = Path(entry['path'] if isinstance(entry, dict) else entry)
        servers.add(path.parent.name)
    return servers


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
        environment = service.get('environment') or {}
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
        if (
            'auth-server' in env_file_servers(service)
            and (service.get('environment') or {}).get(SIGNING_KEY_PATH) != ''
        ):
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


def check(config: dict, repo_root: Path, table: list[Secret]) -> list[str]:
    """모든 검사의 문제들. 비어 있으면 통과다."""
    services = config.get('services') or {}
    return [
        *leaked_secrets(services, table),
        *misplaced_signing_keys(services),
        *unlisted_secrets(repo_root, table),
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
