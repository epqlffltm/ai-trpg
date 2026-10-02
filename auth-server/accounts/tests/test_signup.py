# auth-server/accounts/tests/test_signup.py

"""
회원가입과 이메일 인증을 검증한다.

실제 URL 로 요청을 보내 뷰, Serializer, service, DB 를 한 번에 거친다.
"""

import re
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.email_codes import ISSUE_COOLDOWN, MAX_ISSUES_PER_WINDOW
from accounts.models import EmailCode, User
from accounts.services import PENDING_ACCOUNT_LIFETIME

SIGNUP_URL = reverse('accounts:signup')
VERIFY_URL = reverse('accounts:signup-verify')
RESEND_URL = reverse('accounts:signup-resend')
LOGIN_URL = reverse('accounts:login')

PASSWORD = 'correct-horse-battery'
EMAIL = 'someone@example.com'


def signup_payload(**overrides) -> dict:
    """테스트마다 달라지는 값만 넘기고 나머지는 기본값을 쓴다."""
    payload = {
        'username': 'player_01',
        'email': EMAIL,
        'nickname': '플레이어',
        'password': PASSWORD,
    }
    payload.update(overrides)
    return payload


def code_from(message) -> str:
    """메일 본문에서 6자리 인증 코드를 꺼낸다."""
    return re.search(r'\b(\d{6})\b', message.body).group(1)


def wrong_code_for(code: str) -> str:
    return '000000' if code != '000000' else '111111'


class SignupTestCase(APITestCase):
    def signup(self, **overrides):
        return self.client.post(SIGNUP_URL, signup_payload(**overrides), format='json')

    def verify(self, code: str, email: str = EMAIL):
        return self.client.post(VERIFY_URL, {'email': email, 'code': code}, format='json')

    def resend(self, email: str = EMAIL):
        return self.client.post(RESEND_URL, {'email': email}, format='json')

    def login(self, username: str = 'player_01', password: str = PASSWORD):
        return self.client.post(
            LOGIN_URL,
            {'username': username, 'password': password},
            format='json',
        )

    def signup_and_verify(self, **overrides) -> User:
        """가입부터 인증까지 끝낸 계정을 만든다."""
        self.signup(**overrides)
        payload = signup_payload(**overrides)
        self.verify(code_from(mail.outbox[-1]), email=payload['email'])
        return User.objects.get(username=payload['username'])

    def age_pending_account(self, username: str, age: timedelta) -> None:
        """미인증 계정이 age 만큼 전에 만들어진 것처럼 바꾼다."""
        User.objects.filter(username=username).update(date_joined=timezone.now() - age)


