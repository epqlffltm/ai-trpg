# auth-server/accounts/tests/test_signup.py

"""
회원가입을 검증한다. 가입은 세 단계다(#271).

    1. signup           이메일 → 코드 메일(이미 가입된 주소면 안내 메일)
    2. signup/verify    이메일과 코드 → 가입 티켓
    3. signup/complete  티켓과 아이디, 닉네임, 비밀번호, 만 14세 이상 확인 → 인증된 계정

실제 URL 로 요청을 보내 뷰, Serializer, service, DB 를 한 번에 거친다.
두 연결이 엇갈리는 경우는 맨 아래의 TransactionTestCase 가 진짜 트랜잭션 둘로 본다.
"""

import threading
import time
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.db import IntegrityError, connection
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.email_codes import ISSUE_COOLDOWN, MAX_FAILED_ATTEMPTS, MAX_ISSUES_PER_WINDOW
from accounts.login_tickets import issue_login_ticket
from accounts.models import EmailCode, SignupCode, User, WelcomeCredit
from accounts.services import (
    STALE_SIGNUP_CODE_AGE,
    DuplicateAccountError,
    EmailAlreadyRegisteredError,
    complete_signup,
    start_signup,
    verify_signup,
)
from accounts.signup_tickets import SIGNUP_TICKET_LIFETIME, issue_signup_ticket
from accounts.tests.helpers import code_from, required_consents, wrong_code_for

SIGNUP_URL = reverse('accounts:signup')
VERIFY_URL = reverse('accounts:signup-verify')
COMPLETE_URL = reverse('accounts:signup-complete')
LOGIN_URL = reverse('accounts:login')

PASSWORD = 'correct-horse-battery'
EMAIL = 'someone@example.com'


def account(**overrides) -> dict:
    """가입 내용(3단계). 테스트마다 달라지는 값만 넘기고 나머지는 기본값을 쓴다."""
    payload = {
        'username': 'player_01',
        'nickname': '플레이어',
        'password': PASSWORD,
        'age_over_14': True,
        'consents': required_consents(),
    }
    payload.update(overrides)
    return payload


def after_cooldown():
    """직전 발급의 대기 시간이 지난 시점으로 옮긴다."""
    return patch('accounts.email_codes.timezone.now', return_value=timezone.now() + ISSUE_COOLDOWN)


class SignupTestCase(APITestCase):
    def start(self, email: str = EMAIL):
        return self.client.post(SIGNUP_URL, {'email': email}, format='json')

    def verify(self, code: str, email: str = EMAIL):
        return self.client.post(VERIFY_URL, {'email': email, 'code': code}, format='json')

    def complete(self, ticket: str, **overrides):
        return self.client.post(COMPLETE_URL, {'signup_ticket': ticket, **account(**overrides)}, format='json')

    def ticket_for(self, email: str = EMAIL) -> str:
        """1, 2단계를 지나 가입 티켓을 받는다."""
        self.start(email)
        response = self.verify(code_from(mail.outbox[-1]), email=email)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data['signup_ticket']

    def sign_up(self, email: str = EMAIL, **overrides) -> User:
        """세 단계를 모두 지난 계정을 만든다."""
        response = self.complete(self.ticket_for(email), **overrides)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return User.objects.get(username=account(**overrides)['username'])

    def login(self, username: str = 'player_01', password: str = PASSWORD):
        """로그인의 1단계만 보낸다."""
        return self.client.post(LOGIN_URL, {'username': username, 'password': password}, format='json')


