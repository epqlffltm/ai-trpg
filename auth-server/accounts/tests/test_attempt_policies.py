# auth-server/accounts/tests/test_attempt_policies.py

"""
API 에 걸린 시도 횟수 제한을 검증한다. 실제 Redis 에서 돈다.

다른 테스트에서는 제한이 꺼져 있다. 이 파일은 켜고 돈다.
세는 방법 자체는 test_attempt_limits.py 가 검증한다. 여기는 "어느 API 가 무엇을 기준으로 막히는가" 를 본다.
IP 별 제한은 throttle(throttles.py)이, 실패 횟수 제한은 뷰가 건다. 밖에서 보이는 응답은 같아야 한다.
"""

from unittest.mock import patch

import redis
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.attempt_limits import _key
from accounts.attempt_policies import (
    LOGIN_FAILURES_PER_ACCOUNT_AND_IP,
    LOGIN_PER_IP,
    PASSWORD_CHANGE_FAILURES_PER_USER,
    PASSWORD_RESET_PER_IP,
    SIGNUP_PER_IP,
    SIGNUP_RESEND_PER_IP,
)
from accounts.models import User
from accounts.services import InvalidCredentialsError
from accounts.tests.helpers import LOGIN_URL, delete_attempt_keys, log_in
from config.redis_client import get_redis

SIGNUP_URL = reverse('accounts:signup')
SIGNUP_RESEND_URL = reverse('accounts:signup-resend')
RESET_URL = reverse('accounts:password-reset')
CHANGE_URL = reverse('accounts:password-change')

USERNAME = 'player_01'
PASSWORD = 'correct-horse-battery'
NEW_PASSWORD = 'brand-new-staple-42'
WRONG_PASSWORD = 'wrong-password-000'

IP = '203.0.113.7'
OTHER_IP = '203.0.113.8'


def create_user(**overrides) -> User:
    fields = {
        'username': USERNAME,
        'email': 'someone@example.com',
        'nickname': '플레이어',
        'password': PASSWORD,
        'email_verified_at': timezone.now(),
    }
    fields.update(overrides)
    return User.objects.create_user(**fields)


@override_settings(ATTEMPT_LIMITS_ENABLED=True, TRUSTED_PROXY_COUNT=0)
class AttemptPolicyTestCase(APITestCase):
    def setUp(self):
        delete_attempt_keys()
        self.addCleanup(delete_attempt_keys)

    def login(self, username: str = USERNAME, password: str = PASSWORD, ip: str = IP):
        return self.client.post(
            LOGIN_URL, {'username': username, 'password': password}, format='json', REMOTE_ADDR=ip,
        )

    def fail_login(self, times: int, **kwargs) -> None:
        for _ in range(times):
            response = self.login(password=WRONG_PASSWORD, **kwargs)
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def assert_too_many_attempts(self, response) -> None:
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data['code'], 'too_many_attempts')
        self.assertGreaterEqual(response.data['retry_after'], 1)
        self.assertEqual(response['Retry-After'], str(response.data['retry_after']))


