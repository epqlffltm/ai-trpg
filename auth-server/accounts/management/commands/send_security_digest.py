# auth-server/accounts/management/commands/send_security_digest.py

"""
보안 이벤트 요약 메일을 보내고, 오래된 보안 이벤트와 오래전에 버린 메일의 줄, 기간이 지난 재가입 막기(#634)를 지운다.

    uv run python manage.py send_security_digest

한 번 실행하고 끝난다. 한 시간에 한 번 돌게 등록해 둔다(리눅스의 cron, 윈도우의 작업 스케줄러).
새 사건이 없으면 메일을 보내지 않는다. 받는 사람은 .env 의 SECURITY_DIGEST_TO 다.
버린 메일은 보안 이벤트(mail_discarded)로 알린 것이라 같은 명령이 같은 기간(30일)으로 지운다.
재가입 막기는 사유마다 기간이 다르다(return_blocks.POLICIES). 한 시간에 한 번이면 넉넉하다.
주기 명령을 더 두지 않는다.
"""

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.outbox import delete_old_discarded_mail
from accounts.return_blocks import delete_expired_blocks
from accounts.security_digest import delete_old_security_events, report_new_security_events
from observability.jobs import run_as_job


class Command(BaseCommand):
    help = '새 보안 이벤트를 운영자에게 메일로 알리고, 보관 기간이 지난 기록과 버린 메일, 재가입 막기를 지운다.'

    def handle(self, *args, **options) -> None:
        if not settings.SECURITY_DIGEST_TO:
            self.stdout.write('SECURITY_DIGEST_TO 가 비어 있어 요약 메일을 보내지 않습니다.')

        # 작업의 식별자(job_id)를 건다. 이 일이 남긴 로그가 그 식별자로 묶인다(docs/observability.md)
        with run_as_job('security.send_digest'):
            reported = report_new_security_events()
            deleted = delete_old_security_events()
            deleted_mail = delete_old_discarded_mail()
            deleted_blocks = delete_expired_blocks(timezone.now())

        self.stdout.write(
            f'알린 보안 이벤트 {reported}건, 지운 오래된 기록 {deleted}건, 지운 버린 메일 {deleted_mail}건, '
            f'지운 재가입 막기 {deleted_blocks}건'
        )