class SignupStartTests(SignupTestCase):
    def test_returns_202_with_only_a_message(self):
        response = self.start()

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(set(response.data), {'detail'})

    def test_creates_no_account(self):
        # 계정은 이메일의 주인이 코드를 맞힌 뒤에 생긴다(#271)
        self.start()

        self.assertEqual(User.objects.count(), 0)

    def test_sends_a_code_to_the_email(self):
        self.start()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [EMAIL])
        self.assertRegex(code_from(mail.outbox[0]), r'^\d{6}$')

    def test_the_code_mail_names_no_account(self):
        # 가입 내용은 코드를 맞힌 뒤에 정한다. 메일에는 아이디가 없다
        self.start()

        self.assertNotIn('player_01', mail.outbox[0].body)

    def test_the_code_row_keeps_the_email_in_lowercase(self):
        self.start(email='Someone@Example.com')

        self.assertEqual(SignupCode.objects.get().email, EMAIL)
        self.assertEqual(mail.outbox[0].to, [EMAIL])

    def test_ignores_account_fields_in_the_body(self):
        body = {'email': EMAIL, **account(), 'is_staff': True}
        response = self.client.post(SIGNUP_URL, body, format='json')

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(User.objects.count(), 0)

    def test_rejects_an_invalid_email(self):
        response = self.start(email='not-an-email')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)
        self.assertEqual(len(mail.outbox), 0)

    def test_get_is_not_allowed(self):
        response = self.client.get(SIGNUP_URL)

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class SignupResendTests(SignupTestCase):
    """다시 보내기는 1단계를 다시 부르는 것이다. 코드는 늘 하나만 쓸 수 있다."""

    def setUp(self):
        self.start()
        self.first_code = code_from(mail.outbox[0])
        mail.outbox.clear()

    def test_does_not_send_within_the_cooldown(self):
        response = self.start()

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(len(mail.outbox), 0)

    def test_the_first_code_still_works_within_the_cooldown(self):
        self.start()

        response = self.verify(self.first_code)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_sends_a_new_code_after_the_cooldown(self):
        with after_cooldown():
            self.start()

        self.assertEqual(len(mail.outbox), 1)

    def test_the_new_code_replaces_the_first(self):
        with after_cooldown():
            self.start()
            new_code = code_from(mail.outbox[0])
            if new_code == self.first_code:
                self.skipTest('두 코드가 우연히 같다')
            old = self.verify(self.first_code)
            new = self.verify(new_code)

        self.assertEqual(old.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(new.status_code, status.HTTP_200_OK)

    def test_stops_sending_after_the_hourly_limit(self):
        now = timezone.now()
        for index in range(1, MAX_ISSUES_PER_WINDOW + 3):
            with patch('accounts.email_codes.timezone.now', return_value=now + ISSUE_COOLDOWN * index):
                self.start()

        # 처음 보낸 1통을 포함해 한 시간에 MAX_ISSUES_PER_WINDOW 통까지만 나간다
        self.assertEqual(len(mail.outbox), MAX_ISSUES_PER_WINDOW - 1)


class SignupRegisteredEmailTests(SignupTestCase):
    """이미 가입된 이메일로 1단계를 부르는 경우. 응답으로는 그 사실이 드러나지 않아야 한다."""

    def setUp(self):
        self.user = self.sign_up()
        mail.outbox.clear()

    def test_response_is_identical_to_a_new_email(self):
        new_email = self.start(email='fresh@example.com')
        registered = self.start()

        self.assertEqual(registered.status_code, new_email.status_code)
        self.assertEqual(registered.data, new_email.data)

    def test_notifies_the_owner_instead_of_sending_a_code(self):
        # 코드를 맞히면 대기 시간이 풀린다. 가입을 마친 직후에도 안내 메일이 바로 나간다
        self.start()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [EMAIL])
        self.assertIn('이미 가입', mail.outbox[0].subject)
        self.assertNotRegex(mail.outbox[0].body, r'\b\d{6}\b')

    def test_email_match_ignores_case(self):
        self.start(email='SOMEONE@example.com')

        self.assertIn('이미 가입', mail.outbox[0].subject)

    def test_notices_share_the_limit_of_the_code(self):
        for _ in range(3):
            self.start()

        # 가입 요청을 반복해 남의 메일함에 안내 메일을 쏟아부을 수 없어야 한다
        self.assertEqual(len(mail.outbox), 1)

    def test_no_code_can_verify_a_registered_email(self):
        self.start()

        for code in ('000000', '123456', '999999'):
            with self.subTest(code=code):
                self.assertEqual(self.verify(code).status_code, status.HTTP_400_BAD_REQUEST)

    def test_does_not_change_the_existing_account(self):
        self.start()

        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'player_01')
        self.assertTrue(self.user.check_password(PASSWORD))


