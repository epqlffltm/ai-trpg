# auth-server/support/inquiries.py

"""
문의를 받고, 목록을 읽고, 운영자가 답한다. 주소와 응답의 모양은 views.py 가 정한다.

  - 받기: 로그인했으면 계정의 주소로 답한다. 로그인하지 않았으면 적은 주소로 답한다.
  - 목록: 최근 것부터 PAGE_SIZE 개씩. 다음 쪽은 마지막 줄의 보낸 시각보다 앞의 것이다(before).
  - 답: 한 번만 쓴다. 답을 적는 일과 메일을 맡기는 일은 한 트랜잭션이다(답은 적혔는데 메일이 없는 일이 없다).
    같은 문의에 두 운영자가 함께 답하면 줄을 잠근 쪽만 적고 다른 쪽은 이미 답했다는 거절을 받는다.
  - 읽기: 운영자가 하나를 열면 처음 연 시각을 적는다(메일함의 읽음). 이미 적혔으면 그대로 둔다.
  - 지우기: 하나, 고른 것(SELECTED_MAX 개까지), 상자 하나를 통째로(답 기다림, 답함, 모두).
    보관 기간(1년)이 지난 것은 정리 명령이 지운다. 이미 맡긴 답 메일은 지워도 그대로 간다.
  - 누가: 처음 연 운영자와 답한 운영자는 문의에, 지운 일은 처리 기록(InquiryAction)에 남긴다.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import MailKind, MailReceipt, User
from accounts.outbox import enqueue_mail
from support.mail import REPLY_DEADLINE, REPLY_RECEIPT_PURPOSE, build_reply_message
from support.models import RETENTION, Inquiry, InquiryAction, InquiryActionKind, InquiryStatus

# 목록 한 쪽의 줄 수
PAGE_SIZE = 20

# 고른 것 지우기에 한 번에 실을 수 있는 문의의 수
SELECTED_MAX = 100

# 상자를 통째로 지울 때 "모두"를 뜻하는 이름. 나머지는 상태의 이름이다
ALL_FOLDER = 'all'

# 운영자가 보는 문의와 함께 읽는 것: 보낸 계정, 처음 연 운영자, 답한 운영자, 답 메일의 기록
OPERATOR_RELATED = ('user', 'read_by', 'answered_by', 'reply_receipt')


class InquiryNotFoundError(Exception):
    """그런 문의가 없다."""


class InquiryAlreadyAnsweredError(Exception):
    """이미 답한 문의다. 답은 한 번만 쓴다."""


@dataclass(frozen=True)
class FolderCounts:
    """상자마다의 수. unread 는 운영자가 아직 열지 않은 것이다."""

    all: int
    open: int
    answered: int
    unread: int


@dataclass(frozen=True)
class ActionPage:
    """처리 기록 한 쪽. next_before 가 None 이면 마지막 쪽이다."""

    items: list[InquiryAction]
    next_before: datetime | None


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
    found = Inquiry.objects.select_related(*OPERATOR_RELATED)
    if status:
        found = found.filter(status=status)
    return _page(found, before)


def folder_counts() -> FolderCounts:
    """상자마다의 수. 운영자 화면의 상자 이름 옆에 보인다."""
    counts = Inquiry.objects.aggregate(
        all=Count('id'),
        open=Count('id', filter=Q(status=InquiryStatus.OPEN)),
        answered=Count('id', filter=Q(status=InquiryStatus.ANSWERED)),
        unread=Count('id', filter=Q(read_at__isnull=True)),
    )
    return FolderCounts(**counts)


def read_inquiry(inquiry_id: uuid.UUID, operator: User) -> Inquiry:
    """운영자가 문의 하나를 연다. 처음이면 연 시각과 연 운영자를 적는다. 없으면 InquiryNotFoundError."""
    Inquiry.objects.filter(pk=inquiry_id, read_at__isnull=True).update(read_at=timezone.now(), read_by=operator)
    inquiry = Inquiry.objects.select_related(*OPERATOR_RELATED).filter(pk=inquiry_id).first()
    if inquiry is None:
        raise InquiryNotFoundError
    return inquiry


def delete_inquiry(inquiry_id: uuid.UUID, operator: User) -> None:
    """문의 하나를 지우고 처리 기록에 남긴다. 없으면 InquiryNotFoundError."""
    with transaction.atomic():
        deleted = _delete_and_record(
            Inquiry.objects.filter(pk=inquiry_id), kind=InquiryActionKind.DELETE_ONE, operator=operator
        )
    if deleted == 0:
        raise InquiryNotFoundError


def delete_selected_inquiries(inquiry_ids: list[uuid.UUID], operator: User) -> int:
    """고른 문의들을 지우고 지운 수를 돌려준다. 이미 없는 것은 건너뛴다(다른 운영자가 먼저 지웠을 수 있다)."""
    with transaction.atomic():
        return _delete_and_record(
            Inquiry.objects.filter(pk__in=inquiry_ids), kind=InquiryActionKind.DELETE_SELECTED, operator=operator
        )


def empty_folder(folder: str, operator: User) -> int:
    """상자 하나(상태, 또는 모두)를 통째로 비우고 지운 수를 돌려준다."""
    found = Inquiry.objects.all() if folder == ALL_FOLDER else Inquiry.objects.filter(status=folder)
    with transaction.atomic():
        return _delete_and_record(found, kind=InquiryActionKind.EMPTY_FOLDER, operator=operator, folder=folder)


def delete_old_inquiries(now: datetime | None = None) -> int:
    """
    보관 기간이 지난 문의를 지우고 지운 수를 돌려준다. 정리 명령이 하루 한 번 부른다.
    처리 기록도 같은 기간이 지난 것을 지운다.
    """
    cutoff = (now or timezone.now()) - RETENTION
    with transaction.atomic():
        deleted = _delete_and_record(
            Inquiry.objects.filter(created_at__lt=cutoff), kind=InquiryActionKind.RETENTION, operator=None
        )
        InquiryAction.objects.filter(created_at__lt=cutoff).delete()
    return deleted


def inquiry_actions(*, before: datetime | None) -> ActionPage:
    """처리 기록. 최근 것부터 한 쪽씩."""
    found = InquiryAction.objects.select_related('operator')
    if before is not None:
        found = found.filter(created_at__lt=before)
    rows = list(found.order_by('-created_at')[: PAGE_SIZE + 1])
    items = rows[:PAGE_SIZE]
    return ActionPage(items=items, next_before=items[-1].created_at if len(rows) > PAGE_SIZE else None)


def _delete_and_record(found, *, kind: str, operator: User | None, folder: str = '') -> int:
    """
    고른 문의들을 지우고, 지운 것이 있으면 처리 기록을 한 줄 남긴다. 부르는 쪽의 트랜잭션 안에서 부른다.
    지울 줄을 잠그고 번호를 읽은 뒤 지운다. 기록의 번호와 실제로 지운 것이 같다.
    """
    inquiry_ids = [str(pk) for pk in found.select_for_update().values_list('pk', flat=True)]
    if not inquiry_ids:
        return 0
    Inquiry.objects.filter(pk__in=inquiry_ids).delete()
    InquiryAction.objects.create(
        kind=kind, operator=operator, folder=folder, inquiry_ids=inquiry_ids, deleted_count=len(inquiry_ids)
    )
    return len(inquiry_ids)


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
