# tools/staging_env.py

"""
staging(VM)의 .env 여섯(루트와 서버 다섯)을 새로 만든다. VM 을 처음 준비할 때 한 번 쓴다(docs/operations/staging-vm.md).

    사용(VM 의 저장소 루트에서):
        python3 tools/staging_env.py --domain <도메인> --acme-email <메일> \\
            --llm-base-url http://<집 PC 의 Tailscale 주소>:11434/v1 \\
            --s3-bucket <버킷> --age-recipients "<주 열쇠의 공개키> <확인 열쇠의 공개키>"

하는 일:
  - 저장소의 .env.example 을 바탕으로 만든다. 설명 줄은 그대로 두고 정할 값만 채운다
    (주석으로 막힌 줄 "# 이름=" 은 풀어서 채운다. 예시에 없는 이름은 끝에 더한다)
  - 비밀(DB 비밀번호, 서버끼리의 서명 비밀, Django 의 SECRET_KEY 등)은 이 자리에서 무작위로 만든다(64자).
    로컬의 값을 옮기지 않는다(docs/architecture/deployment.md 의 "비밀과 설정")
  - 서버끼리 같아야 하는 비밀은 같은 값을 넣는다. 짝은 아래의 PAIRS 다
  - 파일은 주인만 읽게(600) 새로 만든다. 여섯 가운데 하나라도 이미 있으면 아무것도 만들지 않고 멈춘다(덮어쓰지 않는다)
  - 비밀의 값은 찍지 않는다. 다 만들면 사람이 채울 것(외부의 키)만 찍는다

사람이 채울 것: 모델 창구의 키(game-server/.env 의 ZAI_API_KEY), S3 의 접근 키(루트 .env 의 BACKUP_AWS_*).
비워 두면 docker compose 가 뜨기를 거부하거나(S3 키) 그 창구의 모델을 부르지 않는다(모델 키).
JWT 의 서명 키(auth-server/keys/)는 만들지 않는다. 문서의 openssl 명령으로 만든다.

VM 에는 uv 가 없어 Ubuntu 에 든 python3 로 돌린다. 표준 라이브러리만 쓴다. 테스트는 tools/test_staging_env.py 다.
"""

import argparse
import os
import re
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# 만드는 파일들. 저장소 루트에서의 경로다. 저마다 옆의 .env.example 을 바탕으로 한다
TARGETS = (
    '.env',
    'auth-server/.env',
    'game-server/.env',
    'board-server/.env',
    'billing-server/.env',
    'notification-server/.env',
)
# 무작위로 만든 비밀의 길이(16진수 글자). 서버들이 요구하는 길이(32자 이상)를 넘는다
SECRET_HEX_BYTES = 32
# 주인만 읽고 쓴다(rw-------)
PRIVATE_FILE_MODE = 0o600
# DB 의 이름(루트 .env.example 의 POSTGRES_DB)
DATABASE = 'trpg'
# 서버끼리 같아야 하는 비밀: (이름표, [(파일, 이름), ...]). 이름표마다 값 하나를 만들어 모두에 넣는다
PAIRS = {
    'auth_billing': [('auth-server/.env', 'BILLING_SECRET'), ('billing-server/.env', 'AUTH_SERVER_SECRET')],
    'game_billing': [('game-server/.env', 'BILLING_SECRET'), ('billing-server/.env', 'GAME_SERVER_SECRET')],
    'game_notify': [('game-server/.env', 'NOTIFICATION_SECRET'), ('notification-server/.env', 'GAME_SERVER_SECRET')],
    'billing_notify': [
        ('billing-server/.env', 'NOTIFICATION_SECRET'),
        ('notification-server/.env', 'BILLING_SERVER_SECRET'),
    ],
    'board_notify': [('board-server/.env', 'NOTIFICATION_SECRET'), ('notification-server/.env', 'BOARD_SERVER_SECRET')],
}
# 서버마다 DB 의 계정. 루트 .env 의 비밀번호와 서버의 DATABASE_URL 이 같아야 한다
DATABASE_ACCOUNTS = {
    'auth-server/.env': ('AUTH_DB_PASSWORD', 'postgres://auth:{password}@db:5432/{database}'),
    'game-server/.env': ('GAME_DB_PASSWORD', 'postgresql+asyncpg://game:{password}@db:5432/{database}'),
    'board-server/.env': ('BOARD_DB_PASSWORD', 'postgresql://board:{password}@db:5432/{database}'),
    'billing-server/.env': ('BILLING_DB_PASSWORD', 'postgres://billing:{password}@db:5432/{database}'),
    'notification-server/.env': (
        'NOTIFICATION_DB_PASSWORD',
        'postgresql+asyncpg://notification:{password}@db:5432/{database}',
    ),
}
# 비워 두어도 되는 비밀: 쓰지 않는 창구와 메일. 쓰게 되면 사람이 적는다.
# 이 밖의 비밀은 모두 채운다(test_staging_env.py 가 본다)
OPTIONAL_SECRETS = frozenset(
    {
        'SMTP_PASSWORD',
        'OPENAI_API_KEY',
        'ANTHROPIC_API_KEY',
        'GEMINI_API_KEY',
        'TOSS_SECRET_KEY',
        'TOSS_CLIENT_KEY',
    }
)
# 사람이 채울 것: (파일, 이름, 까닭)
TO_FILL = (
    ('game-server/.env', 'ZAI_API_KEY', 'Z.ai 의 API 키(GLM-4.7-Flash)'),
    ('.env', 'BACKUP_AWS_ACCESS_KEY_ID', 'S3 의 접근 키(docker/backup-offsite/iam-policy.json 의 권한)'),
    ('.env', 'BACKUP_AWS_SECRET_ACCESS_KEY', 'S3 의 비밀 접근 키'),
)
# 가장 앞에 오는 "이름=" 줄(주석이 아닌 것). 앞의 빈칸은 봐준다
ASSIGNMENT = r'^[ \t]*{name}='
# 주석으로 막힌 "# 이름=" 줄
COMMENTED_ASSIGNMENT = r'^[ \t]*#[ \t]*{name}='
APPENDED_HEADER = '\n# --- tools/staging_env.py 가 더한 값 ---\n'


