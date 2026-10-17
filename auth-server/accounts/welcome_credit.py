# auth-server/accounts/welcome_credit.py

"""
환영 크레딧. 본인인증을 마친 사용자에게 결제 서버가 무료 크레딧(실버)을 주게 한다(#336).

일이 둘로 나뉜다.

적는 쪽(request_welcome_credit)은 본인인증을 처리하는 중에 불린다. DB 에 한 줄을 쓰고 끝난다.
맡기는 쪽(deliver_due_welcome_credits)은 워커가 부른다. 결제 서버와 통신하고, 실패하면 다시 시도한다.

적는 일이 본인인증의 기록과 같은 트랜잭션에 들어간다(identity.py). 그래서
"인증은 됐는데 크레딧을 줄 일은 적히지 않은" 상태가 생기지 않는다.

한 사람이 여러 번 받는 것은 받는 사람의 열쇠(recipient_key, 본인인증의 사람 열쇠)로 막는다.
#336 전에는 이메일 인증 때 메일함의 열쇠로 적었다. 그때 받은 계정은 본인인증을 해도 다시 받지 않는다.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from accounts.billing_client import GRANTED, BillingUnavailableError, grant_welcome_credit
from accounts.models import WelcomeCredit, WelcomeCreditStatus

logger = logging.getLogger(__name__)

# 한 묶음을 처리하는 일의 이름. 로그의 operation 칸에 들어간다(docs/observability.md)
DELIVER_OPERATION = 'welcome_credit.deliver'
# 결제 서버에 맡기지 못했을 때의 오류 코드
BILLING_UNAVAILABLE_ERROR_CODE = 'billing.unavailable'

# 실패한 뒤 다시 시도하기까지의 간격. 실패할 때마다 두 배가 된다(5초, 10초, 20초, ...).
# 결제 서버가 죽어 있을 때 쉬지 않고 두드리지 않기 위해서다
FIRST_RETRY_DELAY = timedelta(seconds=5)
# 간격은 여기까지만 늘어난다. 메일과 달리 늦게 줘도 쓸모가 있어서 버리지 않고 계속 시도한다
MAX_RETRY_DELAY = timedelta(hours=1)
# 간격이 MAX_RETRY_DELAY 에 닿는 실패 횟수. 그 뒤로는 2 의 거듭제곱을 더 키우지 않는다
_DOUBLINGS_UNTIL_MAX = 10

# 워커가 한 번에 처리하는 최대 개수
DEFAULT_BATCH_SIZE = 20


@dataclass(frozen=True)
class DeliveryReport:
    """워커가 한 번 돌면서 한 일."""

    # 결제 서버가 이번에 크레딧을 줬다
    granted: int = 0
    # 결제 서버가 주지 않았다. 이미 받은 사용자이거나, 결제 서버가 환영 크레딧을 꺼 두었다. 맡길 일은 끝났다
    skipped: int = 0
    # 맡기지 못했다. 나중에 다시 시도한다
    retried: int = 0

    @property
    def handled(self) -> int:
        return self.granted + self.skipped + self.retried


def request_welcome_credit(*, user_public_id: UUID, recipient_key: str) -> bool:
    """
    이 사용자에게 환영 크레딧을 주라고 적어 둔다. 실제로 맡기는 것은 워커다. 새로 적었으면 True 를 돌려준다.

    두 경우에는 아무것도 하지 않는다.
      - 이 계정에 이미 적힌 줄이 있다. #336 전에 이메일 인증으로 받은 계정이다
      - 이 사람에게 이미 적힌 줄이 있다. 계정을 지우고 새 계정에서 다시 본인인증을 했다
    부르는 쪽의 트랜잭션 안에서 돈다. 그 트랜잭션이 취소되면 이 줄도 함께 사라진다.
    """
    if WelcomeCredit.objects.filter(user_public_id=user_public_id).exists():
        return False
    _, created = WelcomeCredit.objects.get_or_create(
        recipient_key=recipient_key,
        defaults={'user_public_id': user_public_id, 'next_attempt_at': timezone.now()},
    )
    return created


def deliver_due_welcome_credits(*, batch_size: int = DEFAULT_BATCH_SIZE) -> DeliveryReport:
    """지금 맡길 수 있는 줄을 최대 batch_size 개 처리하고, 한 일을 돌려준다."""
    counts = {'granted': 0, 'skipped': 0, 'retried': 0}
    for _ in range(batch_size):
        outcome = _deliver_next()
        if outcome is None:
            break
        counts[outcome] += 1
    return DeliveryReport(**counts)


def _deliver_next() -> str | None:
    """
    맡길 차례가 된 줄 하나를 처리한다. 처리할 줄이 없으면 None 을 돌려준다.

    줄 하나가 트랜잭션 하나다. 행을 잠근 채로 결제 서버를 부르고, 결과를 적고, 잠금을 푼다.
    부르는 도중 워커가 죽으면 트랜잭션이 취소되어 그 줄은 다시 대기 상태로 남는다.
    결제 서버가 이미 크레딧을 줬더라도 괜찮다. 다시 맡기면 "이미 받았다"는 답이 온다.
    """
    now = timezone.now()

    with transaction.atomic():
        claim = _lock_next_due(now)
        if claim is None:
            return None
        try:
            outcome = grant_welcome_credit(user_public_id=claim.user_public_id)
        except BillingUnavailableError as exc:
            _schedule_retry(claim, exc, now)
            return 'retried'
        _finish(claim, outcome, now)
        return 'granted' if outcome == GRANTED else 'skipped'


def _lock_next_due(now) -> WelcomeCredit | None:
    """
    맡길 차례가 된 줄 하나를 잠그고 가져온다.

    skip_locked 는 다른 워커가 잠근 행을 기다리지 않고 건너뛴다.
    워커를 여러 개 띄워도 같은 줄을 함께 맡기지 않고, 서로를 기다리지도 않는다.
    """
    return (
        WelcomeCredit.objects.select_for_update(skip_locked=True)
        .filter(status=WelcomeCreditStatus.PENDING, next_attempt_at__lte=now)
        .order_by('next_attempt_at', 'id')
        .first()
    )


def _finish(claim: WelcomeCredit, outcome: str, now) -> None:
    """맡길 일이 끝났다고 적는다. outcome 은 결제 서버가 돌려준 결과이고, 그대로 상태가 된다."""
    claim.status = outcome
    claim.finished_at = now
    claim.last_error = ''
    claim.save(update_fields=['status', 'finished_at', 'last_error'])


def _schedule_retry(claim: WelcomeCredit, error: Exception, now) -> None:
    """
    실패를 기록하고 다음 시도 시각을 정한다. 간격은 실패할 때마다 두 배가 되고 MAX_RETRY_DELAY 에서 멈춘다.

    버리지 않는다. 결제 서버가 하루를 죽어 있어도 살아나면 지급된다.
    """
    claim.attempts += 1
    claim.next_attempt_at = now + _retry_delay(claim.attempts)
    claim.last_error = str(error)[: WelcomeCredit._meta.get_field('last_error').max_length]
    claim.save(update_fields=['attempts', 'next_attempt_at', 'last_error'])
    # 받는 사람은 적지 않는다. 관리자 화면에서 번호로 찾는다
    logger.warning(
        '환영 크레딧을 결제 서버에 맡기지 못했다. 나중에 다시 시도한다',
        extra={
            'operation': DELIVER_OPERATION,
            'error_code': BILLING_UNAVAILABLE_ERROR_CODE,
            'error_message': claim.last_error,
            'welcome_credit_id': claim.pk,
            'attempt': claim.attempts,
        },
    )


def _retry_delay(attempts: int) -> timedelta:
    """attempts 번 실패한 뒤에 기다릴 시간."""
    doublings = min(attempts - 1, _DOUBLINGS_UNTIL_MAX)
    return min(FIRST_RETRY_DELAY * (2**doublings), MAX_RETRY_DELAY)
