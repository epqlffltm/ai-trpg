# auth-server/accounts/management/commands/send_outgoing_mail.py

"""
발송함의 메일을 보내는 워커.

    uv run python manage.py send_outgoing_mail            # 계속 돌면서 보낸다. Ctrl+C 로 멈춘다
    uv run python manage.py send_outgoing_mail --once     # 지금 보낼 수 있는 것만 보내고 끝난다

서버(runserver)와 따로 띄우는 프로세스다. 서버는 보낼 메일을 발송함에 적기만 하고,
이 워커가 꺼내 메일 서버로 보낸다. 워커가 멈춰 있으면 메일은 발송함에 쌓였다가,
5분 안에 워커가 다시 뜨면 나가고 그렇지 않으면 버려진다.

바퀴마다 발송함에 남은 메일의 수를 메트릭(background_jobs_queued{operation="mail.deliver_outgoing"})으로 적는다.
워커가 멈추면 이 값이 멈추고, 메일 서버가 죽으면 이 값이 는다.
"""

import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import OperationalError, close_old_connections

from accounts.outbox import DeliveryReport, count_waiting_mail, deliver_due_mail
from observability.heartbeat import beat
from observability.jobs import run_as_job
from observability.metrics import record_queued
from observability.spans import record_handled

# 한 묶음을 처리하는 일의 이름. 로그의 operation 칸에 들어간다(docs/observability.md)
DELIVER_OPERATION = 'mail.deliver_outgoing'
# 보낼 메일이 없을 때 다시 확인하기까지 쉬는 시간(초)
DEFAULT_INTERVAL_SECONDS = 1.0


def deliver_round() -> DeliveryReport:
    """
    한 바퀴. 지금 보낼 수 있는 메일을 보내고, 발송함에 남은 메일의 수를 적는다. 작업 하나로 돈다.

    작업의 식별자(job_id)를 건다. 이 바퀴가 남긴 로그가 그 식별자로 묶인다.
    보낼 것이 없던 바퀴는 추적을 남기지 않는다(observability/idle_rounds.py).
    """
    with run_as_job(DELIVER_OPERATION):
        report = deliver_due_mail()
        record_handled(report.handled)
        record_queued(DELIVER_OPERATION, count_waiting_mail())
    return report


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
            self._report(deliver_round())
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
            report = deliver_round()
        except OperationalError as exc:
            # 오류의 종류만 적는다. 오류의 글에는 DB 의 주소와 계정 이름이 들어 있다. 자세한 것은 로그에 남았다
            self.stderr.write(f'DB 에 접속하지 못했습니다. 잠시 뒤 다시 시도합니다: {type(exc).__name__}')
            return DeliveryReport()
        # DB 에 닿아 한 바퀴를 끝냈다. 닿지 못한 바퀴는 심장박동을 바꾸지 않는다(observability/heartbeat.py)
        beat(settings.HEARTBEAT_FILE)
        return report

    def _report(self, report: DeliveryReport) -> None:
        """한 일이 있을 때만 출력한다. 1초마다 "0건" 을 찍지 않는다."""
        if report.handled == 0:
            return
        self.stdout.write(f'보냄 {report.sent}건, 다시 시도 예정 {report.retried}건, 버림 {report.discarded}건')