@dataclass(frozen=True)
class Options:
    """명령줄에서 받는 staging 의 값. 비밀이 아니다."""

    domain: str
    acme_email: str
    llm_base_url: str
    s3_bucket: str
    age_recipients: str
    s3_region: str = 'ap-northeast-2'


def new_secret() -> str:
    """무작위 비밀 하나(16진수 64자)."""
    return secrets.token_hex(SECRET_HEX_BYTES)


def database_passwords() -> dict[str, str]:
    """루트 .env 의 DB 비밀번호들. 관리 계정과 서버마다의 계정이다."""
    names = ['POSTGRES_PASSWORD', *(name for name, _ in DATABASE_ACCOUNTS.values())]
    return {name: new_secret() for name in names}


def pair_values() -> dict[str, str]:
    """서버끼리 같아야 하는 비밀. 이름표마다 하나다."""
    return {label: new_secret() for label in PAIRS}


def root_values(options: Options, passwords: dict[str, str]) -> dict[str, str]:
    """루트 .env 에 넣을 값."""
    return {
        **passwords,
        # 인증 서버의 테스트용 DB 를 만들 권한. 운영에서는 주지 않는다
        'AUTH_DB_ALLOW_TEST_DB': 'false',
        'GRAFANA_ADMIN_PASSWORD': new_secret(),
        # DB 의 메트릭을 읽는 계정(monitor). 주소에 그대로 들어가므로 16진수(영문과 숫자)다
        'MONITOR_DB_PASSWORD': new_secret(),
        'OTEL_EXPORTER_OTLP_ENDPOINT': 'http://alloy:4318',
        'COMPOSE_FILE': 'docker-compose.yml:docker-compose.staging.yml',
        'COMPOSE_PROFILES': 'app,observability',
        'APP_ENVIRONMENT': 'staging',
        'DOMAIN': options.domain,
        'ACME_EMAIL': options.acme_email,
        'GAME_LLM_BASE_URL': options.llm_base_url,
        'BACKUP_S3_BUCKET': options.s3_bucket,
        'BACKUP_S3_REGION': options.s3_region,
        'BACKUP_AGE_RECIPIENTS': options.age_recipients,
        'BACKUP_AWS_ACCESS_KEY_ID': '',
        'BACKUP_AWS_SECRET_ACCESS_KEY': '',
    }


def server_values() -> dict[str, dict[str, str]]:
    """서버마다의 .env 에 넣을, 짝이 없는 값."""
    common = {'APP_ENVIRONMENT': 'staging'}
    debug_off = {**common, 'DEBUG': 'false'}
    return {
        'auth-server/.env': {**debug_off, 'SECRET_KEY': new_secret()},
        'game-server/.env': {
            **debug_off,
            'NARRATOR': 'llm',
            'LLM_MODEL': 'glm-4-7-flash',
            'LLM_FALLBACK_MODELS': '',
            'ZAI_API_KEY': '',
            'AI_LOG_HMAC_KEY': new_secret(),
            'SIGNAL_SECRET': new_secret(),
        },
        'board-server/.env': dict(common),
        'billing-server/.env': {**debug_off, 'PG_WEBHOOK_SECRET': new_secret(), 'PAYMENT_PROVIDER': 'fake'},
        'notification-server/.env': dict(debug_off),
    }


