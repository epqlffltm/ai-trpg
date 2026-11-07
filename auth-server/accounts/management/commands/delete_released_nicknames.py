# auth-server/accounts/management/commands/delete_released_nicknames.py

"""
묶는 기간이 지난 버린 닉네임의 줄을 지우는 관리 명령.

    uv run python manage.py delete_released_nicknames

닉네임을 바꾸거나 계정을 비우면(탈퇴, 만 14세 미만) 쓰던 이름을 30일 묶는다(accounts/nicknames.py).
기간이 지난 줄은 검사에서 빠지지만, 탈퇴한 사람의 옛 이름이 남지 않게 지운다.
배포 환경에서는 하루에 한 번 실행한다(docker/cron/auth.crontab).
"""

from django.core.management.base import BaseCommand

from accounts.nicknames import delete_expired_released_nicknames
from observability.jobs import run_as_job


class Command(BaseCommand):
    help = '묶는 기간이 지난 버린 닉네임을 지운다.'

    def handle(self, *args, **options) -> None:
        # 작업의 식별자(job_id)를 건다. 이 정리가 남긴 로그가 그 식별자로 묶인다(docs/observability.md)
        with run_as_job('account.delete_released_nicknames'):
            deleted_count = delete_expired_released_nicknames()
        self.stdout.write(f'묶는 기간이 지난 닉네임 {deleted_count}건을 지웠습니다.')
