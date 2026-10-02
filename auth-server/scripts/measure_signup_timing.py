# auth-server/scripts/measure_signup_timing.py

"""
회원가입 응답 시간이 이메일의 가입 여부에 따라 달라지는지 잰다.

응답 본문을 똑같이 맞춰도, 이미 가입된 이메일일 때 비밀번호 해싱을 건너뛰면
응답이 훨씬 빨라져 걸린 시간으로 가입 여부가 드러난다. 이 스크립트는 세 가지를 잰다.
  1. 새 이메일로 가입
  2. 이미 가입된 이메일로 가입 (지금의 구현: 해싱을 수행한다)
  3. 이미 가입된 이메일로 가입 (해싱을 건너뛴다고 가정한 경우. 비교용)

개발용 DB 에 측정용 계정을 만들었다가 끝나면 지운다. 메일은 보내지 않는다.

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

from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

from accounts.models import User  # noqa: E402

SIGNUP_URL = '/api/v1/auth/signup'
PASSWORD = 'correct-horse-battery'
DEFAULT_ROUNDS = 100

# 측정용 계정의 이메일은 모두 이 도메인을 쓴다. 끝나고 이 도메인의 계정만 지운다
MEASURE_DOMAIN = 'signup-timing.invalid'
REGISTERED_EMAIL = f'registered@{MEASURE_DOMAIN}'


def unique_payload(email: str | None = None) -> dict:
    """아이디와 닉네임이 다른 요청과 겹치지 않는 가입 요청을 만든다."""
    token = uuid.uuid4().hex[:12]
    return {
        'username': f'tm_{token}',
        'email': email or f'{token}@{MEASURE_DOMAIN}',
        'nickname': f'측정_{token}',
        'password': PASSWORD,
    }


def measure_signup_ms(client: Client, payload: dict) -> float:
    """가입 요청 한 번에 걸린 시간을 밀리초로 돌려준다."""
    started = time.perf_counter()
    response = client.post(SIGNUP_URL, payload, content_type='application/json')
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert response.status_code == 202, response.content
    return elapsed_ms


def measure_new_email(client: Client, rounds: int) -> list[float]:
    return [measure_signup_ms(client, unique_payload()) for _ in range(rounds)]


def measure_registered_email(client: Client, rounds: int) -> list[float]:
    return [measure_signup_ms(client, unique_payload(REGISTERED_EMAIL)) for _ in range(rounds)]


def create_registered_user() -> None:
    User.objects.create_user(
        username='tm_registered',
        email=REGISTERED_EMAIL,
        nickname='측정_가입됨',
        password=PASSWORD,
        email_verified_at=timezone.now(),
    )


def delete_measurement_users() -> None:
    User.objects.filter(email__endswith=f'@{MEASURE_DOMAIN}').delete()


def report(label: str, samples: list[float], baseline: float) -> None:
    median = statistics.median(samples)
    print(f'{label:<34} 중앙값 {median:8.1f} ms   새 이메일 대비 {baseline / median:5.2f}배 빠름')


def main() -> None:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ROUNDS
    # 테스트용 클라이언트의 기본 호스트 이름은 ALLOWED_HOSTS 에 없다. localhost 로 요청한다
    client = Client(SERVER_NAME='localhost')
    delete_measurement_users()
    create_registered_user()

    try:
        # 메일 발송 시간은 재지 않는다. 해싱 유무의 차이만 본다
        with patch('accounts.mail.send_mail'):
            # 첫 요청은 모듈을 불러오느라 느리다. 한 번 버리고 시작한다
            measure_signup_ms(client, unique_payload())

            new_email = measure_new_email(client, rounds)
            registered = measure_registered_email(client, rounds)
            with patch('accounts.services.make_password', return_value='not-hashed'):
                registered_without_hash = measure_registered_email(client, rounds)
    finally:
        delete_measurement_users()

    baseline = statistics.median(new_email)
    print(f'요청 {rounds}회씩 측정')
    report('새 이메일', new_email, baseline)
    report('가입된 이메일 (해싱 수행, 현재)', registered, baseline)
    report('가입된 이메일 (해싱 생략, 비교용)', registered_without_hash, baseline)


if __name__ == '__main__':
    main()