class LoginFailureLimitTests(AttemptPolicyTestCase):
    """한 IP 가 한 계정의 비밀번호를 틀린 횟수."""

    def setUp(self):
        super().setUp()
        create_user()

    def test_blocks_after_too_many_wrong_passwords(self):
        self.fail_login(LOGIN_FAILURES_PER_ACCOUNT_AND_IP.max_attempts)

        self.assert_too_many_attempts(self.login(password=WRONG_PASSWORD))

    def test_does_not_check_even_the_right_password_while_blocked(self):
        self.fail_login(LOGIN_FAILURES_PER_ACCOUNT_AND_IP.max_attempts)

        # 맞는 비밀번호에 다른 응답을 주면, 막힌 동안에도 계속 맞혀 볼 수 있다
        self.assert_too_many_attempts(self.login())
        self.assertEqual(len(mail.outbox), 0)

    def test_tells_how_long_to_wait(self):
        self.fail_login(LOGIN_FAILURES_PER_ACCOUNT_AND_IP.max_attempts)

        response = self.login()

        window_seconds = LOGIN_FAILURES_PER_ACCOUNT_AND_IP.window.total_seconds()
        self.assertLessEqual(response.data['retry_after'], window_seconds)
        self.assertGreater(response.data['retry_after'], window_seconds - 60)

    def test_does_not_lock_the_owner_out_from_another_ip(self):
        self.fail_login(LOGIN_FAILURES_PER_ACCOUNT_AND_IP.max_attempts)

        # 남이 일부러 틀려도, 다른 곳에 있는 주인은 로그인할 수 있다
        response = self.login(ip=OTHER_IP)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def test_does_not_block_other_accounts_from_the_same_ip(self):
        create_user(username='player_02', email='other@example.com', nickname='다른사람')
        self.fail_login(LOGIN_FAILURES_PER_ACCOUNT_AND_IP.max_attempts)

        response = self.login(username='player_02')

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def test_counts_unknown_usernames_the_same_way(self):
        self.fail_login(LOGIN_FAILURES_PER_ACCOUNT_AND_IP.max_attempts, username='nobody_here')

        # 없는 아이디만 안 막히면, 막히는지 여부로 가입 여부가 드러난다
        self.assert_too_many_attempts(self.login(username='nobody_here', password=WRONG_PASSWORD))

    def test_counts_the_same_username_written_differently_together(self):
        self.fail_login(LOGIN_FAILURES_PER_ACCOUNT_AND_IP.max_attempts, username=USERNAME.upper())

        self.assert_too_many_attempts(self.login())

    def test_right_password_clears_the_failures(self):
        self.fail_login(LOGIN_FAILURES_PER_ACCOUNT_AND_IP.max_attempts - 1)
        self.assertEqual(self.login().status_code, status.HTTP_202_ACCEPTED)

        # 지워지지 않았다면 여기서 한 번만 틀려도 막힌다
        self.fail_login(LOGIN_FAILURES_PER_ACCOUNT_AND_IP.max_attempts - 1)

        self.assertEqual(self.login().status_code, status.HTTP_202_ACCEPTED)


    def test_counts_before_checking_the_password(self):
        counts_seen = []

        def check_password_and_look_at_the_counter(**credentials):
            key = _key(LOGIN_FAILURES_PER_ACCOUNT_AND_IP, f'{USERNAME}|{IP}')
            counts_seen.append(int(get_redis().get(key) or 0))
            raise InvalidCredentialsError

        with patch('accounts.views.start_login', side_effect=check_password_and_look_at_the_counter):
            self.login(password=WRONG_PASSWORD)
            self.login(password=WRONG_PASSWORD)

        # 확인한 뒤에 세면, 동시에 들어온 요청들이 전부 "아직 한도 전" 을 보고 통과한다.
        # 먼저 세면 요청마다 다른 횟수를 받으므로 한도까지만 통과한다
        self.assertEqual(counts_seen, [1, 2])

    def test_right_password_of_an_unverified_account_is_not_a_failure(self):
        create_user(username='pending_01', email='pending@example.com', nickname='대기중', email_verified_at=None)

        for _ in range(LOGIN_FAILURES_PER_ACCOUNT_AND_IP.max_attempts + 1):
            response = self.login(username='pending_01')

            # 비밀번호는 맞았다. 이메일 인증을 끝내지 않았을 뿐이다
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class LoginIpLimitTests(AttemptPolicyTestCase):
    """한 IP 의 로그인 시도 전체."""

    def try_many_accounts(self, times: int, ip: str = IP) -> None:
        # 계정마다 한 번씩만 틀려서, 계정별 제한에는 걸리지 않게 한다
        for number in range(times):
            response = self.login(username=f'guess_{number}', password=WRONG_PASSWORD, ip=ip)
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_blocks_an_ip_that_tries_many_accounts(self):
        self.try_many_accounts(LOGIN_PER_IP.max_attempts)

        self.assert_too_many_attempts(self.login(username='guess_more', password=WRONG_PASSWORD))

    def test_blocks_even_the_right_password_from_that_ip(self):
        create_user()
        self.try_many_accounts(LOGIN_PER_IP.max_attempts)

        self.assert_too_many_attempts(self.login())

    def test_does_not_block_other_ips(self):
        create_user()
        self.try_many_accounts(LOGIN_PER_IP.max_attempts)

        response = self.login(ip=OTHER_IP)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def test_successful_logins_are_counted_too(self):
        create_user()
        self.try_many_accounts(LOGIN_PER_IP.max_attempts - 1)
        self.assertEqual(self.login().status_code, status.HTTP_202_ACCEPTED)

        # 성공이 횟수를 지우면, 자기 계정으로 한 번씩 로그인해 가며 제한을 피할 수 있다
        self.assert_too_many_attempts(self.login())


