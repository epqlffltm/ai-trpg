# auth-server/accounts/management/commands/delete_unverified_users.py

"""
보관 시간이 지난 미인증 계정을 지우는 관리 명령.

    uv run python manage.py delete_unverified_users

가입 요청이 들어올 때도 겹치는 미인증 계정은 그 자리에서 지운다.
이 명령은 아무도 다시 요청하지 않아 남아 있는 계정을 청소한다.
배포 환경에서는 하루에 한 번 실행한다.
"""

from django.core.management.base import BaseCommand

from accounts.services import delete_expired_pending_accounts
from observability.jobs import run_as_job


class Command(BaseCommand):
    help = '보관 시간이 지난 미인증 계정을 지운다.'

    def handle(self, *args, **options) -> None:
        # 작업의 식별자(job_id)를 건다. 이 정리가 남긴 로그가 그 식별자로 묶인다(docs/observability.md)
        with run_as_job('account.delete_unverified'):
            deleted_count = delete_expired_pending_accounts()
        self.stdout.write(f'미인증 계정과 딸린 기록 {deleted_count}건을 지웠습니다.')