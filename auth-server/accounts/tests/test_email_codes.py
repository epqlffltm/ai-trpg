# auth-server/accounts/tests/test_email_codes.py

"""
이메일 인증 코드의 발급, 검증, 제한을 확인한다.
"""

from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import TestCase
from django.utils import timezone

from accounts.email_codes import (
    CODE_LIFETIME,
    ISSUE_COOLDOWN,
    ISSUE_WINDOW,
    MAX_FAILED_ATTEMPTS,
    MAX_ISSUES_PER_WINDOW,
    EmailCodeCooldownError,
    EmailCodeLimitError,
    InvalidEmailCodeError,
    consume_email_code,
    generate_code,
    has_usable_code,
    issue_email_code,
)
from accounts.mail import send_email_code
from accounts.models import EmailCode, EmailCodePurpose, User

SIGNUP = EmailCodePurpose.SIGNUP
LOGIN = EmailCodePurpose.LOGIN


def create_user(**overrides) -> User:
    fields = {
        'username': 'player_01',
        'email': 'someone@example.com',
        'nickname': '플레이어',
        'password': 'correct-horse-battery',
    }
    fields.update(overrides)
    return User.objects.create_user(**fields)


def wrong_code_for(code: str) -> str:
    """주어진 코드와 반드시 다른 코드."""
    return '000000' if code != '000000' else '111111'


class TimeTravelMixin:
    """발급과 검증이 보는 현재 시각을 테스트에서 옮긴다."""

    def at(self, moment):
        return patch('accounts.email_codes.timezone.now', return_value=moment)


class GenerateCodeTests(TestCase):
    def test_is_six_digits(self):
        for _ in range(200):
            code = generate_code()
            self.assertEqual(len(code), 6)
            self.assertTrue(code.isdigit())

    def test_keeps_leading_zeros(self):
        # 숫자 42 는 '42' 가 아니라 '000042' 가 되어야 한다
        with patch('accounts.email_codes.secrets.randbelow', return_value=42):
            self.assertEqual(generate_code(), '000042')


class IssueTests(TestCase):
    def setUp(self):
        self.user = create_user()

    def test_does_not_store_the_code_itself(self):
        code = issue_email_code(user=self.user, purpose=SIGNUP)

        record = EmailCode.objects.get(user=self.user, purpose=SIGNUP)
        self.assertNotEqual(record.code_hash, code)
        self.assertNotIn(code, record.code_hash)
        self.assertEqual(len(record.code_hash), 64)

    def test_same_code_hashes_differently_per_user_and_purpose(self):
        other_user = create_user(
            username='player_02',
            email='another@example.com',
            nickname='다른사람',
        )
        with patch('accounts.email_codes.generate_code', return_value='123456'):
            issue_email_code(user=self.user, purpose=SIGNUP)
            issue_email_code(user=self.user, purpose=LOGIN)
            issue_email_code(user=other_user, purpose=SIGNUP)

        hashes = set(EmailCode.objects.values_list('code_hash', flat=True))
        self.assertEqual(len(hashes), 3)

    def test_keeps_one_row_per_user_and_purpose(self):
        now = timezone.now()
        with patch('accounts.email_codes.timezone.now', return_value=now):
            issue_email_code(user=self.user, purpose=SIGNUP)
        with patch('accounts.email_codes.timezone.now', return_value=now + ISSUE_COOLDOWN):
            issue_email_code(user=self.user, purpose=SIGNUP)

        self.assertEqual(EmailCode.objects.filter(user=self.user, purpose=SIGNUP).count(), 1)