class SignupLimitTests(AttemptPolicyTestCase):
    def signup(self, number: int, ip: str = IP):
        body = {
            'username': f'newbie_{number}',
            'email': f'newbie{number}@example.com',
            'nickname': f'새사람{number}',
            'password': PASSWORD,
        }
        return self.client.post(SIGNUP_URL, body, format='json', REMOTE_ADDR=ip)

    def test_blocks_an_ip_that_signs_up_too_often(self):
        for number in range(SIGNUP_PER_IP.max_attempts):
            self.assertEqual(self.signup(number).status_code, status.HTTP_202_ACCEPTED)
        mail.outbox.clear()

        response = self.signup(999)

        self.assert_too_many_attempts(response)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(User.objects.filter(username='newbie_999').exists())

    def test_counts_requests_that_fail_validation_too(self):
        # throttle 은 본문을 검증하기 전에 센다. 잘못된 요청을 쏟아붓는 것도 묶인다
        for _ in range(SIGNUP_PER_IP.max_attempts):
            response = self.client.post(SIGNUP_URL, {}, format='json', REMOTE_ADDR=IP)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.assert_too_many_attempts(self.signup(999))

    def test_does_not_block_other_ips(self):
        for number in range(SIGNUP_PER_IP.max_attempts):
            self.signup(number)

        response = self.signup(999, ip=OTHER_IP)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def test_blocks_an_ip_that_asks_to_resend_too_often(self):
        for number in range(SIGNUP_RESEND_PER_IP.max_attempts):
            response = self.client.post(
                SIGNUP_RESEND_URL, {'email': f'anyone{number}@example.com'}, format='json', REMOTE_ADDR=IP,
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(
            SIGNUP_RESEND_URL, {'email': 'anyone@example.com'}, format='json', REMOTE_ADDR=IP,
        )

        self.assert_too_many_attempts(response)


class PasswordResetLimitTests(AttemptPolicyTestCase):
    def request_reset(self, email: str, ip: str = IP):
        return self.client.post(RESET_URL, {'email': email}, format='json', REMOTE_ADDR=ip)

    def test_blocks_an_ip_that_asks_too_often(self):
        create_user()
        for number in range(PASSWORD_RESET_PER_IP.max_attempts):
            response = self.request_reset(f'anyone{number}@example.com')
            self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        response = self.request_reset('someone@example.com')

        self.assert_too_many_attempts(response)
        self.assertEqual(len(mail.outbox), 0)

    def test_does_not_block_other_ips(self):
        create_user()
        for number in range(PASSWORD_RESET_PER_IP.max_attempts):
            self.request_reset(f'anyone{number}@example.com')

        response = self.request_reset('someone@example.com', ip=OTHER_IP)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(len(mail.outbox), 1)


class PasswordChangeLimitTests(AttemptPolicyTestCase):
    """한 사용자가 현재 비밀번호를 틀린 횟수. IP 가 아니라 사용자로 센다."""

    def setUp(self):
        super().setUp()
        self.user = create_user()
        access_token = log_in(self.client, USERNAME, PASSWORD).data['access_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

    def change(self, current_password: str, ip: str = IP):
        body = {'current_password': current_password, 'new_password': NEW_PASSWORD}
        return self.client.post(CHANGE_URL, body, format='json', REMOTE_ADDR=ip)

    def fail_change(self, times: int) -> None:
        for _ in range(times):
            self.assertEqual(self.change(WRONG_PASSWORD).status_code, status.HTTP_400_BAD_REQUEST)

    def test_blocks_after_too_many_wrong_current_passwords(self):
        self.fail_change(PASSWORD_CHANGE_FAILURES_PER_USER.max_attempts)

        self.assert_too_many_attempts(self.change(PASSWORD))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_changing_the_ip_does_not_help(self):
        self.fail_change(PASSWORD_CHANGE_FAILURES_PER_USER.max_attempts)

        self.assert_too_many_attempts(self.change(PASSWORD, ip=OTHER_IP))

    def test_right_current_password_clears_the_failures(self):
        self.fail_change(PASSWORD_CHANGE_FAILURES_PER_USER.max_attempts - 1)

        response = self.change(PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {response.data["access_token"]}')
        # 지워지지 않았다면 여기서 한 번만 틀려도 막힌다
        self.fail_change(PASSWORD_CHANGE_FAILURES_PER_USER.max_attempts - 1)


    def test_rejected_new_password_is_not_a_failure(self):
        for _ in range(PASSWORD_CHANGE_FAILURES_PER_USER.max_attempts + 1):
            # 현재 비밀번호는 맞다. 새 비밀번호가 현재와 같아서 거절된다
            response = self.client.post(
                CHANGE_URL, {'current_password': PASSWORD, 'new_password': PASSWORD}, format='json',
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('new_password', response.data)


class RedisDownTests(AttemptPolicyTestCase):
    """Redis 가 죽어도 로그인은 된다. 제한만 사라진다."""

    def test_login_still_works(self):
        create_user()

        with patch('accounts.attempt_limits.get_redis', side_effect=redis.ConnectionError('down')):
            with self.assertLogs('accounts.attempt_limits', level='WARNING'):
                wrong = self.login(password=WRONG_PASSWORD)
                right = self.login()

        self.assertEqual(wrong.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(right.status_code, status.HTTP_202_ACCEPTED)