def planned_values(options: Options) -> dict[str, dict[str, str]]:
    """파일마다 넣을 이름과 값. 짝이 맞는 비밀과 DB 의 주소를 함께 넣는다."""
    passwords = database_passwords()
    plan = {'.env': root_values(options, passwords), **server_values()}
    for label, value in pair_values().items():
        for target, name in PAIRS[label]:
            plan[target][name] = value
    for target, (password_name, url) in DATABASE_ACCOUNTS.items():
        plan[target]['DATABASE_URL'] = url.format(password=passwords[password_name], database=DATABASE)
    return plan


def set_value(text: str, name: str, value: str) -> str:
    """
    글에서 그 이름의 줄 하나를 "이름=값" 으로 바꾼다. 주석이 아닌 줄을 먼저 찾고, 없으면 "# 이름=" 줄을 푼다.
    둘 다 없으면 끝에 더한다. 바꾸는 것은 처음 찾은 한 줄뿐이다(설명 속의 같은 이름은 그대로 둔다).
    """
    line = f'{name}={value}'
    for pattern in (ASSIGNMENT, COMMENTED_ASSIGNMENT):
        regex = re.compile(pattern.format(name=re.escape(name)) + r'.*$', re.MULTILINE)
        if regex.search(text):
            return regex.sub(lambda _: line, text, count=1)
    if APPENDED_HEADER not in text:
        text = text.rstrip('\n') + '\n' + APPENDED_HEADER
    return text + line + '\n'


def render(example: str, values: dict[str, str]) -> str:
    """예시 파일의 글에 값들을 채운 글."""
    for name, value in values.items():
        example = set_value(example, name, value)
    return example


def existing_targets(root: Path) -> list[str]:
    """이미 있는 대상 파일들. 하나라도 있으면 만들지 않는다."""
    return [target for target in TARGETS if (root / target).exists()]


def write_private(path: Path, content: str) -> None:
    """주인만 읽고 쓰는 파일을 새로 만든다. 이미 있으면 실패한다(만드는 순간에 권한을 정한다)."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, PRIVATE_FILE_MODE)
    with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as file:
        file.write(content)


def write_all(root: Path, plan: dict[str, dict[str, str]]) -> None:
    """예시 파일을 바탕으로 여섯을 만든다."""
    for target in TARGETS:
        example = (root / f'{target}.example').read_text(encoding='utf-8')
        write_private(root / target, render(example, plan[target]))


def parse_options(argv: list[str]) -> Options:
    parser = argparse.ArgumentParser(description='staging(VM)의 .env 여섯을 새로 만든다')
    parser.add_argument('--domain', required=True, help='이 VM 의 도메인')
    parser.add_argument('--acme-email', required=True, help="Let's Encrypt 에 알리는 메일")
    parser.add_argument(
        '--llm-base-url', required=True, help='집 PC 의 Ollama(Tailscale 주소), 예: http://100.x.y.z:11434/v1'
    )
    parser.add_argument('--s3-bucket', required=True, help='바깥 백업의 S3 버킷')
    parser.add_argument('--s3-region', default='ap-northeast-2', help='그 버킷의 리전')
    parser.add_argument(
        '--age-recipients', required=True, help='age 의 공개키 둘(주 열쇠, 확인 열쇠)을 빈칸으로 이은 것'
    )
    parsed = parser.parse_args(argv)
    recipients = parsed.age_recipients.split()
    if len(recipients) != 2 or not all(key.startswith('age1') for key in recipients):
        parser.error('--age-recipients 는 age 의 공개키(age1...) 둘이다(주 열쇠, 확인 열쇠)')
    return Options(
        domain=parsed.domain,
        acme_email=parsed.acme_email,
        llm_base_url=parsed.llm_base_url,
        s3_bucket=parsed.s3_bucket,
        s3_region=parsed.s3_region,
        age_recipients=' '.join(recipients),
    )


def main(argv: list[str], root: Path = REPO_ROOT) -> int:
    options = parse_options(argv)
    existing = existing_targets(root)
    if existing:
        print(f'이미 있다: {", ".join(existing)}. 덮어쓰지 않는다. 아무것도 만들지 않았다', file=sys.stderr)
        return 1
    write_all(root, planned_values(options))
    print('만들었다(주인만 읽는다): ' + ', '.join(TARGETS))
    print('사람이 채울 것:')
    for target, name, reason in TO_FILL:
        print(f'  {target} 의 {name}: {reason}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