class ConsumeTests(TimeTravelMixin, TestCase):
    def setUp(self):
        self.user = create_user()
        self.issued_at = timezone.now()
        with self.at(self.issued_at):
            self.code = issue_email_code(user=self.user, purpose=SIGNUP)

    def consume(self, code: str, purpose: str = SIGNUP, user: User | None = None):
        consume_email_code(user=user or self.user, purpose=purpose, code=code)

    def test_accepts_correct_code(self):
        self.consume(self.code)

    def test_code_works_only_once(self):
        self.consume(self.code)

        with self.assertRaises(InvalidEmailCodeError):
            self.consume(self.code)

    def test_rejects_wrong_code(self):
        with self.assertRaises(InvalidEmailCodeError):
            self.consume(wrong_code_for(self.code))

    def test_wrong_code_does_not_spend_the_code(self):
        with self.assertRaises(InvalidEmailCodeError):
            self.consume(wrong_code_for(self.code))

        self.consume(self.code)

    def test_rejects_code_issued_for_another_purpose(self):
        with self.assertRaises(InvalidEmailCodeError):
            self.consume(self.code, purpose=LOGIN)

    def test_rejects_code_issued_to_another_user(self):
        other_user = create_user(
            username='player_02',
            email='another@example.com',
            nickname='다른사람',
        )

        with self.assertRaises(InvalidEmailCodeError):
            self.consume(self.code, user=other_user)

    def test_rejects_expired_code(self):
        with self.at(self.issued_at + CODE_LIFETIME):
            with self.assertRaises(InvalidEmailCodeError):
                self.consume(self.code)

    def test_accepts_code_just_before_expiry(self):
        with self.at(self.issued_at + CODE_LIFETIME - timedelta(seconds=1)):
            self.consume(self.code)

    def test_rejects_when_nothing_was_issued(self):
        with self.assertRaises(InvalidEmailCodeError):
            self.consume('123456', purpose=LOGIN)

    def test_counts_wrong_attempts(self):
        for _ in range(2):
            with self.assertRaises(InvalidEmailCodeError):
                self.consume(wrong_code_for(self.code))

        record = EmailCode.objects.get(user=self.user, purpose=SIGNUP)
        self.assertEqual(record.failed_attempts, 2)

    def test_discards_code_after_too_many_wrong_attempts(self):
        for _ in range(MAX_FAILED_ATTEMPTS):
            with self.assertRaises(InvalidEmailCodeError):
                self.consume(wrong_code_for(self.code))

        # 한도에 닿으면 정답으로도 통과할 수 없다
        with self.assertRaises(InvalidEmailCodeError):
            self.consume(self.code)

    def test_new_code_replaces_the_old_one(self):
        with self.at(self.issued_at + ISSUE_COOLDOWN):
            with patch('accounts.email_codes.generate_code', return_value=wrong_code_for(self.code)):
                new_code = issue_email_code(user=self.user, purpose=SIGNUP)

            with self.assertRaises(InvalidEmailCodeError):
                self.consume(self.code)
            self.consume(new_code)

    def test_new_code_resets_wrong_attempts(self):
        for _ in range(MAX_FAILED_ATTEMPTS):
            with self.assertRaises(InvalidEmailCodeError):
                self.consume(wrong_code_for(self.code))

        with self.at(self.issued_at + ISSUE_COOLDOWN):
            new_code = issue_email_code(user=self.user, purpose=SIGNUP)
            self.consume(new_code)


