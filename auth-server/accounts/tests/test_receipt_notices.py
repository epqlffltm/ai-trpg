# auth-server/accounts/tests/test_receipt_notices.py

"""
결제 서버가 보낸 본인 결제 알림(#553)을 검증한다. 실제 주소로 서명한 요청을 보내고, 결제한 본인에게 간 메일을 본다.

  - 서명: 결제 서버의 서명이 아니면 아무것도 적지 않는다
  - 알림: 결제한 본인에게 한 번만. 받은 골드, 청약철회의 기한, 주문 내역 링크를 싣는다
  - 알릴 계정이 없으면(모르는 사용자, 탈퇴를 마침) 적기만 한다
  - 보낸 기록: 발송함을 거쳐도 메일 서버가 받은 시각이 남는다
"""

import json
import time
import uuid
from datetime import UTC, datetime

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import MailKind, MailReceipt, OutgoingMail, ReceiptNotice, User
from accounts.outbox import deliver_due_mail
from accounts.receipt_notices import RECEIPT_MAIL_DEADLINE
from accounts.service_signature import SIGNATURE_HEADER, sign_request
from accounts.tests.billing_stub import SECRET

NOTICES_URL = reverse('accounts:service-receipt-notices')
ORDER_ID = '11111111-2222-4333-8444-555555555555'
BUYER_EMAIL = 'player1@example.com'


def make_buyer() -> User:
    return User.objects.create_user(
        username='player_01',
        email=BUYER_EMAIL,
        nickname='플레이어1',
        password='correct-horse-battery',
        email_verified_at=timezone.now(),
    )


def notice_body(user: User, **overrides) -> bytes:
    fields = {
        'order_id': ORDER_ID,
        'kind': 'paid',
        'user_id': str(user.public_id),
        'product_id': 'credits-1000',
        'price': 1000,
        'credits': 1000,
        'paid_at': '2026-03-02T09:30:00Z',
        'occurred_at': '2026-03-02T09:30:00Z',
        'refundable_until': '2026-03-09T09:30:00Z',
    }
    fields.update(overrides)
    return json.dumps(fields).encode()


@override_settings(BILLING_SECRET=SECRET, ORDERS_URL='https://example.test/wallet/orders/')
class NoticeTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.buyer = make_buyer()
        mail.outbox.clear()

    def post(self, body: bytes, *, secret: str = SECRET, path: str = NOTICES_URL):
        """결제 서버가 하듯 서명해 보낸다."""
        signature = sign_request(secret=secret, method='POST', request_uri=path, body=body, sent_at=int(time.time()))
        return self.client.generic(
            'POST',
            NOTICES_URL,
            body,
            content_type='application/json',
            **{'HTTP_' + SIGNATURE_HEADER.upper().replace('-', '_'): signature},
        )


class SignatureTests(NoticeTestCase):
    def test_only_the_billing_servers_signature_is_accepted(self):
        body = notice_body(self.buyer)
        refused = {
            '다른 비밀': self.post(body, secret='another-secret-that-is-32-chars!!'),
            # 보호자 알림의 주소에 한 서명을 이 주소에 다시 쓸 수 없다
            '다른 주소에 서명했다': self.post(body, path='/api/v1/auth/service/guardian-notices'),
            '서명이 없다': self.client.post(NOTICES_URL, body, content_type='application/json'),
        }
        for name, response in refused.items():
            with self.subTest(name):
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
                self.assertEqual(response.data['code'], 'service_bad_signature')
        self.assertFalse(ReceiptNotice.objects.exists())
        self.assertEqual(len(mail.outbox), 0)


