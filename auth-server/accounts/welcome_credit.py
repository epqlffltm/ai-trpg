# auth-server/accounts/welcome_credit.py

"""
환영 크레딧. 가입을 마친 사용자에게 결제 서버가 무료 크레딧을 주게 한다.

일이 둘로 나뉜다.

적는 쪽(request_welcome_credit)은 가입 인증을 처리하는 중에 불린다. DB 에 한 줄을 쓰고 끝난다.
맡기는 쪽(deliver_due_welcome_credits)은 워커가 부른다. 결제 서버와 통신하고, 실패하면 다시 시도한다.

적는 일이 "이메일 인증됨" 으로 바꾸는 일과 같은 트랜잭션에 들어간다. 그래서
"인증은 됐는데 크레딧을 줄 일은 적히지 않은" 상태가 생기지 않는다.

한 사람이 여러 번 받는 것은 메일함의 열쇠(mailbox_key)로 막는다. 가입 자체는 막지 않는다.
받는 것만 메일함마다 한 번이다.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from accounts.billing_client import GRANTED, BillingUnavailableError, grant_welcome_credit
from accounts.models import User, WelcomeCredit, WelcomeCreditStatus

logger = logging.getLogger(__name__)

# 한 묶음을 처리하는 일의 이름. 로그의 operation 칸에 들어간다(docs/observability.md)
DELIVER_OPERATION = 'welcome_credit.deliver'
# 결제 서버에 맡기지 못했을 때의 오류 코드
BILLING_UNAVAILABLE_ERROR_CODE = 'billing.unavailable'

# 메일함의 열쇠를 만들 때 SECRET_KEY 에 섞는 값.
# 같은 SECRET_KEY 에서 나온 다른 용도의 값(인증 코드 해시, 발송함의 암호화 키)과 겹치지 않게 한다
KEY_SALT = 'accounts.welcome_credit.mailbox'

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


def mailbox_of(email: str) -> str:
    """
    메일 주소를 "같은 메일함이면 같은 글자"가 되게 정리한다.

    대소문자를 가리지 않고, 사용자 이름의 + 뒤를 뗀다. A+trpg@Example.com 과 a@example.com 은 같은 메일함이다.
    + 뒤는 대부분의 메일 서비스가 무시하는 꼬리표라, 주소 하나로 계정을 얼마든지 만들 수 있다.

    Gmail 이 무시하는 점(a.b@gmail.com)이나 서비스마다 다른 별칭은 정리하지 않는다.
    그것까지 따라가면 서비스별 규칙을 이 코드가 알아야 하고, 틀리면 남의 메일함과 같다고 본다.
    """
    local, _, domain = email.strip().lower().rpartition('@')
    return f'{local.split("+", 1)[0]}@{domain}'


def mailbox_key(email: str) -> str:
    """
    메일함의 열쇠. 정리한 주소를 서버의 비밀키로 서명한 값이다(HMAC-SHA256, 16진수 64자).

    그냥 해시가 아니라 비밀키를 섞는다. 메일 주소는 짐작할 수 있는 값이라, 해시만으로는
    DB 를 읽은 사람이 주소를 하나씩 넣어 보며 누가 가입했었는지 알아낼 수 있다.
    SECRET_KEY 를 바꾸면 열쇠가 모두 달라진다. 그 전에 받은 메일함이 다시 받을 수 있게 된다.
    """
    return salted_hmac(KEY_SALT, mailbox_of(email), algorithm='sha256').hexdigest()


def request_welcome_credit(user: User) -> bool:
    """
    이 사용자에게 환영 크레딧을 주라고 적어 둔다. 실제로 맡기는 것은 워커다.

    그 메일함으로 이미 적힌 줄이 있으면 아무것도 하지 않는다. 새로 적었으면 True 를 돌려준다.
    부르는 쪽의 트랜잭션 안에서 돈다. 그 트랜잭션이 취소되면 이 줄도 함께 사라진다.
    """
    _, created = WelcomeCredit.objects.get_or_create(
        mailbox_key=mailbox_key(user.email),
        defaults={'user_public_id': user.public_id, 'next_attempt_at': timezone.now()},
    )
    return created


def request_welcome_credits_for_verified_users() -> int:
    """
    이미 가입을 마친 계정들에 환영 크레딧을 주라고 적어 둔다. 새로 적은 줄의 수를 돌려준다.

    이 기능이 생기기 전에 가입한 계정을 위한 것이다. 여러 번 돌려도 줄이 늘지 않는다.
    먼저 인증한 계정부터 본다. 같은 메일함의 계정이 둘이면 먼저 인증한 쪽이 받는다.
    """
    verified_users = User.objects.filter(email_verified_at__isnull=False).order_by('email_verified_at', 'id')
    return sum(1 for user in verified_users.iterator() if request_welcome_credit(user))


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
        WelcomeCredit.objects
        .select_for_update(skip_locked=True)
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
    claim.last_error = str(error)[:WelcomeCredit._meta.get_field('last_error').max_length]
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
    return min(FIRST_RETRY_DELAY * (2 ** doublings), MAX_RETRY_DELAY)
