# auth-server/accounts/tests/test_guardian_notices.py

"""
결제 서버가 보낸 보호자 알림(#352)을 검증한다. 실제 주소로 서명한 요청을 보내고, 보호자에게 간 메일을 본다.

  - 서명: 결제 서버의 서명이 아니면 아무것도 적지 않는다
  - 알림: 동의한 보호자에게 한 번만, 철회 링크와 함께. 알릴 보호자가 없으면 적기만 한다
  - 보낸 기록: 메일 서버가 받은 시각이 남는다. 발송함의 줄은 지워져도 남는다
"""

import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.guardian_notices import NOTICE_MAIL_DEADLINE
from accounts.identity import verify_identity
from accounts.models import (
    GuardianConsent,
    GuardianConsentStatus,
    GuardianNotice,
    MailReceipt,
    OutgoingMail,
    User,
)
from accounts.outbox import deliver_due_mail
from accounts.service_signature import SIGNATURE_HEADER, sign_request
from accounts.tests.billing_stub import SECRET
from accounts.tests.helpers import identity_token

NOTICES_URL = reverse('accounts:service-guardian-notices')
GUARDIAN_EMAIL = 'parent@example.com'
ORDER_ID = '11111111-2222-4333-8444-555555555555'


def make_minor(consented: bool = True) -> User:
    """본인인증을 마친 17세. consented 면 보호자가 동의해 있다."""
    minor = User.objects.create_user(
        username='player_01',
        email='player1@example.com',
        nickname='플레이어1',
        password='correct-horse-battery',
        email_verified_at=timezone.now(),
    )
    verify_identity(user=minor, token=identity_token('minor-di', timezone.localdate().replace(year=2009)))
    GuardianConsent.objects.create(
        minor=minor,
        guardian_email=GUARDIAN_EMAIL if consented else '',
        status=GuardianConsentStatus.CONSENTED if consented else GuardianConsentStatus.REVOKED,
        link_nonce='nonce-1',
        requested_at=timezone.now(),
        window_started_at=timezone.now(),
    )
    return minor


def notice_body(user: User, **overrides) -> bytes:
    fields = {
        'order_id': ORDER_ID,
        'kind': 'paid',
        'user_id': str(user.public_id),
        'product_id': 'credits-1000',
        'price': 1000,
        'credits': 1000,
        'occurred_at': '2026-03-02T09:30:00Z',
    }
    fields.update(overrides)
    return json.dumps(fields).encode()


@override_settings(BILLING_SECRET=SECRET)
class NoticeTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.minor = make_minor()
        mail.outbox.clear()

    def post(self, body: bytes, *, secret: str = SECRET, path: str = NOTICES_URL, sent_at: int | None = None):
        """결제 서버가 하듯 서명해 보낸다."""
        signature = sign_request(
            secret=secret, method='POST', request_uri=path, body=body, sent_at=sent_at or int(time.time())
        )
        return self.client.generic(
            'POST',
            NOTICES_URL,
            body,
            content_type='application/json',
            **{'HTTP_' + SIGNATURE_HEADER.upper().replace('-', '_'): signature},
        )


