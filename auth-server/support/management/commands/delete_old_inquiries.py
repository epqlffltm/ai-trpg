# auth-server/support/management/commands/delete_old_inquiries.py

"""
보관 기간(1년, support/models.py 의 RETENTION)이 지난 문의를 지우는 관리 명령.

    uv run python manage.py delete_old_inquiries

문의에는 보낸 사람의 주소와 글이 있다. 정한 기간보다 오래 두지 않는다(2026-11-09 유저 결정).
그 전에 지우는 것은 운영자가 한다(하나씩, 고른 것, 상자 하나).
배포 환경에서는 하루에 한 번 실행한다(docker/cron/auth.crontab).
"""

from django.core.management.base import BaseCommand

from observability.jobs import run_as_job
from support.inquiries import delete_old_inquiries


class Command(BaseCommand):
    help = '보관 기간(1년)이 지난 문의를 지운다.'

    def handle(self, *args, **options) -> None:
        # 작업의 식별자(job_id)를 건다. 이 정리가 남긴 로그가 그 식별자로 묶인다(docs/observability.md)
        with run_as_job('inquiry.delete_old'):
            deleted_count = delete_old_inquiries()
        self.stdout.write(f'보관 기간이 지난 문의 {deleted_count}건을 지웠습니다.')
