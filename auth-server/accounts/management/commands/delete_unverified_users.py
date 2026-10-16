# auth-server/accounts/management/commands/delete_unverified_users.py

"""
가입을 마치지 않은 이메일의 오래된 가입 코드 행을 지우는 관리 명령.

    uv run python manage.py delete_unverified_users

가입은 이메일을 먼저 확인하고 그 뒤에 인증된 계정을 만든다(#271). 미인증 계정은 더 생기지 않는다.
대신 코드를 받기만 하고 끝내지 않은 이메일의 행(SignupCode)이 남는다. 마지막 발급에서 발급 제한의 구간이
지난 행은 지킬 것이 없어 지운다. 이름은 cron(docker/cron/auth.crontab)과 작업 이름을 바꾸지 않으려고 그대로 둔다.
배포 환경에서는 하루에 한 번 실행한다.
"""

from django.core.management.base import BaseCommand

from accounts.services import delete_stale_signup_codes
from observability.jobs import run_as_job


class Command(BaseCommand):
    help = '가입을 마치지 않은 이메일의 오래된 가입 코드를 지운다.'

    def handle(self, *args, **options) -> None:
        # 작업의 식별자(job_id)를 건다. 이 정리가 남긴 로그가 그 식별자로 묶인다(docs/observability.md)
        with run_as_job('account.delete_unverified'):
            deleted_count = delete_stale_signup_codes()
        self.stdout.write(f'오래된 가입 코드 {deleted_count}건을 지웠습니다.')
