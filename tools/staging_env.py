# tools/staging_env.py

"""
staging(VM)의 .env 일곱(루트와 서버 여섯)을 새로 만든다. VM 을 처음 준비할 때 한 번 쓴다(docs/operations/staging-vm.md).

    사용(VM 의 저장소 루트에서):
        python3 tools/staging_env.py --domain <도메인> --acme-email <메일> \\
            --llm-base-url http://<집 PC 의 Tailscale 주소>:11434/v1 \\
            --s3-bucket <버킷> --image-bucket <그림 버킷> \\
            --age-recipients "<주 열쇠의 공개키> <확인 열쇠의 공개키>"

하는 일(차례대로):
  1. tools/fill_env.py 로 .env 일곱을 .env.example 에서 만들고 비밀을 난수로 채운다.
     어느 비밀끼리 짝인지, DB 비밀번호가 어디에 들어가는지는 그 도구의 표(SECRETS)가 정한다. 여기에 다시 적지 않는다.
     서버끼리의 짝 비밀(# BILLING_SECRET= 등)은 그 도구가 주석을 풀어 둔다
  2. 그 표의 비밀 가운데 아직 주석으로 막힌 줄을 값 그대로 푼다. 남는 것은 한 파일만 아는 비밀이다
     (trpg-server 의 SIGNAL_SECRET, AI_LOG_HMAC_KEY). fill_env.py 는 켜면 동작이 바뀌어 막아 두지만 staging 에서는 켠다:
     SIGNAL_SECRET 은 서버를 다시 띄워도 같은 값이 되고, AI_LOG_HMAC_KEY 는 호출 기록에 입력의 지문을 남긴다
  3. staging 에서만 쓰는 값을 적는다(STAGING_VALUES 와 명령줄의 값). 주석으로 막힌 줄이면 풀어서 적는다

일곱 가운데 하나라도 이미 있으면 아무것도 만들지 않고 멈춘다. 두 번 돌려 staging 의 값을 덮는 일을 막는다.
이미 있는 .env 의 빈 비밀만 채우려면 tools/fill_env.py 를 쓴다. 파일은 주인만 읽는다(600).

서버의 .env 에는 DEBUG, APP_ENVIRONMENT, DATABASE_URL 을 적지 않는다.
docker-compose.yml 과 docker-compose.staging.yml 이 environment 로 덮는다(DB 주소의 비밀번호는 루트 .env 에서 가져간다).

사람이 채울 것: 모델 창구의 키(trpg-server/.env 의 ZAI_API_KEY),
S3 의 접근 키(루트 .env 의 BACKUP_AWS_*, IMAGE_STORE_*).
비워 두면 docker compose 가 뜨기를 거부하거나(S3 키) 그 창구의 모델을 부르지 않는다(모델 키).
그림 저장소의 비밀 키(IMAGE_STORE_SECRET_ACCESS_KEY)는 fill_env.py 가 로컬의 흉내를 위해 난수로 채우지만,
staging 에서는 그 버킷만 쓰는 IAM 사용자의 키라서 비운다.
JWT 의 서명 키(auth-server/keys/)는 만들지 않는다. 문서의 openssl 명령으로 만든다.

VM 에는 uv 가 없어 Ubuntu 에 든 python3 로 돌린다. 표준 라이브러리만 쓴다. 테스트는 tools/test_staging_env.py 다.
"""

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from fill_env import ENV_FILES, LINE, SECRETS, read_lines, report, run

REPO_ROOT = Path(__file__).resolve().parents[1]
# 새로 만드는 파일이 주인만 읽게 한다(fill_env.py 가 쓰는 순간부터 rw-------)
PRIVATE_UMASK = 0o077
# 예시에 없는 이름을 끝에 더할 때 그 앞에 붙이는 줄
APPENDED_HEADER = '# --- tools/staging_env.py 가 더한 값 ---\n'

