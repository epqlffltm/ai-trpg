# auth-server/accounts/guardian_notices.py

"""
보호자에게 미성년자의 결제를 알린다(#352).
결제 서버가 미성년자의 결제와 청약철회를 보내 오면, 동의한 보호자의 메일로 알린다.

결제 서버는 보호자의 이메일을 모른다. 그래서 알릴 일만 보내고, 누구에게 보낼지는 이 서버가 정한다.
  - 동의한 보호자가 있으면 그 이메일로 메일을 적는다. 메일에 철회 링크를 붙인다
  - 없으면(그새 철회했다, 계정이 지워졌다) 적지 않고 "알릴 보호자가 없음"으로 남긴다
주문과 종류마다 한 번이다. 결제 서버가 답을 못 받고 다시 보내도 메일은 한 번만 간다.

법(게임산업법 12조의3 ①4)의 고지 의무는 중소기업이면 적용되지 않는다. 이것은 다툼에 대비한 안전장치다.
그래서 보냈다는 것을 남긴다(MailReceipt). 메일만 쓴다. 문자와 알림톡은 건당 돈이 든다.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.db import IntegrityError, transaction

from accounts.guardian_links import issue_revoke_token
from accounts.mail import send_guardian_payment_notice
from accounts.models import (
    GuardianConsent,
    GuardianConsentStatus,
    GuardianNotice,
    GuardianNoticeOutcome,
    MailReceipt,
    User,
)

# 기록의 용도(MailReceipt.purpose)
RECEIPT_PURPOSE = 'guardian_payment_notice'
# 결제 알림 메일을 버리기까지의 시간. 인증 코드와 달리 하루 늦어도 쓸모가 있다
NOTICE_MAIL_DEADLINE = timedelta(days=1)

# 결제 서버에 돌려주는 결과
QUEUED = GuardianNoticeOutcome.QUEUED.value
SKIPPED = GuardianNoticeOutcome.SKIPPED.value
# 이미 받은 알림이다. 처음 받았을 때의 결과는 바꾸지 않는다
DUPLICATE = 'duplicate'


@dataclass(frozen=True)
class PaymentNotice:
    """결제 서버가 보낸 알릴 일 하나."""

    order_id: UUID
    kind: str
    user_public_id: UUID
    product_id: str
    price: int
    credits: int
    occurred_at: datetime


@transaction.atomic
def record_payment_notice(notice: PaymentNotice) -> str:
    """
    알릴 일을 받아 적고, 보호자가 있으면 메일을 적는다. QUEUED, SKIPPED, DUPLICATE 중 하나를 돌려준다.

    줄을 먼저 적는다. 같은 알림이 함께 두 번 와도 유일 제약이 하나만 남기고, 메일도 하나만 적힌다.
    """
    minor = User.objects.filter(public_id=notice.user_public_id).first()
    consent = _active_consent(minor)
    receipt = MailReceipt.objects.create(purpose=RECEIPT_PURPOSE) if consent else None
    try:
        # 실패하면 이 안쪽만 되돌린다. 바깥에서 DUPLICATE 를 돌려줄 수 있어야 한다
        with transaction.atomic():
            _create_notice(notice, minor, receipt)
    except IntegrityError:
        if receipt is not None:
            receipt.delete()
        return DUPLICATE
    if consent is None:
        return SKIPPED
    send_guardian_payment_notice(
        minor=minor,
        guardian_email=consent.guardian_email,
        kind=notice.kind,
        product_id=notice.product_id,
        price=notice.price,
        credits=notice.credits,
        occurred_at=notice.occurred_at,
        revoke_token=issue_revoke_token(minor_public_id=minor.public_id, nonce=consent.link_nonce),
        receipt=receipt,
        deadline=NOTICE_MAIL_DEADLINE,
    )
    return QUEUED


def _active_consent(minor: User | None) -> GuardianConsent | None:
    """그 미성년자에게 지금 동의한 보호자가 있으면 그 동의다."""
    if minor is None:
        return None
    return GuardianConsent.objects.filter(minor=minor, status=GuardianConsentStatus.CONSENTED).first()


def _create_notice(notice: PaymentNotice, minor: User | None, receipt: MailReceipt | None) -> GuardianNotice:
    """받은 알림을 적는다. 같은 주문과 종류가 이미 있으면 IntegrityError 다."""
    return GuardianNotice.objects.create(
        order_id=notice.order_id,
        kind=notice.kind,
        minor=minor,
        minor_public_id=notice.user_public_id,
        product_id=notice.product_id,
        price=notice.price,
        credits=notice.credits,
        occurred_at=notice.occurred_at,
        outcome=QUEUED if receipt else SKIPPED,
        receipt=receipt,
    )
