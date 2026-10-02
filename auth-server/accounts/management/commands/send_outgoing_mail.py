# auth-server/accounts/management/commands/send_outgoing_mail.py

"""
발송함의 메일을 보내는 워커.

    uv run python manage.py send_outgoing_mail            # 계속 돌면서 보낸다. Ctrl+C 로 멈춘다
    uv run python manage.py send_outgoing_mail --once     # 지금 보낼 수 있는 것만 보내고 끝난다

서버(runserver)와 따로 띄우는 프로세스다. 서버는 보낼 메일을 발송함에 적기만 하고,
이 워커가 꺼내 메일 서버로 보낸다. 워커가 멈춰 있으면 메일은 발송함에 쌓였다가,
5분 안에 워커가 다시 뜨면 나가고 그렇지 않으면 버려진다.
"""

import time

from django.core.management.base import BaseCommand
from django.db import OperationalError, close_old_connections

from accounts.outbox import DeliveryReport, deliver_due_mail

# 보낼 메일이 없을 때 다시 확인하기까지 쉬는 시간(초)
DEFAULT_INTERVAL_SECONDS = 1.0


class Command(BaseCommand):
    help = '발송함에 쌓인 메일을 보낸다.'

    def add_arguments(self, parser) -> None:
        parser.add_argument('--once', action='store_true', help='한 번만 처리하고 끝낸다.')
        parser.add_argument(
            '--interval',
            type=float,
            default=DEFAULT_INTERVAL_SECONDS,
            help='보낼 메일이 없을 때 쉬는 시간(초).',
        )

    def handle(self, *args, **options) -> None:
        if options['once']:
            self._report(deliver_due_mail())
            return

        self.stdout.write('메일 워커를 시작합니다. Ctrl+C 로 멈춥니다.')
        try:
            self._run_forever(options['interval'])
        except KeyboardInterrupt:
            self.stdout.write('메일 워커를 멈춥니다.')

    def _run_forever(self, interval: float) -> None:
        while True:
            report = self._deliver_safely()
            self._report(report)
            # 처리한 것이 있으면 쉬지 않고 바로 다음 묶음을 본다
            if report.handled == 0:
                time.sleep(interval)

    def _deliver_safely(self) -> DeliveryReport:
        """
        한 묶음을 처리한다. DB 에 잠깐 접속할 수 없어도 워커가 죽지 않게 한다.

        오래 도는 프로세스는 끊긴 DB 연결을 쥐고 있을 수 있다.
        매번 확인해서 끊긴 연결은 버리고 새로 맺게 한다.
        """
        close_old_connections()
        try:
            return deliver_due_mail()
        except OperationalError as exc:
            self.stderr.write(f'DB 에 접속하지 못했습니다. 잠시 뒤 다시 시도합니다: {exc}')
            return DeliveryReport()

    def _report(self, report: DeliveryReport) -> None:
        """한 일이 있을 때만 출력한다. 1초마다 "0건" 을 찍지 않는다."""
        if report.handled == 0:
            return
        self.stdout.write(f'보냄 {report.sent}건, 다시 시도 예정 {report.retried}건, 버림 {report.discarded}건')
