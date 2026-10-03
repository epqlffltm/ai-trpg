# auth-server/accounts/management/commands/send_security_digest.py

"""
보안 이벤트 요약 메일을 보내고, 오래된 보안 이벤트를 지운다.

    uv run python manage.py send_security_digest

한 번 실행하고 끝난다. 한 시간에 한 번 돌게 등록해 둔다(리눅스의 cron, 윈도우의 작업 스케줄러).
새 사건이 없으면 메일을 보내지 않는다. 받는 사람은 .env 의 SECURITY_DIGEST_TO 다.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from accounts.security_digest import delete_old_security_events, report_new_security_events


class Command(BaseCommand):
    help = '새 보안 이벤트를 운영자에게 메일로 알리고, 보관 기간이 지난 기록을 지운다.'

    def handle(self, *args, **options) -> None:
        if not settings.SECURITY_DIGEST_TO:
            self.stdout.write('SECURITY_DIGEST_TO 가 비어 있어 요약 메일을 보내지 않습니다.')

        reported = report_new_security_events()
        deleted = delete_old_security_events()

        self.stdout.write(f'알린 보안 이벤트 {reported}건, 지운 오래된 기록 {deleted}건')
