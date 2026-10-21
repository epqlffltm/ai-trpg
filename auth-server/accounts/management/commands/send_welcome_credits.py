# auth-server/accounts/management/commands/send_welcome_credits.py

"""
결제 서버에 맡길 일을 보내는 워커. 한 바퀴에 차례로 한다.
  - 환영 크레딧과 결제 자격(#336)을 보낸다
  - 유예가 지난 탈퇴를 마치고(계정을 비운다), 다른 서버에 탈퇴를 알린다(#603). 지금 알릴 곳은 결제 서버뿐이다

    uv run python manage.py send_welcome_credits            # 계속 돌면서 맡긴다. Ctrl+C 로 멈춘다
    uv run python manage.py send_welcome_credits --once     # 지금 맡길 수 있는 것만 맡기고 끝난다

서버(runserver)와 따로 띄우는 프로세스다. 서버는 본인인증, 보호자 동의, 철회 때 할 일을 적기만 하고,
이 워커가 꺼내 결제 서버에 맡긴다. 워커나 결제 서버가 멈춰 있으면 줄이 쌓였다가, 다시 뜨면 나간다.
메일과 달리 버리지 않는다. 늦게 줘도 쓸모가 있다.

이름은 처음 맡은 일(환영 크레딧)의 것이다. compose 의 auth-welcome-credits 와 함께 쓰여서 바꾸지 않았다.
"""

import time
from dataclasses import dataclass, field

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, close_old_connections

from accounts import payment_eligibility, withdrawal
from accounts.welcome_credit import DELIVER_OPERATION, DeliveryReport, deliver_due_welcome_credits
from observability.heartbeat import beat
from observability.jobs import run_as_job
from observability.spans import record_handled

# 맡길 것이 없을 때 다시 확인하기까지 쉬는 시간(초). 메일과 달리 몇 초 늦어도 된다
DEFAULT_INTERVAL_SECONDS = 5.0


@dataclass(frozen=True)
class WithdrawalRound:
    """한 바퀴에 탈퇴로 한 일. 마친 계정의 수와 알린 결과다."""

    completed: int = 0
    notices: withdrawal.DeliveryReport = field(default_factory=withdrawal.DeliveryReport)

    @property
    def done(self) -> int:
        """이번에 끝낸 일. 다시 시도할 것은 세지 않는다(그것만 있으면 워커가 쉰다)."""
        return self.completed + self.notices.sent


