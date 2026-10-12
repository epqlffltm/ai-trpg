# auth-server/accounts/management/commands/request_welcome_credits.py

"""
이미 가입을 마친 계정들에 환영 크레딧을 주라고 적어 두는 관리 명령.

    uv run python manage.py request_welcome_credits

가입할 때 저절로 받는 기능이 생기기 전에 만든 계정을 위한 것이다. 한 번 돌리면 된다.
여러 번 돌려도 같은 메일함에 두 번 적지 않는다. 적어 둔 것을 결제 서버에 맡기는 일은 워커가 한다
(manage.py send_welcome_credits). 전에 이미 받은 사용자는 결제 서버가 다시 주지 않는다.
"""

from django.core.management.base import BaseCommand

from accounts.welcome_credit import request_welcome_credits_for_verified_users
from observability.jobs import run_as_job


class Command(BaseCommand):
    help = '이미 가입을 마친 계정들에 환영 크레딧을 주라고 적어 둔다.'

    def handle(self, *args, **options) -> None:
        # 작업의 식별자(job_id)를 건다. 이 일이 남긴 로그가 그 식별자로 묶인다(docs/observability.md)
        with run_as_job('welcome_credit.request_existing'):
            created_count = request_welcome_credits_for_verified_users()
        self.stdout.write(f'환영 크레딧을 받을 메일함 {created_count}개를 새로 적었습니다.')
