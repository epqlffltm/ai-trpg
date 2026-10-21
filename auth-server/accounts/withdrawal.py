# auth-server/accounts/withdrawal.py

"""
탈퇴(#603, docs/architecture/withdrawal.md).
요청하고, 유예 동안 취소하고, 유예가 지나면 계정을 비우고 다른 서버에 알린다.

  1. 요청(request_withdrawal): 요청 시각을 적고 모든 세션을 끊는다. 메일로 알린다.
     비밀번호는 부르는 쪽이 먼저 확인한다(check_withdrawal_password)
  2. 유예(GRACE, 7일): 로그인은 되지만 토큰이 인증 서버에만 통한다(tokens.py). 그 안에 취소한다(cancel_withdrawal)
  3. 마치기(complete_due_withdrawals): 워커가 부른다. 계정을 비우고(erasure.py) 서버마다 알릴 줄을 적는다
  4. 알리기(deliver_due_withdrawal_notices): 워커가 부른다. 서명해 보내고 2xx 까지 다시 보낸다

알리는 일의 모양은 결제 자격을 알리는 것(payment_eligibility.py)과 같다. 짧은 트랜잭션에서 줄을 차지하고,
트랜잭션 밖에서 상대를 부르고, 다시 짧게 결과를 적는다. 잠근 채로 상대를 기다리지 않는다.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from accounts.backoff import retry_delay
from accounts.billing_client import BillingUnavailableError, report_withdrawal
from accounts.consents import erase_consents
from accounts.erasure import blank_account, erase_identity_records, erase_mail_records
from accounts.mail import send_withdrawal_completed_notice, send_withdrawal_requested_notice
from accounts.models import SecurityEventKind, User, WithdrawalNotice, WithdrawalTarget
from accounts.security_events import record_security_event
from accounts.tokens import revoke_all_sessions
from accounts.withdrawal_schedule import GRACE, withdrawal_scheduled_at

logger = logging.getLogger(__name__)

# 한 묶음을 처리하는 일의 이름. 로그의 operation 칸에 들어간다(docs/observability.md)
COMPLETE_OPERATION = 'withdrawal.complete'
DELIVER_OPERATION = 'withdrawal.deliver'
# 다른 서버에 알리지 못했을 때의 오류 코드
UNDELIVERED_ERROR_CODE = 'withdrawal.undelivered'

# 실패한 뒤 다시 보내기까지의 간격. 결제 서버에 맡기는 다른 일과 같다
FIRST_RETRY_DELAY = timedelta(seconds=5)
MAX_RETRY_DELAY = timedelta(hours=1)
# 워커가 줄을 차지한 뒤 상대의 답을 기다리는 동안. 상대를 기다리는 시간(5초)보다 넉넉해야 한다
LEASE = timedelta(seconds=30)

DEFAULT_BATCH_SIZE = 20


class WrongWithdrawalPasswordError(Exception):
    """탈퇴를 요청하며 적은 비밀번호가 틀렸다."""


@dataclass(frozen=True)
class NoticeClaim:
    """워커가 차지한 알림 하나. 보낼 때 필요한 것만 담는다."""

    notice_id: int
    target: str
    user_public_id: UUID
    withdrawn_at: datetime


@dataclass(frozen=True)
class DeliveryReport:
    """워커가 한 번 돌면서 알린 일."""

    sent: int = 0
    retried: int = 0

    @property
    def handled(self) -> int:
        return self.sent + self.retried


# 서버마다 알리는 함수와, 그 함수가 "나중에 다시 하면 된다"로 내는 오류. 서버를 더하면 여기에 더한다
SENDERS: dict[str, Callable[..., str]] = {WithdrawalTarget.BILLING: report_withdrawal}
RETRYABLE_ERRORS: tuple[type[Exception], ...] = (BillingUnavailableError,)


def check_withdrawal_password(user: User, password: str) -> None:
    """탈퇴를 요청하며 적은 비밀번호를 확인한다. 틀리면 WrongWithdrawalPasswordError."""
    if not user.check_password(password):
        raise WrongWithdrawalPasswordError


@transaction.atomic
def request_withdrawal(user: User) -> datetime:
    """
    탈퇴를 요청한다. 계정을 비울 시각을 돌려준다.

    요청 시각을 적고, 모든 세션을 끊고(이 요청의 토큰도), 메일과 보안 이벤트를 남긴다.
    이미 요청한 계정이면 아무것도 바꾸지 않고 그때 정한 시각을 돌려준다. 다시 눌러도 유예가 늘지 않는다.
    """
    locked = _lock(user)
    scheduled = withdrawal_scheduled_at(locked)
    if scheduled is not None:
        return scheduled
    locked.withdrawal_requested_at = timezone.now()
    locked.save(update_fields=['withdrawal_requested_at'])
    revoke_all_sessions(locked)
    scheduled = withdrawal_scheduled_at(locked)
    send_withdrawal_requested_notice(user=locked, scheduled_at=scheduled)
    record_security_event(kind=SecurityEventKind.WITHDRAWAL_REQUESTED, user=locked)
    return scheduled


@transaction.atomic
def cancel_withdrawal(user: User) -> None:
    """
    유예 중인 탈퇴를 취소한다. 요청하지 않은 계정이면 아무것도 하지 않는다.

    취소한 뒤의 토큰 갱신(/refresh)부터 모든 서버에 통한다.
    """
    locked = _lock(user)
    if withdrawal_scheduled_at(locked) is None:
        return
    locked.withdrawal_requested_at = None
    locked.save(update_fields=['withdrawal_requested_at'])


def complete_due_withdrawals(*, batch_size: int = DEFAULT_BATCH_SIZE) -> int:
    """유예가 지난 계정을 최대 batch_size 개 비우고, 비운 수를 돌려준다. 계정마다 트랜잭션 하나다."""
    now = timezone.now()
    due_ids = list(
        User.objects.filter(withdrawal_requested_at__lte=now - GRACE, withdrawn_at__isnull=True)
        .order_by('withdrawal_requested_at', 'pk')
        .values_list('pk', flat=True)[:batch_size]
    )
    return sum(1 for user_id in due_ids if complete_withdrawal(user_id, now))


@transaction.atomic
def complete_withdrawal(user_id: int, now: datetime) -> bool:
    """
    그 계정의 탈퇴를 마친다. 마쳤으면 True, 그사이 취소했거나 이미 마쳤으면 False 다.

    계정을 비우고(erasure.py), 동의 기록을 지우고, 서버마다 알릴 줄을 적고, 지우기 전의 주소로 메일을 보낸다.
    모두 한 트랜잭션이다. 줄을 잠근 뒤 다시 확인하므로 취소와 엇갈려도 둘 중 하나만 된다.
    """
    locked = User.objects.select_for_update().get(pk=user_id)
    scheduled = withdrawal_scheduled_at(locked)
    if scheduled is None or scheduled > now:
        return False
    email = locked.email
    blank_account(locked)
    revoke_all_sessions(locked)
    erase_mail_records(locked, email)
    erase_identity_records(locked)
    erase_consents(locked)
    locked.withdrawn_at = now
    locked.save(update_fields=['withdrawn_at'])
    _queue_notices(locked, now)
    send_withdrawal_completed_notice(email=email)
    record_security_event(kind=SecurityEventKind.ACCOUNT_WITHDRAWN, user=locked)
    return True


def _queue_notices(user: User, withdrawn_at: datetime) -> None:
    """알릴 서버마다 한 줄을 적는다. 바로 보낼 수 있게 한다."""
    WithdrawalNotice.objects.bulk_create(
        WithdrawalNotice(user=user, target=target, withdrawn_at=withdrawn_at, next_attempt_at=withdrawn_at)
        for target in SENDERS
    )


def _lock(user: User) -> User:
    """계정의 줄을 잠그고 지금 값으로 다시 읽는다."""
    return User.objects.select_for_update().get(pk=user.pk)


def deliver_due_withdrawal_notices(*, batch_size: int = DEFAULT_BATCH_SIZE) -> DeliveryReport:
    """지금 보낼 수 있는 알림을 최대 batch_size 개 처리하고, 한 일을 돌려준다."""
    counts = {'sent': 0, 'retried': 0}
    for _ in range(batch_size):
        outcome = _deliver_next()
        if outcome is None:
            break
        counts[outcome] += 1
    return DeliveryReport(**counts)


def _deliver_next() -> str | None:
    """보낼 차례가 된 알림 하나를 처리한다. 없으면 None 을 돌려준다."""
    now = timezone.now()
    claim = _claim_next(now)
    if claim is None:
        return None
    try:
        SENDERS[claim.target](user_public_id=claim.user_public_id, withdrawn_at=claim.withdrawn_at)
    except RETRYABLE_ERRORS as exc:
        _schedule_retry(claim.notice_id, exc, now)
        return 'retried'
    WithdrawalNotice.objects.filter(pk=claim.notice_id).update(delivered_at=now, attempts=0, last_error='')
    return 'sent'


@transaction.atomic
def _claim_next(now: datetime) -> NoticeClaim | None:
    """
    보낼 차례가 된 알림 하나를 차지한다. 다른 워커가 차지하는 중인 줄은 건너뛴다.

    차지하면 다음 시도 시각을 임대가 끝나는 때로 민다. 워커가 보내다 죽으면 그 뒤에 다른 워커가 다시 보낸다.
    """
    notice = (
        WithdrawalNotice.objects.select_for_update(skip_locked=True)
        .select_related('user')
        .filter(delivered_at__isnull=True, next_attempt_at__lte=now)
        .order_by('next_attempt_at', 'id')
        .first()
    )
    if notice is None:
        return None
    notice.next_attempt_at = now + LEASE
    notice.save(update_fields=['next_attempt_at'])
    return NoticeClaim(notice.pk, notice.target, notice.user.public_id, notice.withdrawn_at)


def _schedule_retry(notice_id: int, error: Exception, now: datetime) -> None:
    """실패를 적고 다음 시도 시각을 정한다. 버리지 않는다. 상대가 살아나면 나간다."""
    with transaction.atomic():
        notice = WithdrawalNotice.objects.select_for_update().get(pk=notice_id)
        notice.attempts += 1
        notice.next_attempt_at = now + retry_delay(notice.attempts, first=FIRST_RETRY_DELAY, maximum=MAX_RETRY_DELAY)
        notice.last_error = str(error)[: WithdrawalNotice._meta.get_field('last_error').max_length]
        notice.save(update_fields=['attempts', 'next_attempt_at', 'last_error'])
    # 사용자는 적지 않는다. 관리자 화면에서 번호로 찾는다
    logger.warning(
        '탈퇴를 다른 서버에 알리지 못했다. 나중에 다시 시도한다',
        extra={
            'operation': DELIVER_OPERATION,
            'error_code': UNDELIVERED_ERROR_CODE,
            'error_message': notice.last_error,
            'withdrawal_notice_id': notice.pk,
            'target': notice.target,
            'attempt': notice.attempts,
        },
    )