class SignupStartTests(SignupTestCase):
    def test_returns_202_without_account_details(self):
        response = self.signup()

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(set(response.data), {'detail'})

    def test_creates_unverified_user(self):
        self.signup()

        user = User.objects.get(username='player_01')
        self.assertFalse(user.is_email_verified)

    def test_sends_code_to_the_email(self):
        self.signup()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [EMAIL])
        self.assertRegex(code_from(mail.outbox[0]), r'^\d{6}$')

    def test_password_is_stored_hashed(self):
        self.signup()

        user = User.objects.get(username='player_01')
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))

    def test_email_is_stored_in_lowercase(self):
        self.signup(email='Someone@Example.com')

        user = User.objects.get(username='player_01')
        self.assertEqual(user.email, EMAIL)

    def test_new_user_has_no_admin_rights(self):
        # 요청 본문에 권한 필드를 끼워 넣어도 무시되어야 한다
        self.signup(is_staff=True, is_superuser=True, email_verified_at='2020-01-01T00:00:00Z')

        user = User.objects.get(username='player_01')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_email_verified)

    def test_get_is_not_allowed(self):
        response = self.client.get(SIGNUP_URL)

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class SignupValidationTests(SignupTestCase):
    def assert_rejected(self, field: str, **overrides) -> None:
        """400 으로 거부되고, 오류가 해당 필드에 달려 있고, 계정도 메일도 생기지 않았는지 확인한다."""
        response = self.signup(**overrides)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(field, response.data)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_rejects_uppercase_username(self):
        self.assert_rejected('username', username='Player_01')

    def test_rejects_reserved_username(self):
        self.assert_rejected('username', username='admin')

    def test_rejects_username_equal_to_email_local_part(self):
        self.assert_rejected('username', username='someone')

    def test_rejects_reserved_nickname(self):
        self.assert_rejected('nickname', nickname='운영자')
        self.assert_rejected('nickname', nickname='GM')

    def test_rejects_nickname_with_space(self):
        self.assert_rejected('nickname', nickname='운 영 자')

    def test_rejects_invalid_email(self):
        self.assert_rejected('email', email='not-an-email')

    def test_rejects_weak_passwords(self):
        weak_passwords = [
            'short1!',          # 8자 미만
            '1234567890',       # 숫자만
            'password123',      # 흔한 비밀번호
            'player_01',        # 아이디와 같음
        ]
        for password in weak_passwords:
            with self.subTest(password=password):
                self.assert_rejected('password', password=password)

    def test_rejects_missing_field(self):
        payload = signup_payload()
        del payload['nickname']

        response = self.client.post(SIGNUP_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('nickname', response.data)


class SignupTakenTests(SignupTestCase):
    """아이디와 닉네임의 중복. 이것은 숨기지 않는다. 다른 값을 골라야 하기 때문이다."""

    def setUp(self):
        self.signup_and_verify()
        mail.outbox.clear()

    def test_rejects_taken_username(self):
        response = self.signup(email='another@example.com', nickname='다른사람')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data)

    def test_rejects_taken_nickname(self):
        response = self.signup(username='player_02', email='another@example.com')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('nickname', response.data)

    def test_rejects_username_held_by_recent_pending_account(self):
        self.signup(username='player_02', email='another@example.com', nickname='다른사람')

        response = self.signup(username='player_02', email='third@example.com', nickname='세번째')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data)

    def test_returns_409_when_database_rejects_duplicate(self):
        # 동시 요청으로 사전 조회를 둘 다 통과한 상황을 흉내 낸다
        with patch.object(User, 'save', side_effect=IntegrityError):
            response = self.signup(username='player_02', email='another@example.com', nickname='다른사람')

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(User.objects.filter(username='player_02').exists())


class SignupRegisteredEmailTests(SignupTestCase):
    """이미 가입된 이메일로 가입을 시도하는 경우. 응답으로는 그 사실이 드러나지 않아야 한다."""

    def setUp(self):
        self.signup_and_verify()
        mail.outbox.clear()

    def signup_with_registered_email(self):
        return self.signup(username='player_02', nickname='다른사람')

    def after_cooldown(self):
        """
        가입 직후는 그 주소로 방금 메일이 나간 상태라 발급 제한에 걸린다.
        안내 메일이 나가는지 보려면 제한 시간이 지난 시점으로 옮겨야 한다.
        """
        return patch(
            'accounts.email_codes.timezone.now',
            return_value=timezone.now() + ISSUE_COOLDOWN,
        )

    def test_response_is_identical_to_a_new_signup(self):
        new_signup = self.signup(username='player_03', email='fresh@example.com', nickname='새사람')
        registered = self.signup_with_registered_email()

        self.assertEqual(registered.status_code, new_signup.status_code)
        self.assertEqual(registered.data, new_signup.data)

    def test_does_not_create_an_account(self):
        self.signup_with_registered_email()

        self.assertFalse(User.objects.filter(username='player_02').exists())
        self.assertEqual(User.objects.filter(email=EMAIL).count(), 1)

    def test_does_not_change_the_existing_account(self):
        self.signup_with_registered_email()

        user = User.objects.get(email=EMAIL)
        self.assertEqual(user.username, 'player_01')
        self.assertTrue(user.check_password(PASSWORD))
        self.assertTrue(user.is_email_verified)

    def test_notifies_the_owner_instead_of_sending_a_code(self):
        with self.after_cooldown():
            self.signup_with_registered_email()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [EMAIL])
        self.assertIn('이미 가입', mail.outbox[0].subject)
        self.assertIsNone(re.search(r'\b\d{6}\b', mail.outbox[0].body))

    def test_email_match_ignores_case(self):
        self.signup(username='player_02', nickname='다른사람', email='SOMEONE@example.com')

        self.assertFalse(User.objects.filter(username='player_02').exists())

    def test_notices_are_rate_limited(self):
        with self.after_cooldown():
            for _ in range(3):
                self.signup_with_registered_email()

        # 가입 요청을 반복해 남의 메일함에 안내 메일을 쏟아부을 수 없어야 한다
        self.assertEqual(len(mail.outbox), 1)

    def test_hashes_password_even_though_no_account_is_created(self):
        # 해싱을 건너뛰면 응답이 빨라져, 걸린 시간으로 가입 여부가 드러난다
        with patch('accounts.services.make_password', wraps=lambda password: 'hashed') as hasher:
            self.signup_with_registered_email()

        hasher.assert_called_once()