class SignupVerifyTests(SignupTestCase):
    def setUp(self):
        self.start()
        self.code = code_from(mail.outbox[0])

    def test_gives_a_ticket_and_creates_no_account(self):
        response = self.verify(self.code)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {'detail', 'signup_ticket'})
        self.assertEqual(User.objects.count(), 0)

    def test_email_match_ignores_case(self):
        response = self.verify(self.code, email='SOMEONE@example.com')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_rejects_a_wrong_code(self):
        response = self.verify(wrong_code_for(self.code))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn('signup_ticket', response.data)

    def test_unknown_email_gets_the_same_response_as_a_wrong_code(self):
        wrong_code = self.verify(wrong_code_for(self.code))
        unknown_email = self.verify(self.code, email='nobody@example.com')

        self.assertEqual(unknown_email.status_code, wrong_code.status_code)
        self.assertEqual(unknown_email.data, wrong_code.data)

    def test_the_code_of_one_email_does_not_verify_another(self):
        self.start(email='other@example.com')

        response = self.verify(self.code, email='other@example.com')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_a_malformed_code(self):
        for code in ('12345', '1234567', 'abcdef', ''):
            with self.subTest(code=code):
                response = self.verify(code)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('code', response.data)

    def test_the_code_cannot_be_used_twice(self):
        self.verify(self.code)

        response = self.verify(self.code)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_too_many_wrong_codes_discard_the_right_one(self):
        for _ in range(MAX_FAILED_ATTEMPTS):
            self.verify(wrong_code_for(self.code))

        response = self.verify(self.code)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class SignupCompleteTests(SignupTestCase):
    def setUp(self):
        self.ticket = self.ticket_for()

    def test_creates_a_verified_account_with_the_ticket_email(self):
        response = self.complete(self.ticket)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(set(response.data), {'detail'})
        user = User.objects.get(username='player_01')
        self.assertEqual(user.email, EMAIL)
        self.assertEqual(user.nickname, '플레이어')
        self.assertTrue(user.is_email_verified)

    def test_the_password_is_stored_hashed(self):
        self.complete(self.ticket)

        user = User.objects.get(username='player_01')
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))

    def test_the_new_account_can_start_logging_in(self):
        self.complete(self.ticket)

        response = self.login()

        # 로그인의 1단계를 통과한다. 토큰은 2단계에서 나온다(test_login.py)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn('login_ticket', response.data)

    def test_the_new_account_has_no_admin_rights(self):
        # 요청 본문에 권한 필드나 다른 이메일을 끼워 넣어도 무시되어야 한다
        self.complete(self.ticket, is_staff=True, is_superuser=True, email='other@example.com')

        user = User.objects.get(username='player_01')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.email, EMAIL)

    def test_the_ticket_cannot_be_used_twice(self):
        self.complete(self.ticket)

        response = self.complete(self.ticket, username='player_02', nickname='다른사람')

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'email_registered')
        self.assertEqual(User.objects.count(), 1)

    def test_rejects_a_forged_ticket(self):
        response = self.complete(self.ticket[:-2] + 'xx')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'signup_ticket_invalid')
        self.assertEqual(User.objects.count(), 0)

    def test_rejects_an_expired_ticket(self):
        later = time.time() + SIGNUP_TICKET_LIFETIME.total_seconds() + 60
        with patch('django.core.signing.time.time', return_value=later):
            response = self.complete(self.ticket)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'signup_ticket_invalid')

    def test_a_login_ticket_is_not_a_signup_ticket(self):
        # 같은 비밀키로 서명했어도 용도가 다르면 받지 않는다
        owner = User.objects.create_superuser(
            username='owner_01', email='owner@example.com', nickname='주인', password=PASSWORD
        )

        response = self.complete(issue_login_ticket(owner))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'signup_ticket_invalid')

    def test_a_missing_ticket_is_a_field_error(self):
        payload = account()
        response = self.client.post(COMPLETE_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('signup_ticket', response.data)

    def test_signing_up_queues_no_welcome_credit(self):
        # 환영 크레딧은 본인인증 때 적는다(#336). 이메일은 얼마든지 만들 수 있다
        self.assertEqual(self.complete(self.ticket).status_code, status.HTTP_201_CREATED)

        self.assertEqual(WelcomeCredit.objects.count(), 0)

    def test_returns_409_when_the_database_rejects_a_duplicate(self):
        # 동시 요청으로 사전 조회를 둘 다 통과한 상황을 흉내 낸다
        with patch.object(User, 'save', side_effect=IntegrityError):
            response = self.complete(self.ticket)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(User.objects.count(), 0)


class SignupCompleteValidationTests(SignupTestCase):
    def setUp(self):
        self.ticket = self.ticket_for()

    def assert_rejected(self, field: str, **overrides) -> None:
        """400 으로 거부되고, 오류가 해당 필드에 달려 있고, 계정이 생기지 않았는지 확인한다."""
        response = self.complete(self.ticket, **overrides)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(field, response.data)
        self.assertEqual(User.objects.count(), 0)

    def test_rejects_an_uppercase_username(self):
        self.assert_rejected('username', username='Player_01')

    def test_rejects_a_reserved_username(self):
        self.assert_rejected('username', username='admin')

    def test_rejects_a_numbered_reserved_username(self):
        self.assert_rejected('username', username='admin1')
        self.assert_rejected('username', username='root_2')

    def test_rejects_a_username_equal_to_the_email_local_part(self):
        # 티켓 속의 이메일과 견준다
        self.assert_rejected('username', username='someone')

    def test_rejects_reserved_nicknames(self):
        self.assert_rejected('nickname', nickname='운영자')
        self.assert_rejected('nickname', nickname='GM')
        self.assert_rejected('nickname', nickname='운영자1')

    def test_rejects_a_nickname_with_spaces(self):
        self.assert_rejected('nickname', nickname='운 영 자')

    def test_rejects_weak_passwords(self):
        weak_passwords = [
            'short1!',  # 8자 미만
            '1234567890',  # 숫자만
            'password123',  # 흔한 비밀번호
            'player_01',  # 아이디와 같음
            'someone@example.com',  # 티켓 속의 이메일과 같음
        ]
        for password in weak_passwords:
            with self.subTest(password=password):
                self.assert_rejected('password', password=password)

    def test_rejects_a_missing_field(self):
        payload = {'signup_ticket': self.ticket, **account()}
        del payload['nickname']

        response = self.client.post(COMPLETE_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('nickname', response.data)

    def test_rejects_an_account_without_the_age_confirmation(self):
        # 만 14세 미만은 받지 않는다. 자기 신고라 실제 나이는 본인인증에서 다시 본다(#336)
        self.assert_rejected('age_over_14', age_over_14=False)

        payload = {'signup_ticket': self.ticket, **account()}
        del payload['age_over_14']
        response = self.client.post(COMPLETE_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('age_over_14', response.data)
        self.assertEqual(User.objects.count(), 0)

    def test_a_rejected_attempt_keeps_the_ticket_usable(self):
        self.complete(self.ticket, password='short1!')

        response = self.complete(self.ticket)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class SignupTakenTests(SignupTestCase):
    """아이디와 닉네임의 중복. 이것은 숨기지 않는다. 다른 값을 골라야 하기 때문이다."""

    def setUp(self):
        self.sign_up()
        self.ticket = self.ticket_for('another@example.com')

    def test_rejects_a_taken_username(self):
        response = self.complete(self.ticket, nickname='다른사람')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data)

    def test_rejects_a_taken_nickname(self):
        response = self.complete(self.ticket, username='player_02')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('nickname', response.data)

    def test_starting_a_signup_holds_no_username(self):
        # 1, 2단계만 지난 이메일은 아이디를 붙잡지 않는다. 옛 흐름의 "미인증 계정의 선점"이 없다
        self.ticket_for('third@example.com')

        response = self.complete(self.ticket, username='player_02', nickname='다른사람')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class SomeoneElseStartsTheSameEmailTests(SignupTestCase):
    """
    #271: 남이 내 이메일로 가입을 시작해도 내 코드로 남의 가입 내용이 확정되지 않는다.

    옛 흐름은 이메일을 확인하기 전에 계정(가입 내용)을 만들어, 같은 이메일로 다시 가입하면 그 내용을 고쳐 썼다.
    지금은 가입 내용을 코드를 맞힌 사람만 정한다.
    """

    def setUp(self):
        self.start()
        self.code = code_from(mail.outbox[-1])

    def test_starting_again_changes_nothing_the_owner_has(self):
        # 남이 같은 이메일로 1단계를 다시 부른다. 보낼 수 있는 것은 이메일뿐이다
        self.start()

        response = self.verify(self.code)
        created = self.complete(response.data['signup_ticket'])

        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email=EMAIL)
        self.assertEqual(user.username, 'player_01')
        self.assertTrue(user.check_password(PASSWORD))

    def test_without_the_code_no_ticket_can_be_made(self):
        # 코드를 모르는 사람은 다섯 번 안에 맞혀야 한다. 틀리면 그 코드는 버려진다
        for _ in range(MAX_FAILED_ATTEMPTS):
            self.verify(wrong_code_for(self.code))

        self.assertEqual(self.verify(self.code).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.count(), 0)


class DeleteUnverifiedUsersCommandTests(SignupTestCase):
    """정리 명령. 미인증 계정은 더 생기지 않아, 오래된 가입 코드의 행을 지운다."""

    def age_signup_code(self, email: str, age: timedelta) -> None:
        SignupCode.objects.filter(email=email).update(last_issued_at=timezone.now() - age)

    def test_deletes_only_stale_signup_codes(self):
        self.start(email='stale@example.com')
        self.start(email='recent@example.com')
        self.age_signup_code('stale@example.com', STALE_SIGNUP_CODE_AGE + timedelta(minutes=1))

        call_command('delete_unverified_users', stdout=StringIO())

        self.assertEqual(set(SignupCode.objects.values_list('email', flat=True)), {'recent@example.com'})

    def test_leaves_accounts_alone(self):
        self.sign_up()
        self.age_signup_code(EMAIL, STALE_SIGNUP_CODE_AGE * 10)

        call_command('delete_unverified_users', stdout=StringIO())

        self.assertTrue(User.objects.filter(username='player_01').exists())
        self.assertEqual(SignupCode.objects.count(), 0)


class SuperuserTests(SignupTestCase):
    def test_superuser_is_verified_from_the_start(self):
        user = User.objects.create_superuser(
            username='owner_01',
            email='owner@example.com',
            nickname='주인',
            password=PASSWORD,
        )

        self.assertTrue(user.is_email_verified)
        self.assertEqual(self.login(username='owner_01').status_code, status.HTTP_202_ACCEPTED)

    def test_signup_writes_no_member_email_code(self):
        # 가입 코드는 이메일의 행(SignupCode)에 있다. 회원의 인증 코드(EmailCode)에는 생기지 않는다
        self.sign_up()

        self.assertEqual(EmailCode.objects.count(), 0)


class TwoConnectionsTests(TransactionTestCase):
    """
    두 요청이 진짜 트랜잭션 둘로 엇갈리는 경우(#271). 테스트를 트랜잭션으로 감싸지 않는 종류를 쓴다.

    가입 흐름에는 고쳐 쓰는 미인증 계정이 없다. 남는 경합은 같은 코드나 같은 티켓을 동시에 쓰는 것뿐이고,
    코드는 행 잠금이, 티켓은 이메일의 유일 제약이 하나만 통과시킨다.
    """

    def run_twice_at_once(self, work) -> list[str]:
        """work 를 두 스레드에서 동시에 돌리고 결과(성공이면 'ok', 아니면 예외의 이름)를 모은다."""
        barrier = threading.Barrier(2)
        results: list[str] = []

        def run(index: int) -> None:
            try:
                barrier.wait(timeout=10)
                work(index)
                results.append('ok')
            except Exception as exc:  # 어떤 예외였는지를 결과로 모은다
                results.append(type(exc).__name__)
            finally:
                connection.close()

        threads = [threading.Thread(target=run, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        return sorted(results)

    def test_the_same_code_twice_at_once_gives_one_ticket(self):
        start_signup(email=EMAIL)
        code = code_from(mail.outbox[-1])

        results = self.run_twice_at_once(lambda _: verify_signup(email=EMAIL, code=code))

        self.assertEqual(results, ['InvalidEmailCodeError', 'ok'])

    def test_the_same_ticket_twice_at_once_makes_one_account(self):
        ticket = issue_signup_ticket(EMAIL)

        def complete(index: int) -> None:
            # 아이디와 닉네임은 다르게 한다. 이메일 하나만 겹친다
            complete_signup(
                signup_ticket=ticket,
                username=f'player_0{index + 1}',
                nickname=f'플레이어{index + 1}',
                password=PASSWORD,
                consents=required_consents(),
            )

        results = self.run_twice_at_once(complete)

        self.assertEqual(results[1], 'ok')
        self.assertIn(results[0], {DuplicateAccountError.__name__, EmailAlreadyRegisteredError.__name__})
        self.assertEqual(User.objects.filter(email=EMAIL).count(), 1)
