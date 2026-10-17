# auth-server/accounts/payment_eligibility.py

"""
결제 자격을 결제 서버에 알린다(#336, 결제 서버의 #337).

결제 서버는 결제할 때 이 서버를 부르지 않는다. 그래서 이 서버가 미리 알려 둔다. 알리는 것은 지금의 상태 둘이다.
  - 성년이 되는 날(legal_adult_from). 비어 있으면 이미 성년이다. 그날이 지나면 결제 서버가 스스로 성년으로 본다
  - 보호자 동의가 있는가(guardian_consent)
본인인증을 하지 않은 사용자는 알리지 않는다. 결제 서버는 모르는 사용자를 "본인인증 전"으로 본다.

일이 둘로 나뉜다. 환영 크레딧과 같다(welcome_credit.py).
  적는 쪽(mark_changed)은 본인인증, 동의, 철회와 같은 트랜잭션에서 버전 하나를 올린다
  보내는 쪽(deliver_due_eligibility)은 워커가 부른다. 그때의 상태를 버전과 함께 보낸다

보내는 동안 줄을 잠가 두지 않는다. 짧은 트랜잭션에서 줄을 차지하고(다음 시도 시각을 임대가 끝나는 때로 민다),
트랜잭션 밖에서 결제 서버를 부르고, 다시 짧게 결과를 적는다. 잠근 채로 기다리면 그동안 그 사용자의 동의와 철회가 멈춘다.
보내는 사이에 상태가 또 바뀌면 버전이 올라 있어 다음 바퀴에 다시 나간다.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from django.db import transaction
from django.db.models import F, Q
from django.db.models.functions import Greatest
from django.utils import timezone

from accounts.backoff import retry_delay
from accounts.billing_client import BillingUnavailableError, report_payment_eligibility
from accounts.models import (
    GuardianConsent,
    GuardianConsentStatus,
    IdentityVerification,
    PaymentEligibility,
    User,
)

logger = logging.getLogger(__name__)

# 한 묶음을 처리하는 일의 이름. 로그의 operation 칸에 들어간다(docs/observability.md)
DELIVER_OPERATION = 'payment_eligibility.deliver'
# 결제 서버에 알리지 못했을 때의 오류 코드
BILLING_UNAVAILABLE_ERROR_CODE = 'billing.unavailable'

# 실패한 뒤 다시 보내기까지의 간격. 환영 크레딧과 같다
FIRST_RETRY_DELAY = timedelta(seconds=5)
MAX_RETRY_DELAY = timedelta(hours=1)
# 워커가 줄을 차지한 뒤 결제 서버의 답을 기다리는 동안. 워커가 그 사이에 죽으면 이 시간 뒤에 다른 워커가 다시 보낸다.
# 결제 서버를 기다리는 시간(billing_client.TIMEOUT_SECONDS)보다 넉넉해야 한다
LEASE = timedelta(seconds=30)

DEFAULT_BATCH_SIZE = 20


@dataclass(frozen=True)
class EligibilitySnapshot:
    """결제 서버에 보내는 한 사용자의 결제 자격."""

    user_public_id: UUID
    version: int
    # 성년이 되는 날. None 이면 이미 성년이다
    legal_adult_from: date | None
    guardian_consent: bool


@dataclass(frozen=True)
class DeliveryReport:
    """워커가 한 번 돌면서 한 일."""

    sent: int = 0
    retried: int = 0

    @property
    def handled(self) -> int:
        return self.sent + self.retried


def mark_changed(user: User) -> None:
    """
    결제 자격이 바뀌었다고 적는다. 부르는 쪽의 트랜잭션 안에서 돈다.

    줄이 없으면 만든다. 있으면 버전을 올리고 바로 보낼 수 있게 한다. 실패를 쌓던 줄도 처음부터 다시 센다.
    """
    now = timezone.now()
    row, created = PaymentEligibility.objects.get_or_create(user=user, defaults={'version': 1, 'next_attempt_at': now})
    if created:
        return
    PaymentEligibility.objects.filter(pk=row.pk).update(version=F('version') + 1, next_attempt_at=now, attempts=0)


def deliver_due_eligibility(*, batch_size: int = DEFAULT_BATCH_SIZE) -> DeliveryReport:
    """지금 보낼 수 있는 줄을 최대 batch_size 개 처리하고, 한 일을 돌려준다."""
    counts = {'sent': 0, 'retried': 0}
    for _ in range(batch_size):
        outcome = _deliver_next()
        if outcome is None:
            break
        counts[outcome] += 1
    return DeliveryReport(**counts)


def _deliver_next() -> str | None:
    """보낼 차례가 된 줄 하나를 처리한다. 없으면 None 을 돌려준다."""
    now = timezone.now()
    claim = _claim_next(now)
    if claim is None:
        return None
    row_id, snapshot = claim
    try:
        report_payment_eligibility(
            user_public_id=snapshot.user_public_id,
            version=snapshot.version,
            legal_adult_from=snapshot.legal_adult_from,
            guardian_consent=snapshot.guardian_consent,
        )
    except BillingUnavailableError as exc:
        _schedule_retry(row_id, exc, now)
        return 'retried'
    _mark_delivered(row_id, snapshot.version, now)
    return 'sent'


@transaction.atomic
def _claim_next(now) -> tuple[int, EligibilitySnapshot] | None:
    """
    보낼 차례가 된 줄 하나를 차지하고, 그때의 상태를 읽는다.

    skip_locked 로 다른 워커가 차지하는 중인 줄을 건너뛴다. 차지하면 다음 시도 시각을 임대가 끝나는 때로 민다.
    상태는 같은 트랜잭션에서 읽는다. 버전과 상태가 같은 때의 것이다(바꾸는 쪽도 한 트랜잭션에서 둘을 바꾼다).
    """
    row = (
        PaymentEligibility.objects.select_for_update(skip_locked=True)
        .select_related('user')
        .filter(Q(version__gt=F('delivered_version')), next_attempt_at__lte=now)
        .order_by('next_attempt_at', 'id')
        .first()
    )
    if row is None:
        return None
    row.next_attempt_at = now + LEASE
    row.save(update_fields=['next_attempt_at'])
    return row.pk, snapshot_of(row)


def snapshot_of(row: PaymentEligibility) -> EligibilitySnapshot:
    """그 줄의 사용자가 지금 가진 결제 자격."""
    verification = IdentityVerification.objects.filter(user_id=row.user_id).first()
    return EligibilitySnapshot(
        user_public_id=row.user.public_id,
        version=row.version,
        legal_adult_from=verification.legal_adult_from if verification else None,
        guardian_consent=_has_guardian_consent(row.user_id),
    )


def _has_guardian_consent(user_id: int) -> bool:
    """그 사용자에게 지금 보호자의 동의가 있는가."""
    return GuardianConsent.objects.filter(minor_id=user_id, status=GuardianConsentStatus.CONSENTED).exists()


def _mark_delivered(row_id: int, version: int, now) -> None:
    """
    그 버전까지 알렸다고 적는다. 그 사이에 버전이 올랐으면 바로 다시 보낼 수 있게 둔다.

    알린 버전은 줄어들지 않는다. 늦게 끝난 워커가 앞선 버전을 적어도 더 높은 기록을 지우지 않는다.
    """
    PaymentEligibility.objects.filter(pk=row_id).update(
        delivered_version=Greatest(F('delivered_version'), version),
        attempts=0,
        last_error='',
        next_attempt_at=now,
    )


def _schedule_retry(row_id: int, error: Exception, now) -> None:
    """실패를 적고 다음 시도 시각을 정한다. 버리지 않는다. 결제 서버가 살아나면 나간다."""
    with transaction.atomic():
        row = PaymentEligibility.objects.select_for_update().get(pk=row_id)
        row.attempts += 1
        row.next_attempt_at = now + retry_delay(row.attempts, first=FIRST_RETRY_DELAY, maximum=MAX_RETRY_DELAY)
        row.last_error = str(error)[: PaymentEligibility._meta.get_field('last_error').max_length]
        row.save(update_fields=['attempts', 'next_attempt_at', 'last_error'])
    # 사용자는 적지 않는다. 관리자 화면에서 번호로 찾는다
    logger.warning(
        '결제 자격을 결제 서버에 알리지 못했다. 나중에 다시 시도한다',
        extra={
            'operation': DELIVER_OPERATION,
            'error_code': BILLING_UNAVAILABLE_ERROR_CODE,
            'error_message': row.last_error,
            'payment_eligibility_id': row.pk,
            'attempt': row.attempts,
        },
    )