class SignupPendingAccountTests(SignupTestCase):
    """인증을 끝내지 않은 계정의 교체와 삭제."""

    def test_same_email_replaces_the_pending_account(self):
        self.signup()

        self.signup(username='player_02', nickname='다른이름')

        self.assertEqual(User.objects.filter(email=EMAIL).count(), 1)
        self.assertEqual(User.objects.get(email=EMAIL).username, 'player_02')

    def test_replacing_keeps_the_same_username_usable(self):
        self.signup()

        # 같은 사람이 비밀번호만 바꿔 다시 가입한다. 자기 아이디와 겹친다고 거부하면 안 된다
        response = self.signup(password='another-strong-pass')

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertTrue(User.objects.get(email=EMAIL).check_password('another-strong-pass'))

    def test_replacing_does_not_bypass_the_mail_limit(self):
        for index in range(4):
            self.signup(username=f'player_0{index + 2}')

        # 가입 요청을 반복해도 1분에 한 통만 나간다
        self.assertEqual(len(mail.outbox), 1)

    def test_first_code_still_works_after_a_replaced_signup(self):
        self.signup()
        code = code_from(mail.outbox[0])
        self.signup(username='player_02')

        response = self.verify(code)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(User.objects.get(username='player_02').is_email_verified)

    def test_expired_pending_account_releases_its_username(self):
        self.signup()
        self.age_pending_account('player_01', PENDING_ACCOUNT_LIFETIME + timedelta(minutes=1))

        response = self.signup(email='another@example.com', nickname='다른사람')

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(User.objects.get(username='player_01').email, 'another@example.com')
        self.assertFalse(User.objects.filter(email=EMAIL).exists())

    def test_pending_account_keeps_its_username_before_expiry(self):
        self.signup()
        self.age_pending_account('player_01', PENDING_ACCOUNT_LIFETIME - timedelta(minutes=1))

        response = self.signup(email='another@example.com', nickname='다른사람')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verified_account_is_never_replaced(self):
        self.signup_and_verify()
        self.age_pending_account('player_01', PENDING_ACCOUNT_LIFETIME * 10)

        response = self.signup(email='another@example.com', nickname='다른사람')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.get(username='player_01').email, EMAIL)


