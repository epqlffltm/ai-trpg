# auth-server/support/inquiries.py

"""
문의를 받고, 목록을 읽고, 운영자가 답한다. 주소와 응답의 모양은 views.py 가 정한다.

  - 받기: 로그인했으면 계정의 주소로 답한다. 로그인하지 않았으면 적은 주소로 답한다.
  - 목록: 최근 것부터 PAGE_SIZE 개씩. 다음 쪽은 마지막 줄의 보낸 시각보다 앞의 것이다(before).
  - 답: 한 번만 쓴다. 답을 적는 일과 메일을 맡기는 일은 한 트랜잭션이다(답은 적혔는데 메일이 없는 일이 없다).
    같은 문의에 두 운영자가 함께 답하면 줄을 잠근 쪽만 적고 다른 쪽은 이미 답했다는 거절을 받는다.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from accounts.models import MailKind, MailReceipt, User
from accounts.outbox import enqueue_mail
from support.mail import REPLY_DEADLINE, REPLY_RECEIPT_PURPOSE, build_reply_message
from support.models import Inquiry, InquiryStatus

# 목록 한 쪽의 줄 수
PAGE_SIZE = 20


class InquiryNotFoundError(Exception):
    """그런 문의가 없다."""


class InquiryAlreadyAnsweredError(Exception):
    """이미 답한 문의다. 답은 한 번만 쓴다."""


@dataclass(frozen=True)
class Page:
    """목록 한 쪽. next_before 가 None 이면 마지막 쪽이다."""

    items: list[Inquiry]
    next_before: datetime | None


def submit_inquiry(*, user: User | None, category: str, title: str, body: str, email: str | None) -> Inquiry:
    """문의를 받는다. 로그인했으면 적은 주소 대신 계정의 주소로 답한다."""
    reply_to = user.email if user is not None else email
    if not reply_to:
        raise ValueError('답 받을 주소가 없다')
    return Inquiry.objects.create(user=user, category=category, title=title, body=body, email=reply_to)


def my_inquiries(user: User, *, before: datetime | None) -> Page:
    """그 사람의 문의. 최근 것부터."""
    return _page(Inquiry.objects.filter(user=user), before)


def operator_inquiries(*, status: str | None, before: datetime | None) -> Page:
    """운영자가 보는 문의. 상태를 고르면 그 상태만. 최근 것부터. 보낸 계정을 함께 읽는다."""
    found = Inquiry.objects.select_related('user', 'reply_receipt')
    if status:
        found = found.filter(status=status)
    return _page(found, before)


def reply_to_inquiry(*, inquiry_id: uuid.UUID, operator: User, reply: str) -> Inquiry:
    """
    운영자가 답을 적고 그 답을 메일로 맡긴다.
    없으면 InquiryNotFoundError, 이미 답했으면 InquiryAlreadyAnsweredError.
    """
    with transaction.atomic():
        inquiry = Inquiry.objects.select_for_update().filter(pk=inquiry_id).first()
        if inquiry is None:
            raise InquiryNotFoundError
        if inquiry.status == InquiryStatus.ANSWERED:
            raise InquiryAlreadyAnsweredError
        receipt = MailReceipt.objects.create(purpose=REPLY_RECEIPT_PURPOSE)
        inquiry.status = InquiryStatus.ANSWERED
        inquiry.reply = reply
        inquiry.answered_at = timezone.now()
        inquiry.answered_by = operator
        inquiry.reply_receipt = receipt
        inquiry.save(update_fields=['status', 'reply', 'answered_at', 'answered_by', 'reply_receipt'])
        subject, body = build_reply_message(inquiry)
        enqueue_mail(
            to_email=inquiry.email,
            subject=subject,
            body=body,
            receipt=receipt,
            deadline=REPLY_DEADLINE,
            kind=MailKind.INQUIRY_REPLY,
        )
    # inline 발송이면 맡길 때 기록에 보낸 시각이 적혔다. 응답에 싣도록 다시 읽는다
    receipt.refresh_from_db()
    return inquiry


def erase_inquiries(user: User) -> None:
    """그 사람의 문의를 지운다. 계정을 비울 때(탈퇴, 만 14세 미만) 부른다."""
    Inquiry.objects.filter(user=user).delete()


def _page(found, before: datetime | None) -> Page:
    """최근 것부터 한 쪽. 한 줄 더 읽어 다음 쪽이 있는지 본다."""
    if before is not None:
        found = found.filter(created_at__lt=before)
    rows = list(found.order_by('-created_at')[: PAGE_SIZE + 1])
    items = rows[:PAGE_SIZE]
    next_before = items[-1].created_at if len(rows) > PAGE_SIZE else None
    return Page(items=items, next_before=next_before)
