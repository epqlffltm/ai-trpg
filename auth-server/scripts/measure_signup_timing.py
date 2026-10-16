# auth-server/scripts/measure_signup_timing.py

"""
가입의 1단계(이메일을 보내는 요청) 응답 시간이 이메일의 가입 여부에 따라 달라지는지 잰다.

응답 본문은 같다. 새 이메일이면 코드를 발급하고 코드 메일을, 가입된 이메일이면 같은 자리의 횟수만 세고
안내 메일을 발송함에 적는다. 둘 다 DB 쓰기가 두 번이고 비밀번호 해싱은 없다(비밀번호는 3단계에서 받는다, #271).
  1. 새 이메일
  2. 이미 가입된 이메일

이메일마다 처음 보내는 요청을 잰다. 같은 이메일을 거듭 보내면 1분 대기에 걸려 쓰기 없이 끝나고, 그것은 두 경우가 같다.
개발용 DB 에 측정용 계정과 가입 코드를 만들었다가 끝나면 지운다. 메일은 보내지 않는다.

    uv run python scripts/measure_signup_timing.py
    uv run python scripts/measure_signup_timing.py 50
"""

import os
import statistics
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch

# 이 파일은 scripts/ 안에 있다. manage.py 가 있는 폴더를 import 경로에 넣는다
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402

django.setup()

from django.test import Client, override_settings  # noqa: E402
from django.utils import timezone  # noqa: E402

from accounts.models import SignupCode, User  # noqa: E402

SIGNUP_URL = '/api/v1/auth/signup'
PASSWORD = 'correct-horse-battery'
DEFAULT_ROUNDS = 100

# 측정용 이메일은 모두 이 도메인을 쓴다. 끝나고 이 도메인의 계정과 가입 코드만 지운다
MEASURE_DOMAIN = 'signup-timing.invalid'


def fresh_email() -> str:
    return f'{uuid.uuid4().hex[:12]}@{MEASURE_DOMAIN}'


def measure_signup_ms(client: Client, email: str) -> float:
    """1단계 요청 한 번에 걸린 시간을 밀리초로 돌려준다."""
    started = time.perf_counter()
    response = client.post(SIGNUP_URL, {'email': email}, content_type='application/json')
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert response.status_code == 202, response.content
    return elapsed_ms


def create_registered_users(rounds: int) -> list[str]:
    """가입을 마친 측정용 계정을 rounds 개 만들고 그 이메일들을 돌려준다."""
    emails = [fresh_email() for _ in range(rounds)]
    for index, email in enumerate(emails):
        User.objects.create_user(
            username=f'tm_{index:04d}_{uuid.uuid4().hex[:6]}',
            email=email,
            nickname=f'측정_{index:04d}_{uuid.uuid4().hex[:6]}',
            password=PASSWORD,
            email_verified_at=timezone.now(),
        )
    return emails


def delete_measurement_rows() -> None:
    User.objects.filter(email__endswith=f'@{MEASURE_DOMAIN}').delete()
    SignupCode.objects.filter(email__endswith=f'@{MEASURE_DOMAIN}').delete()


def report(label: str, samples: list[float], baseline: float) -> None:
    median = statistics.median(samples)
    print(f'{label:<20} 중앙값 {median:8.2f} ms   새 이메일 대비 {baseline / median:5.2f}배')


def main() -> None:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ROUNDS
    # 테스트용 클라이언트의 기본 호스트 이름은 ALLOWED_HOSTS 에 없다. localhost 로 요청한다
    client = Client(SERVER_NAME='localhost')
    delete_measurement_rows()
    registered_emails = create_registered_users(rounds)

    try:
        # 메일 발송 시간은 재지 않는다. 가입 여부에 따른 처리의 차이만 본다.
        # IP 의 시도 제한(1시간에 10번)도 끈다. 한 IP 에서 수백 번 보내는 측정이다
        with patch('accounts.outbox.send_mail'), override_settings(ATTEMPT_LIMITS_ENABLED=False):
            # 첫 요청은 모듈을 불러오느라 느리다. 한 번 버리고 시작한다
            measure_signup_ms(client, fresh_email())

            # 두 경우를 번갈아 잰다. 한쪽만 먼저 재면 DB 의 캐시가 데워지는 정도가 달라진다
            new_email, registered = [], []
            for email in registered_emails:
                new_email.append(measure_signup_ms(client, fresh_email()))
                registered.append(measure_signup_ms(client, email))
    finally:
        delete_measurement_rows()

    baseline = statistics.median(new_email)
    print(f'요청 {rounds}회씩 측정')
    report('새 이메일', new_email, baseline)
    report('가입된 이메일', registered, baseline)


if __name__ == '__main__':
    main()
