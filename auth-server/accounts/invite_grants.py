# auth-server/accounts/invite_grants.py

"""
초대 보상을 결제 서버에 맡긴다(#990). 워커(manage.py send_welcome_credits)가 부른다.

환영 크레딧(welcome_credit.py)과 같은 방식이다. 맡길 차례가 된 줄을 하나씩 잠그고, 결제 서버를 부르고, 결과를 적는다.
실패하면 간격을 두 배씩 늘려(5초, 10초, ... 1시간까지) 다시 맡긴다. 버리지 않는다.
워커가 부른 뒤 결과를 적기 전에 죽으면 그 줄은 다시 나간다. 결제 서버가 "이미 받았다"고 답한다.
"""

import logging

from django.db import transaction
from django.utils import timezone

from accounts.backoff import retry_delay
from accounts.billing_client import GRANTED, BillingUnavailableError, grant_invite_credit
from accounts.models import InviteGrant, WelcomeCreditStatus
from accounts.welcome_credit import (
    BILLING_UNAVAILABLE_ERROR_CODE,
    DEFAULT_BATCH_SIZE,
    FIRST_RETRY_DELAY,
    MAX_RETRY_DELAY,
    DeliveryReport,
)

logger = logging.getLogger(__name__)

# 한 묶음을 처리하는 일의 이름. 로그의 operation 칸에 들어간다(docs/observability.md)
DELIVER_OPERATION = 'invite_grant.deliver'


def deliver_due_invite_grants(*, batch_size: int = DEFAULT_BATCH_SIZE) -> DeliveryReport:
    """지금 맡길 수 있는 줄을 최대 batch_size 개 처리하고, 한 일을 돌려준다."""
    counts = {'granted': 0, 'skipped': 0, 'retried': 0}
    for _ in range(batch_size):
        outcome = _deliver_next()
        if outcome is None:
            break
        counts[outcome] += 1
    return DeliveryReport(**counts)


def _deliver_next() -> str | None:
    """맡길 차례가 된 줄 하나를 처리한다. 처리할 줄이 없으면 None 이다. 줄 하나가 트랜잭션 하나다."""
    now = timezone.now()
    with transaction.atomic():
        claim = _lock_next_due(now)
        if claim is None:
            return None
        try:
            outcome = grant_invite_credit(
                user_public_id=claim.user_public_id, reward_id=claim.reward_id, role=claim.role
            )
        except BillingUnavailableError as exc:
            _schedule_retry(claim, exc, now)
            return 'retried'
        _finish(claim, outcome, now)
        return 'granted' if outcome == GRANTED else 'skipped'


def _lock_next_due(now) -> InviteGrant | None:
    """맡길 차례가 된 줄 하나를 잠그고 가져온다. 다른 워커가 잠근 줄은 건너뛴다."""
    return (
        InviteGrant.objects.select_for_update(skip_locked=True)
        .filter(status=WelcomeCreditStatus.PENDING, next_attempt_at__lte=now)
        .order_by('next_attempt_at', 'id')
        .first()
    )


def _finish(claim: InviteGrant, outcome: str, now) -> None:
    """맡길 일이 끝났다고 적는다. outcome 은 결제 서버가 돌려준 결과이고, 그대로 상태가 된다."""
    claim.status = outcome
    claim.finished_at = now
    claim.last_error = ''
    claim.save(update_fields=['status', 'finished_at', 'last_error'])


def _schedule_retry(claim: InviteGrant, error: Exception, now) -> None:
    """실패를 기록하고 다음 시도 시각을 정한다. 간격은 두 배씩 늘고 MAX_RETRY_DELAY 에서 멈춘다."""
    claim.attempts += 1
    claim.next_attempt_at = now + retry_delay(claim.attempts, first=FIRST_RETRY_DELAY, maximum=MAX_RETRY_DELAY)
    claim.last_error = str(error)[: InviteGrant._meta.get_field('last_error').max_length]
    claim.save(update_fields=['attempts', 'next_attempt_at', 'last_error'])
    logger.warning(
        '초대 보상을 결제 서버에 맡기지 못했다. 나중에 다시 시도한다',
        extra={
            'operation': DELIVER_OPERATION,
            'error_code': BILLING_UNAVAILABLE_ERROR_CODE,
            'error_message': claim.last_error,
            'invite_grant_id': claim.pk,
            'attempt': claim.attempts,
        },
    )