class Command(BaseCommand):
    help = '환영 크레딧과 결제 자격을 결제 서버에 맡기고, 유예가 지난 탈퇴를 마치고 알린다.'

    def add_arguments(self, parser) -> None:
        parser.add_argument('--once', action='store_true', help='한 번만 처리하고 끝낸다.')
        parser.add_argument(
            '--interval',
            type=float,
            default=DEFAULT_INTERVAL_SECONDS,
            help='맡길 것이 없을 때 쉬는 시간(초).',
        )

    def handle(self, *args, **options) -> None:
        # 비밀이 없으면 모든 요청이 실패한다. 줄마다 실패를 쌓지 않고 여기서 멈춘다
        if not settings.BILLING_SECRET:
            raise CommandError(
                'BILLING_SECRET 이 없습니다. '
                'auth-server/.env 에 결제 서버의 AUTH_SERVER_SECRET 과 같은 값을 적어 주세요. '
                '(전에 BILLING_SERVICE_SECRET 으로 적어 두었다면 이름이 바뀌었습니다. '
                'README 의 "환영 크레딧"을 봐 주세요.)'
            )

        if options['once']:
            report, eligibility, withdrawals = self._deliver_round()
            self._report(report)
            self._report_eligibility(eligibility)
            self._report_withdrawals(withdrawals)
            return

        self.stdout.write('환영 크레딧 워커를 시작합니다. Ctrl+C 로 멈춥니다.')
        try:
            self._run_forever(options['interval'])
        except KeyboardInterrupt:
            self.stdout.write('환영 크레딧 워커를 멈춥니다.')

    def _run_forever(self, interval: float) -> None:
        while True:
            report, eligibility, withdrawals = self._deliver_safely()
            self._report(report)
            self._report_eligibility(eligibility)
            self._report_withdrawals(withdrawals)
            # 줄 것이 더 있을 수 있으면 쉬지 않고 바로 다음 묶음을 본다.
            # 맡기지 못한 것만 있었으면 쉰다. 그 줄들은 다음 시도 시각이 뒤로 밀려 있다
            if report.granted + report.skipped + eligibility.sent + withdrawals.done == 0:
                time.sleep(interval)

    def _deliver_round(self) -> tuple[DeliveryReport, payment_eligibility.DeliveryReport, WithdrawalRound]:
        """
        일마다 한 묶음씩 처리한다. 일마다 작업의 식별자(job_id)를 걸어, 그 일이 남긴 로그를 그 식별자로 묶는다.

        할 일이 없던 바퀴는 추적을 남기지 않는다(observability/idle_rounds.py).
        탈퇴는 마치는 것을 먼저 한다. 이번에 마친 계정의 알림이 같은 바퀴에 나간다.
        """
        with run_as_job(DELIVER_OPERATION):
            report = deliver_due_welcome_credits()
            record_handled(report.handled)
        with run_as_job(payment_eligibility.DELIVER_OPERATION):
            eligibility = payment_eligibility.deliver_due_eligibility()
            record_handled(eligibility.handled)
        with run_as_job(withdrawal.COMPLETE_OPERATION):
            completed = withdrawal.complete_due_withdrawals()
            record_handled(completed)
        with run_as_job(withdrawal.DELIVER_OPERATION):
            notices = withdrawal.deliver_due_withdrawal_notices()
            record_handled(notices.handled)
        return report, eligibility, WithdrawalRound(completed=completed, notices=notices)

    def _deliver_safely(self) -> tuple[DeliveryReport, payment_eligibility.DeliveryReport, WithdrawalRound]:
        """
        두 일의 한 묶음씩을 처리한다. DB 에 잠깐 접속할 수 없어도 워커가 죽지 않게 한다.

        오래 도는 프로세스는 끊긴 DB 연결을 쥐고 있을 수 있다.
        매번 확인해서 끊긴 연결은 버리고 새로 맺게 한다.
        """
        close_old_connections()
        try:
            result = self._deliver_round()
        except OperationalError as exc:
            # 오류의 종류만 적는다. 오류의 글에는 DB 의 주소와 계정 이름이 들어 있다. 자세한 것은 로그에 남았다
            self.stderr.write(f'DB 에 접속하지 못했습니다. 잠시 뒤 다시 시도합니다: {type(exc).__name__}')
            return DeliveryReport(), payment_eligibility.DeliveryReport(), WithdrawalRound()
        # DB 에 닿아 한 바퀴를 끝냈다. 닿지 못한 바퀴는 심장박동을 바꾸지 않는다(observability/heartbeat.py)
        beat(settings.HEARTBEAT_FILE)
        return result

    def _report(self, report: DeliveryReport) -> None:
        """한 일이 있을 때만 출력한다. 몇 초마다 "0건" 을 찍지 않는다."""
        if report.handled == 0:
            return
        self.stdout.write(f'지급 {report.granted}건, 주지 않음 {report.skipped}건, 다시 시도 예정 {report.retried}건')

    def _report_eligibility(self, report: payment_eligibility.DeliveryReport) -> None:
        """결제 자격의 한 일. 한 일이 있을 때만 출력한다."""
        if report.handled == 0:
            return
        self.stdout.write(f'결제 자격 알림 {report.sent}건, 다시 시도 예정 {report.retried}건')

    def _report_withdrawals(self, result: WithdrawalRound) -> None:
        """탈퇴의 한 일. 한 일이 있을 때만 출력한다."""
        if result.completed + result.notices.handled == 0:
            return
        self.stdout.write(
            f'탈퇴를 마친 계정 {result.completed}건, 탈퇴 알림 {result.notices.sent}건, '
            f'다시 시도 예정 {result.notices.retried}건'
        )