class SignatureTests(NoticeTestCase):
    def test_only_the_billing_servers_signature_is_accepted(self):
        body = notice_body(self.minor)
        refused = {
            '다른 비밀': self.post(body, secret='another-secret-that-is-32-chars!!'),
            '다른 주소에 서명했다': self.post(body, path='/api/v1/billing/service/grants/welcome'),
            '10분 전의 서명': self.post(body, sent_at=int(time.time()) - 600),
            '서명이 없다': self.client.post(NOTICES_URL, body, content_type='application/json'),
        }
        for name, response in refused.items():
            with self.subTest(name):
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
                self.assertEqual(response.data['code'], 'service_bad_signature')
        self.assertFalse(GuardianNotice.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(BILLING_SECRET='')
    def test_without_the_secret_nothing_is_accepted(self):
        response = self.post(notice_body(self.minor), secret='')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_user_token_is_not_enough(self):
        # 사용자의 토큰으로는 남의 보호자에게 메일을 보낼 수 없다
        self.client.credentials(HTTP_AUTHORIZATION='Bearer anything')

        response = self.client.post(NOTICES_URL, notice_body(self.minor), content_type='application/json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class NoticeTests(NoticeTestCase):
    def test_the_guardian_is_told_once_with_a_revoke_link(self):
        first = self.post(notice_body(self.minor))
        again = self.post(notice_body(self.minor))

        self.assertEqual((first.status_code, first.data['status']), (200, 'queued'))
        self.assertEqual(again.data['status'], 'duplicate')
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [GUARDIAN_EMAIL])
        self.assertEqual(message.subject, '[AI TRPG] 결제 알림')
        for text in ('플레이어1', 'credits-1000', '1,000원', '2026-03-02 18:30 (한국 시각)', '/guardian/revoke#token='):
            self.assertIn(text, message.body)
        # 아이디와 이메일은 보호자에게 보이지 않는다
        self.assertNotIn('player_01', message.body)

    def test_a_refund_is_told_too(self):
        self.post(notice_body(self.minor))

        response = self.post(notice_body(self.minor, kind='refunded', occurred_at='2026-03-03T01:00:00Z'))

        self.assertEqual(response.data['status'], 'queued')
        self.assertEqual(mail.outbox[-1].subject, '[AI TRPG] 청약철회 알림')
        self.assertEqual(GuardianNotice.objects.count(), 2)

    def test_without_a_consenting_guardian_it_is_only_recorded(self):
        # 결제 뒤에 보호자가 철회했다. 알릴 곳이 없다
        GuardianConsent.objects.update(status=GuardianConsentStatus.REVOKED, guardian_email='')

        response = self.post(notice_body(self.minor))

        notice = GuardianNotice.objects.get()
        self.assertEqual(response.data['status'], 'skipped')
        self.assertEqual(notice.outcome, 'skipped')
        self.assertIsNone(notice.receipt)
        self.assertEqual(len(mail.outbox), 0)

    def test_an_unknown_user_is_only_recorded(self):
        stranger = str(uuid.uuid4())

        response = self.post(notice_body(self.minor, user_id=stranger))

        self.assertEqual(response.data['status'], 'skipped')
        self.assertEqual(str(GuardianNotice.objects.get().minor_public_id), stranger)

    def test_a_bad_body_is_refused(self):
        for name, body in {
            'JSON 이 아니다': b'nope',
            '모르는 종류': notice_body(self.minor, kind='charged'),
            '값이 0': notice_body(self.minor, price=0),
            '시각이 아니다': notice_body(self.minor, occurred_at='yesterday'),
        }.items():
            with self.subTest(name):
                self.assertEqual(self.post(body).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(GuardianNotice.objects.exists())

    def test_the_record_keeps_what_was_told(self):
        self.post(notice_body(self.minor))

        notice = GuardianNotice.objects.get()
        self.assertEqual(str(notice.order_id), ORDER_ID)
        self.assertEqual(notice.minor, self.minor)
        self.assertEqual((notice.price, notice.credits), (1000, 1000))
        self.assertEqual(notice.occurred_at, datetime(2026, 3, 2, 9, 30, tzinfo=UTC))
        # 바로 보내는 설정(테스트)이라 메일 서버가 이미 받았다
        self.assertIsNotNone(notice.receipt.sent_at)


@override_settings(BILLING_SECRET=SECRET, MAIL_DELIVERY='outbox')
class ReceiptTests(NoticeTestCase):
    """발송함을 거칠 때 보낸 기록이 남는지 본다. 발송함의 줄은 보내면 지워진다."""

    def test_sending_marks_the_receipt(self):
        self.post(notice_body(self.minor))
        receipt = GuardianNotice.objects.get().receipt
        self.assertIsNone(receipt.sent_at)

        deliver_due_mail()

        receipt.refresh_from_db()
        self.assertFalse(OutgoingMail.objects.exists())
        self.assertIsNotNone(receipt.sent_at)
        self.assertEqual(mail.outbox[-1].to, [GUARDIAN_EMAIL])

    def test_a_notice_waits_a_day_before_it_is_discarded(self):
        # 인증 코드는 5분이면 버리지만 결제 알림은 하루 늦어도 쓸모가 있다
        self.post(notice_body(self.minor))
        queued = OutgoingMail.objects.get()

        self.assertAlmostEqual(
            (queued.expires_at - queued.next_attempt_at).total_seconds(), NOTICE_MAIL_DEADLINE.total_seconds(), delta=1
        )

    def test_discarding_marks_the_receipt(self):
        self.post(notice_body(self.minor))

        with (
            patch(
                'accounts.outbox.timezone.now',
                return_value=timezone.now() + NOTICE_MAIL_DEADLINE + timedelta(seconds=1),
            ),
            self.assertLogs('accounts.outbox', level='ERROR'),
        ):
            deliver_due_mail()

        receipt = MailReceipt.objects.get()
        self.assertIsNone(receipt.sent_at)
        self.assertIsNotNone(receipt.discarded_at)

    def test_ordinary_mail_has_no_receipt(self):
        from accounts.outbox import enqueue_mail

        enqueue_mail(to_email='someone@example.com', subject='s', body='b')
        deliver_due_mail()

        self.assertFalse(MailReceipt.objects.exists())