# staging 에서 늘 같은 값. 파일마다 이름과 값이다
STAGING_VALUES = {
    '.env': {
        'COMPOSE_FILE': 'docker-compose.yml:docker-compose.staging.yml',
        'COMPOSE_PROFILES': 'app,observability',
        'APP_ENVIRONMENT': 'staging',
        # 인증 서버의 테스트용 DB 를 만들 권한. 운영에서는 주지 않는다(docker/postgres/init/01-auth-role.sql)
        'AUTH_DB_ALLOW_TEST_DB': 'false',
        'OTEL_EXPORTER_OTLP_ENDPOINT': 'http://alloy:4318',
        # 사람이 채운다. 비워 두면 compose 가 뜨기를 거부한다(${...:?})
        'BACKUP_AWS_ACCESS_KEY_ID': '',
        'BACKUP_AWS_SECRET_ACCESS_KEY': '',
        # 사람이 채운다. 그림 버킷만 쓰는 IAM 사용자의 키다(docker/object-store/iam-policy.json).
        # 비밀 키는 fill_env.py 가 로컬의 흉내를 위해 채운 난수를 지운다. 비워 두면 compose 가 뜨기를 거부한다
        'IMAGE_STORE_ACCESS_KEY_ID': '',
        'IMAGE_STORE_SECRET_ACCESS_KEY': '',
    },
    'trpg-server/.env': {
        'NARRATOR': 'llm',
        # 서술 모델. 모델 목록에 넣는 법은 docs/operations/staging-vm.md 의 "모델"
        'LLM_MODEL': 'glm-4-7-flash',
        'LLM_FALLBACK_MODELS': '',
        # 사람이 채운다(Z.ai 의 API 키)
        'ZAI_API_KEY': '',
    },
    # 진짜 결제 대행사는 아직 붙이지 않는다
    'billing-server/.env': {'PAYMENT_PROVIDER': 'fake'},
}
# 비워 두어도 되는 비밀: 쓰지 않는 창구와 메일, 경보를 받는 곳(README 의 "경보", 적은 것만 켜진다).
# 쓰게 되면 사람이 적는다.
# 이 밖의 비밀은 모두 채운다(test_staging_env.py 가 본다)
OPTIONAL_SECRETS = frozenset(
    {
        'SMTP_PASSWORD',
        'OPENAI_API_KEY',
        'ANTHROPIC_API_KEY',
        'GEMINI_API_KEY',
        'DEEPINFRA_API_KEY',
        'TOSS_SECRET_KEY',
        'TOSS_CLIENT_KEY',
        'ALERT_SMTP_PASSWORD',
    }
)
# 사람이 채울 것: (파일, 이름, 까닭)
TO_FILL = (
    ('trpg-server/.env', 'ZAI_API_KEY', 'Z.ai 의 API 키(GLM-4.7-Flash)'),
    ('.env', 'BACKUP_AWS_ACCESS_KEY_ID', 'S3 의 접근 키(docker/backup-offsite/iam-policy.json 의 권한)'),
    ('.env', 'BACKUP_AWS_SECRET_ACCESS_KEY', 'S3 의 비밀 접근 키'),
    ('.env', 'IMAGE_STORE_ACCESS_KEY_ID', '그림 버킷의 접근 키(docker/object-store/iam-policy.json 의 권한)'),
    ('.env', 'IMAGE_STORE_SECRET_ACCESS_KEY', '그림 버킷의 비밀 접근 키'),
)


@dataclass(frozen=True)
class Options:
    """명령줄에서 받는 staging 의 값. 비밀이 아니다."""

    domain: str
    acme_email: str
    llm_base_url: str
    s3_bucket: str
    image_bucket: str
    age_recipients: str
    s3_region: str = 'ap-northeast-2'


def secret_lines() -> dict[str, set[str]]:
    """
    fill_env.py 가 채우는 비밀의 이름들. 파일마다다. staging 에서는 모두 켠다.
    DB 주소 안의 비밀번호는 줄이 아니라 뺀다.
    """
    names: dict[str, set[str]] = {}
    for secret in SECRETS:
        for spot in secret.spots:
            if not spot.url:
                names.setdefault(spot.file, set()).add(spot.key)
    return names


def option_values(options: Options) -> dict[str, str]:
    """명령줄의 값을 루트 .env 의 이름으로."""
    return {
        'DOMAIN': options.domain,
        'ACME_EMAIL': options.acme_email,
        'GAME_LLM_BASE_URL': options.llm_base_url,
        'BACKUP_S3_BUCKET': options.s3_bucket,
        'BACKUP_S3_REGION': options.s3_region,
        'BACKUP_AGE_RECIPIENTS': options.age_recipients,
        'IMAGE_STORE_BUCKET': options.image_bucket,
        # 그림 버킷도 백업과 같은 리전에 둔다
        'IMAGE_STORE_REGION': options.s3_region,
    }


def planned_values(options: Options) -> dict[str, dict[str, str]]:
    """파일마다 적을 이름과 값."""
    plan = {target: dict(STAGING_VALUES.get(target, {})) for target in ENV_FILES}
    plan['.env'].update(option_values(options))
    return plan


def assignments(lines: list[str], key: str) -> tuple[int | None, list[int]]:
    """그 이름의 줄들. (주석이 아닌 첫 줄, 주석으로 막힌 줄들)이다."""
    active = None
    commented = []
    for index, line in enumerate(lines):
        match = LINE.match(line)
        if not match or match['key'] != key:
            continue
        if match['comment']:
            commented.append(index)
        elif active is None:
            active = index
    return active, commented


def uncomment(line: str) -> str:
    """주석으로 막힌 줄의 # 을 뗀다. 값은 그대로다."""
    return line[len(LINE.match(line)['comment']) :]


def enable(lines: list[str], key: str) -> None:
    """
    주석으로 막힌 그 이름의 줄을 값 그대로 푼다. 이미 켜진 줄이 있으면 그대로 둔다.
    fill_env.py 가 값을 넣는 곳과 같은, 처음 막힌 줄을 푼다(fill_env.find_line).
    """
    active, commented = assignments(lines, key)
    if active is None and commented:
        lines[commented[0]] = uncomment(lines[commented[0]])