class IssueLimitTests(TimeTravelMixin, TestCase):
    def setUp(self):
        self.user = create_user()
        self.start = timezone.now()

    def issue_at(self, moment, purpose: str = SIGNUP) -> str:
        with self.at(moment):
            return issue_email_code(user=self.user, purpose=purpose)

    def issue_as_many_as_allowed(self):
        """쿨다운을 지키면서 한 구간에 허용된 횟수를 다 쓴다. 마지막 발급 시각을 돌려준다."""
        moment = self.start
        for index in range(MAX_ISSUES_PER_WINDOW):
            moment = self.start + ISSUE_COOLDOWN * index
            self.issue_at(moment)
        return moment

    def test_rejects_second_issue_within_cooldown(self):
        self.issue_at(self.start)

        with self.assertRaises(EmailCodeCooldownError) as caught:
            self.issue_at(self.start + timedelta(seconds=10))

        self.assertEqual(caught.exception.retry_after, ISSUE_COOLDOWN - timedelta(seconds=10))

    def test_rejected_issue_keeps_the_current_code(self):
        code = self.issue_at(self.start)

        with self.assertRaises(EmailCodeCooldownError):
            self.issue_at(self.start + timedelta(seconds=10))

        with self.at(self.start + timedelta(seconds=20)):
            consume_email_code(user=self.user, purpose=SIGNUP, code=code)

    def test_allows_issue_after_cooldown(self):
        self.issue_at(self.start)

        self.issue_at(self.start + ISSUE_COOLDOWN)

    def test_using_a_code_lifts_the_cooldown(self):
        code = self.issue_at(self.start)
        with self.at(self.start + timedelta(seconds=10)):
            consume_email_code(user=self.user, purpose=SIGNUP, code=code)

        # 코드를 맞게 쓴 뒤에는 1분을 기다리지 않고 다시 발급받을 수 있다
        self.issue_at(self.start + timedelta(seconds=20))

    def test_using_a_code_does_not_reset_the_window_count(self):
        moment = self.start
        for index in range(MAX_ISSUES_PER_WINDOW):
            moment = self.start + timedelta(seconds=index)
            code = self.issue_at(moment)
            with self.at(moment):
                consume_email_code(user=self.user, purpose=SIGNUP, code=code)

        # 대기 시간은 풀려도, 한 구간의 발급 횟수 제한은 그대로다
        with self.assertRaises(EmailCodeLimitError):
            self.issue_at(moment + timedelta(seconds=1))

    def test_wrong_attempts_do_not_lift_the_cooldown(self):
        code = self.issue_at(self.start)
        with self.at(self.start + timedelta(seconds=10)):
            with self.assertRaises(InvalidEmailCodeError):
                consume_email_code(user=self.user, purpose=SIGNUP, code=wrong_code_for(code))

        with self.assertRaises(EmailCodeCooldownError):
            self.issue_at(self.start + timedelta(seconds=20))

    def test_has_usable_code(self):
        self.assertFalse(has_usable_code(user=self.user, purpose=SIGNUP))

        code = self.issue_at(self.start)
        with self.at(self.start + timedelta(seconds=10)):
            self.assertTrue(has_usable_code(user=self.user, purpose=SIGNUP))
            self.assertFalse(has_usable_code(user=self.user, purpose=LOGIN))
        with self.at(self.start + CODE_LIFETIME):
            self.assertFalse(has_usable_code(user=self.user, purpose=SIGNUP))
        with self.at(self.start + timedelta(seconds=20)):
            consume_email_code(user=self.user, purpose=SIGNUP, code=code)
            self.assertFalse(has_usable_code(user=self.user, purpose=SIGNUP))

    def test_rejects_issue_over_the_window_limit(self):
        last_issue = self.issue_as_many_as_allowed()

        with self.assertRaises(EmailCodeLimitError):
            self.issue_at(last_issue + ISSUE_COOLDOWN)

    def test_allows_issue_in_the_next_window(self):
        self.issue_as_many_as_allowed()

        self.issue_at(self.start + ISSUE_WINDOW)

    def test_rejected_issue_does_not_extend_the_window(self):
        last_issue = self.issue_as_many_as_allowed()
        with self.assertRaises(EmailCodeLimitError):
            self.issue_at(last_issue + ISSUE_COOLDOWN)
        with self.assertRaises(EmailCodeLimitError):
            self.issue_at(self.start + ISSUE_WINDOW - timedelta(seconds=1))

        # 구간은 첫 발급 시각에서 시작한다. 거부된 요청이 구간을 뒤로 밀지 않는다
        self.issue_at(self.start + ISSUE_WINDOW)

    def test_limits_are_separate_per_purpose(self):
        self.issue_at(self.start, purpose=SIGNUP)

        self.issue_at(self.start, purpose=LOGIN)


class SendEmailCodeTests(TestCase):
    def test_sends_code_to_the_user(self):
        user = create_user()

        send_email_code(user=user, purpose=SIGNUP, code='123456')

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['someone@example.com'])
        self.assertIn('123456', message.body)
        self.assertIn('가입 인증', message.subject)

    def test_subject_depends_on_purpose(self):
        user = create_user()

        send_email_code(user=user, purpose=LOGIN, code='123456')

        self.assertIn('로그인 인증', mail.outbox[0].subject)