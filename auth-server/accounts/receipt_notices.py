# auth-server/accounts/receipt_notices.py

"""
결제한 본인에게 결제와 청약철회를 메일로 알린다(#553).
결제 서버가 결제와 청약철회를 보내 오면, 그 계정의 이메일로 거래를 확인하는 메일을 적는다.

결제 영수증은 결제 대행사(토스페이먼츠)가 보낸다. 이 메일은 거기에 없는 것을 싣는다.
받은 골드, 청약철회의 기한과 하는 길(주문 내역 화면)이다. 거래 확인이라 끌 수 없다.

결제 서버는 사용자의 이메일을 모른다. 그래서 알릴 일만 보내고, 주소는 이 서버가 찾는다.
  - 계정이 있으면 그 이메일로 메일을 적는다
  - 없으면(지워졌다, 탈퇴를 마쳤다) 적지 않고 "알릴 계정이 없음"으로 남긴다
주문과 종류마다 한 번이다. 결제 서버가 답을 못 받고 다시 보내도 메일은 한 번만 간다.
미성년자의 결제는 보호자에게도 따로 간다(guardian_notices.py). 이 메일은 결제한 본인에게 간다.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.db import IntegrityError, transaction

from accounts.mail import send_payment_receipt, send_refund_receipt
from accounts.models import GuardianNoticeKind, MailReceipt, ReceiptNotice, ReceiptNoticeOutcome, User

# 기록의 용도(MailReceipt.purpose)
RECEIPT_PURPOSE = 'payment_receipt'
# 메일을 버리기까지의 시간. 인증 코드와 달리 하루 늦어도 쓸모가 있다
RECEIPT_MAIL_DEADLINE = timedelta(days=1)

# 결제 서버에 돌려주는 결과
QUEUED = ReceiptNoticeOutcome.QUEUED.value
SKIPPED = ReceiptNoticeOutcome.SKIPPED.value
# 이미 받은 알림이다. 처음 받았을 때의 결과는 바꾸지 않는다
DUPLICATE = 'duplicate'


@dataclass(frozen=True)
class OrderReceipt:
    """결제 서버가 보낸 알릴 일 하나."""

    order_id: UUID
    kind: str
    user_public_id: UUID
    product_id: str
    price: int
    credits: int
    paid_at: datetime
    occurred_at: datetime
    refundable_until: datetime


@transaction.atomic
def record_receipt_notice(notice: OrderReceipt) -> str:
    """
    알릴 일을 받아 적고, 계정이 있으면 메일을 적는다. QUEUED, SKIPPED, DUPLICATE 중 하나를 돌려준다.

    줄을 먼저 적는다. 같은 알림이 함께 두 번 와도 유일 제약이 하나만 남기고, 메일도 하나만 적힌다.
    """
    user = _reachable_user(notice.user_public_id)
    receipt = MailReceipt.objects.create(purpose=RECEIPT_PURPOSE) if user else None
    try:
        # 실패하면 이 안쪽만 되돌린다. 바깥에서 DUPLICATE 를 돌려줄 수 있어야 한다
        with transaction.atomic():
            _create_notice(notice, user, receipt)
    except IntegrityError:
        if receipt is not None:
            receipt.delete()
        return DUPLICATE
    if user is None:
        return SKIPPED
    _send(notice, user, receipt)
    return QUEUED


def _reachable_user(public_id: UUID) -> User | None:
    """메일을 받을 수 있는 계정이다. 없거나 탈퇴를 마쳤으면(주소를 지웠다) None 이다."""
    return User.objects.filter(public_id=public_id, withdrawn_at__isnull=True).first()


def _create_notice(notice: OrderReceipt, user: User | None, receipt: MailReceipt | None) -> ReceiptNotice:
    """받은 알림을 적는다. 같은 주문과 종류가 이미 있으면 IntegrityError 다."""
    return ReceiptNotice.objects.create(
        order_id=notice.order_id,
        kind=notice.kind,
        user=user,
        user_public_id=notice.user_public_id,
        product_id=notice.product_id,
        price=notice.price,
        credits=notice.credits,
        paid_at=notice.paid_at,
        occurred_at=notice.occurred_at,
        refundable_until=notice.refundable_until,
        outcome=QUEUED if receipt else SKIPPED,
        receipt=receipt,
    )


def _send(notice: OrderReceipt, user: User, receipt: MailReceipt) -> None:
    """종류에 맞는 메일을 적는다."""
    common = {
        'user': user,
        'order_id': str(notice.order_id),
        'product_id': notice.product_id,
        'price': notice.price,
        'credits': notice.credits,
        'paid_at': notice.paid_at,
        'receipt': receipt,
        'deadline': RECEIPT_MAIL_DEADLINE,
    }
    if notice.kind == GuardianNoticeKind.PAID:
        send_payment_receipt(**common, refundable_until=notice.refundable_until)
    else:
        send_refund_receipt(**common, refunded_at=notice.occurred_at)