class NoticeTests(NoticeTestCase):
    def test_the_buyer_is_told_once_with_the_refund_deadline(self):
        first = self.post(notice_body(self.buyer))
        again = self.post(notice_body(self.buyer))

        self.assertEqual((first.status_code, first.data['status']), (200, 'queued'))
        self.assertEqual(again.data['status'], 'duplicate')
        self.assertEqual(len(mail.outbox), 1)
        # 두 번째에 만든 보낸 기록은 지운다. 보내지 않은 메일의 기록이 남지 않는다
        self.assertEqual(MailReceipt.objects.count(), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [BUYER_EMAIL])
        self.assertEqual(message.subject, '[AI TRPG] 결제를 확인했습니다')
        for text in (
            '플레이어1',
            ORDER_ID,
            'credits-1000',
            '1,000원',
            '받은 골드: 1,000',
            '결제 시각: 2026-03-02 18:30 (한국 시각)',
            '2026-03-09 18:30 (한국 시각)까지',
            f'https://example.test/wallet/orders/{ORDER_ID}',
        ):
            self.assertIn(text, message.body)

    def test_a_refund_is_told_too(self):
        self.post(notice_body(self.buyer))

        response = self.post(notice_body(self.buyer, kind='refunded', occurred_at='2026-03-03T01:00:00Z'))

        self.assertEqual(response.data['status'], 'queued')
        message = mail.outbox[-1]
        self.assertEqual(message.subject, '[AI TRPG] 청약철회를 마쳤습니다')
        for text in (
            '돌려 드리는 금액: 1,000원',
            '거둬들인 골드: 1,000',
            '청약철회 시각: 2026-03-03 10:00 (한국 시각)',
        ):
            self.assertIn(text, message.body)
        # 끝난 청약철회에는 기한을 싣지 않는다
        self.assertNotIn('2026-03-09', message.body)
        self.assertEqual(ReceiptNotice.objects.count(), 2)

    def test_an_unknown_user_is_only_recorded(self):
        stranger = str(uuid.uuid4())

        response = self.post(notice_body(self.buyer, user_id=stranger))

        notice = ReceiptNotice.objects.get()
        self.assertEqual(response.data['status'], 'skipped')
        self.assertEqual(str(notice.user_public_id), stranger)
        self.assertIsNone(notice.receipt)
        self.assertEqual(len(mail.outbox), 0)

    def test_a_withdrawn_account_is_only_recorded(self):
        # 탈퇴를 마친 계정은 주소를 지웠다. 그 자리의 글자로 보내지 않는다
        User.objects.filter(pk=self.buyer.pk).update(withdrawn_at=timezone.now())

        response = self.post(notice_body(self.buyer))

        self.assertEqual(response.data['status'], 'skipped')
        self.assertEqual(len(mail.outbox), 0)

    def test_a_bad_body_is_refused(self):
        for name, body in {
            'JSON 이 아니다': b'nope',
            '모르는 종류': notice_body(self.buyer, kind='charged'),
            '값이 0': notice_body(self.buyer, price=0),
            '기한이 없다': json.dumps({**json.loads(notice_body(self.buyer)), 'refundable_until': None}).encode(),
            '시각이 아니다': notice_body(self.buyer, paid_at='yesterday'),
        }.items():
            with self.subTest(name):
                self.assertEqual(self.post(body).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ReceiptNotice.objects.exists())

    def test_the_record_keeps_what_was_told(self):
        self.post(notice_body(self.buyer))

        notice = ReceiptNotice.objects.get()
        self.assertEqual(str(notice.order_id), ORDER_ID)
        self.assertEqual(notice.user, self.buyer)
        self.assertEqual((notice.price, notice.credits), (1000, 1000))
        self.assertEqual(notice.refundable_until, datetime(2026, 3, 9, 9, 30, tzinfo=UTC))
        # 바로 보내는 설정(테스트)이라 메일 서버가 이미 받았다
        self.assertIsNotNone(notice.receipt.sent_at)


@override_settings(BILLING_SECRET=SECRET, MAIL_DELIVERY='outbox')
class OutboxTests(NoticeTestCase):
    """발송함을 거칠 때 메일의 종류와 기한, 보낸 기록을 본다."""

    def test_the_mail_waits_a_day_and_marks_the_receipt(self):
        self.post(notice_body(self.buyer))
        queued = OutgoingMail.objects.get()
        receipt = ReceiptNotice.objects.get().receipt

        self.assertEqual(queued.kind, MailKind.PAYMENT_RECEIPT)
        self.assertAlmostEqual(
            (queued.expires_at - queued.next_attempt_at).total_seconds(), RECEIPT_MAIL_DEADLINE.total_seconds(), delta=1
        )
        deliver_due_mail()

        receipt.refresh_from_db()
        self.assertIsNotNone(receipt.sent_at)
        self.assertEqual(mail.outbox[-1].to, [BUYER_EMAIL])

    def test_a_refund_mail_has_its_own_kind(self):
        self.post(notice_body(self.buyer, kind='refunded'))

        self.assertEqual(OutgoingMail.objects.get().kind, MailKind.REFUND_RECEIPT)