class SignupVerifyTests(SignupTestCase):
    def setUp(self):
        self.signup()
        self.code = code_from(mail.outbox[0])

    def test_marks_the_account_verified(self):
        response = self.verify(self.code)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(User.objects.get(username='player_01').is_email_verified)

    def test_email_match_ignores_case(self):
        response = self.verify(self.code, email='SOMEONE@example.com')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_rejects_wrong_code(self):
        response = self.verify(wrong_code_for(self.code))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.get(username='player_01').is_email_verified)

    def test_unknown_email_gets_the_same_response_as_a_wrong_code(self):
        wrong_code = self.verify(wrong_code_for(self.code))
        unknown_email = self.verify(self.code, email='nobody@example.com')

        self.assertEqual(unknown_email.status_code, wrong_code.status_code)
        self.assertEqual(unknown_email.data, wrong_code.data)

    def test_rejects_malformed_code(self):
        for code in ('12345', '1234567', 'abcdef', ''):
            with self.subTest(code=code):
                response = self.verify(code)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('code', response.data)

    def test_code_cannot_be_used_twice(self):
        self.verify(self.code)

        response = self.verify(self.code)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_code_stays_usable_when_marking_verified_fails(self):
        # 인증 처리가 실패하면 코드 소비도 함께 취소되어야 한다
        with patch('accounts.services._mark_email_verified', side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.verify(self.code)

        response = self.verify(self.code)

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class SignupResendTests(SignupTestCase):
    def setUp(self):
        self.signup()
        self.first_code = code_from(mail.outbox[0])
        mail.outbox.clear()

    def after_cooldown(self):
        return patch(
            'accounts.email_codes.timezone.now',
            return_value=timezone.now() + ISSUE_COOLDOWN,
        )

    def test_sends_a_new_code(self):
        with self.after_cooldown():
            response = self.resend()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)

    def test_new_code_verifies_the_account(self):
        with self.after_cooldown():
            self.resend()
            response = self.verify(code_from(mail.outbox[0]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_does_not_send_within_cooldown(self):
        response = self.resend()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_stops_sending_after_the_hourly_limit(self):
        now = timezone.now()
        for index in range(1, MAX_ISSUES_PER_WINDOW + 3):
            with patch('accounts.email_codes.timezone.now', return_value=now + ISSUE_COOLDOWN * index):
                self.resend()

        # 가입할 때 보낸 1통을 포함해 한 시간에 MAX_ISSUES_PER_WINDOW 통까지만 나간다
        self.assertEqual(len(mail.outbox), MAX_ISSUES_PER_WINDOW - 1)

    def test_unknown_and_verified_emails_get_the_same_response(self):
        pending = self.resend()
        unknown = self.resend(email='nobody@example.com')
        self.verify(self.first_code)
        verified = self.resend()

        self.assertEqual(unknown.data, pending.data)
        self.assertEqual(verified.data, pending.data)
        self.assertEqual(len(mail.outbox), 0)


class LoginRequiresVerificationTests(SignupTestCase):
    def setUp(self):
        self.signup()
        self.code = code_from(mail.outbox[0])

    def test_unverified_account_cannot_log_in(self):
        response = self.login()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'email_not_verified')
        self.assertNotIn('access_token', response.data)

    def test_wrong_password_does_not_reveal_the_unverified_account(self):
        response = self.login(password='wrong-password')

        # 비밀번호가 틀리면 계정이 있는지조차 알려 주지 않는다
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_can_log_in_after_verification(self):
        self.verify(self.code)

        response = self.login()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access_token', response.data)


class DeleteUnverifiedUsersCommandTests(SignupTestCase):
    def test_deletes_only_expired_pending_accounts(self):
        self.signup_and_verify()
        self.signup(username='expired_one', email='expired@example.com', nickname='만료된계정')
        self.signup(username='recent_one', email='recent@example.com', nickname='최근계정')
        long_ago = PENDING_ACCOUNT_LIFETIME + timedelta(minutes=1)
        self.age_pending_account('expired_one', long_ago)
        self.age_pending_account('player_01', long_ago)

        call_command('delete_unverified_users', stdout=StringIO())

        remaining = set(User.objects.values_list('username', flat=True))
        self.assertEqual(remaining, {'player_01', 'recent_one'})

    def test_deletes_the_codes_of_deleted_accounts(self):
        self.signup()
        self.age_pending_account('player_01', PENDING_ACCOUNT_LIFETIME + timedelta(minutes=1))

        call_command('delete_unverified_users', stdout=StringIO())

        self.assertEqual(EmailCode.objects.count(), 0)


class SuperuserTests(SignupTestCase):
    def test_superuser_is_verified_from_the_start(self):
        user = User.objects.create_superuser(
            username='owner_01',
            email='owner@example.com',
            nickname='주인',
            password=PASSWORD,
        )

        self.assertTrue(user.is_email_verified)
        self.assertEqual(self.login(username='owner_01').status_code, status.HTTP_200_OK)