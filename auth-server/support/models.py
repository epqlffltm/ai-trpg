# auth-server/support/models.py

"""
문의 하나. 로그인한 사람도, 로그인하지 못하는 사람도 보낸다(로그인이 안 되는 문의가 있다).

답은 운영자가 한 번 쓰고, 메일로 보낸다. 로그인한 사람은 마이페이지에서도 답을 본다.
답을 보냈는지는 보낸 메일의 기록(MailReceipt)으로 남긴다.
받는 사람의 주소를 기록에 적지 않는 것은 그 기록의 규칙과 같다.

탈퇴하면 그 사람의 문의를 지운다(accounts/erasure.py). 계정의 줄은 남지만 문의는 그 사람이 쓴 글이다.
"""

import uuid

from django.conf import settings
from django.db import models

# 제목과 본문, 답의 최대 길이(글자)
TITLE_MAX_LENGTH = 100
BODY_MAX_LENGTH = 5000
REPLY_MAX_LENGTH = 5000


class InquiryCategory(models.TextChoices):
    """문의의 종류. 운영자가 목록을 가를 때와 답을 쓸 때 본다."""

    ACCOUNT = 'account', '계정·로그인'
    PAYMENT = 'payment', '결제·환불'
    REPORT = 'report', '신고'
    BUG = 'bug', '오류'
    OTHER = 'other', '그 밖'


class InquiryStatus(models.TextChoices):
    OPEN = 'open', '답을 기다림'
    ANSWERED = 'answered', '답함'


class Inquiry(models.Model):
    # 주소에 싣는 번호. 차례가 드러나지 않게 UUID 다
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # 보낸 계정. 로그인하지 않고 보냈으면 비어 있다
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='보낸 계정',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='inquiries',
    )
    category = models.CharField('종류', max_length=20, choices=InquiryCategory.choices)
    title = models.CharField('제목', max_length=TITLE_MAX_LENGTH)
    body = models.TextField('내용')
    # 답을 받을 주소. 로그인했으면 보낼 때의 계정 주소다
    email = models.EmailField('답 받을 주소')
    status = models.CharField('상태', max_length=20, choices=InquiryStatus.choices, default=InquiryStatus.OPEN)
    created_at = models.DateTimeField('보낸 시각', auto_now_add=True)
    reply = models.TextField('답', blank=True)
    answered_at = models.DateTimeField('답한 시각', null=True, blank=True)
    # 답한 운영자. 운영자의 계정이 비워져도 답은 남는다
    answered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='답한 운영자',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    # 답의 메일을 보냈는지의 기록
    reply_receipt = models.OneToOneField(
        'accounts.MailReceipt',
        verbose_name='답 메일의 기록',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )

    class Meta:
        verbose_name = '문의'
        verbose_name_plural = '문의'
        indexes = [
            # 운영자의 목록: 상태마다 최근 것부터
            models.Index(fields=['status', '-created_at'], name='inquiry_status_recent'),
            # 내 문의: 최근 것부터
            models.Index(fields=['user', '-created_at'], name='inquiry_user_recent'),
        ]

    def __str__(self) -> str:
        return f'{self.get_category_display()} / {self.title}'