def set_value(lines: list[str], key: str, value: str) -> None:
    """
    그 이름의 줄을 "이름=값" 으로 바꾼다. 주석이 아닌 줄이 있으면 그 줄을, 없으면 주석으로 막힌 마지막 줄을 풀어서 쓴다
    (루트 .env.example 은 같은 이름의 로컬용 줄 뒤에 staging 용 줄을 둔다). 둘 다 없으면 끝에 더한다.
    """
    active, commented = assignments(lines, key)
    index = active if active is not None else (commented[-1] if commented else None)
    if index is None:
        if APPENDED_HEADER not in lines:
            if lines and not lines[-1].endswith('\n'):
                lines[-1] += '\n'
            lines.extend(['\n', APPENDED_HEADER])
        lines.append(f'{key}={value}\n')
        return
    newline = LINE.match(lines[index])['newline'] or '\n'
    lines[index] = f'{key}={value}{newline}'


def apply_staging(path: Path, enabled: set[str], values: dict[str, str]) -> None:
    """만든 .env 하나에 비밀의 줄을 풀고 staging 의 값을 적는다."""
    lines = read_lines(path)
    for key in sorted(enabled):
        enable(lines, key)
    for key, value in values.items():
        set_value(lines, key, value)
    path.write_text(''.join(lines), encoding='utf-8', newline='')


def existing_targets(root: Path) -> list[str]:
    """이미 있는 대상 파일들. 하나라도 있으면 만들지 않는다."""
    return [target for target in ENV_FILES if (root / target).exists()]


def create(root: Path, options: Options) -> str:
    """일곱을 만들고 staging 의 값을 적는다. fill_env.py 가 한 일을 글로 돌려준다(비밀의 값은 없다)."""
    previous = os.umask(PRIVATE_UMASK)
    try:
        files, outcomes, external = run(root, dry_run=False)
        enabled = secret_lines()
        for target, values in planned_values(options).items():
            apply_staging(root / target, enabled.get(target, set()), values)
    finally:
        os.umask(previous)
    return report(files, outcomes, external, dry_run=False)


def parse_options(argv: list[str]) -> Options:
    """명령줄을 읽는다. age 의 공개키는 둘이어야 한다(주 열쇠, 확인 열쇠)."""
    parser = argparse.ArgumentParser(description='staging(VM)의 .env 일곱을 새로 만든다')
    parser.add_argument('--domain', required=True, help='이 VM 의 도메인')
    parser.add_argument('--acme-email', required=True, help="Let's Encrypt 에 알리는 메일")
    parser.add_argument(
        '--llm-base-url', required=True, help='집 PC 의 Ollama(Tailscale 주소), 예: http://100.x.y.z:11434/v1'
    )
    parser.add_argument('--s3-bucket', required=True, help='바깥 백업의 S3 버킷')
    parser.add_argument('--image-bucket', required=True, help='그림의 S3 버킷. 백업의 버킷과 다르다')
    parser.add_argument('--s3-region', default='ap-northeast-2', help='두 버킷의 리전')
    parser.add_argument(
        '--age-recipients', required=True, help='age 의 공개키 둘(주 열쇠, 확인 열쇠)을 빈칸으로 이은 것'
    )
    parsed = parser.parse_args(argv)
    recipients = parsed.age_recipients.split()
    if len(recipients) != 2 or not all(key.startswith('age1') for key in recipients):
        parser.error('--age-recipients 는 age 의 공개키(age1...) 둘이다(주 열쇠, 확인 열쇠)')
    if parsed.image_bucket == parsed.s3_bucket:
        # 두 키의 권한이 정반대다. 백업의 키는 지우지 못하고 그림의 키는 지운다
        # (docs/architecture/deployment.md 의 "그림 저장소")
        parser.error('--image-bucket 은 --s3-bucket(백업)과 다른 버킷이어야 한다')
    return Options(
        domain=parsed.domain,
        acme_email=parsed.acme_email,
        llm_base_url=parsed.llm_base_url,
        s3_bucket=parsed.s3_bucket,
        image_bucket=parsed.image_bucket,
        s3_region=parsed.s3_region,
        age_recipients=' '.join(recipients),
    )


def to_fill_report() -> str:
    """사람이 채울 것의 목록."""
    return '\n'.join(['사람이 채울 것:', *(f'  {target} 의 {name}: {reason}' for target, name, reason in TO_FILL)])


def main(argv: list[str], root: Path = REPO_ROOT) -> int:
    """만들고 한 일과 사람이 채울 것을 찍는다. 이미 있는 파일이 있으면 1 로 끝난다."""
    options = parse_options(argv)
    existing = existing_targets(root)
    if existing:
        print(f'이미 있다: {", ".join(existing)}. 덮어쓰지 않는다. 아무것도 만들지 않았다', file=sys.stderr)
        return 1
    print(create(root, options))
    print(to_fill_report())
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
