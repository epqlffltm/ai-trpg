# auth-server/accounts/tests/test_step_up.py

"""
민감한 작업 앞의 본인 확인(F5, accounts/step_up.py, accounts/step_up_views.py).

  - 토큰의 세션 이름(sid): 로그인마다 새로 짓고, 갱신해도 물려주고, 없는 옛 토큰은 갱신할 때 새로 짓는다
  - 창의 규칙: 확인하면 10분, 민감한 작업마다 다시 10분, 확인한 때에서 1시간이 상한, 세션마다 따로
  - 주소: 코드 보내기, 코드로 열기, 이 세션의 창 보기, 켜고 끄기(끄는 것은 창이 열린 동안만), 결제 서버의 묻기(서명)
"""

import json
import time
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import UntypedToken

from accounts.email_codes import issue_email_code
from accounts.models import EmailCodePurpose, StepUpWindow, TokenClient, User
from accounts.service_signature import SIGNATURE_HEADER, sign_request
from accounts.step_up import (
    STEP_UP_CAP,
    STEP_UP_WINDOW,
    StepUpRequiredError,
    StepUpState,
    check_step_up,
    set_step_up_enabled,
    verify_step_up,
    window_status,
)
from accounts.tests.helpers import code_from, wrong_code_for
from accounts.tokens import SESSION_CLAIM, issue_token_pair, rotate_refresh_token

STEP_UP_URL = reverse('accounts:my-step-up')
CODE_URL = reverse('accounts:my-step-up-code')
SETTING_URL = reverse('accounts:my-step-up-setting')
CHECK_URL = reverse('accounts:service-step-up-check')
SECRET = 'billing-secret-for-tests-0123456789abcdef'


def make_user(username: str = 'player_01', email: str = 'player1@example.com') -> User:
    return User.objects.create_user(
        username=username,
        email=email,
        nickname=f'플레이어{username[-1]}',
        password='correct-horse-battery',
        email_verified_at=timezone.now(),
    )


def session_of(raw_token: str) -> str:
    return UntypedToken(raw_token)[SESSION_CLAIM]


class SessionClaimTests(TestCase):
    """토큰의 세션 이름."""

    def setUp(self):
        self.user = make_user()

    def test_a_login_gets_a_new_session_shared_by_its_two_tokens(self):
        first = issue_token_pair(self.user)
        second = issue_token_pair(self.user)

        self.assertEqual(session_of(first.access), session_of(first.refresh))
        self.assertNotEqual(session_of(first.access), session_of(second.access))
        self.assertEqual(len(session_of(first.access)), 32)

    def test_refreshing_keeps_the_session(self):
        pair = issue_token_pair(self.user)

        rotated = rotate_refresh_token(pair.refresh, TokenClient.WEB)

        self.assertEqual(session_of(rotated.access), session_of(pair.access))
        self.assertEqual(session_of(rotated.refresh), session_of(pair.refresh))

    def test_an_old_token_without_a_session_gets_one_when_refreshed(self):
        with patch('accounts.tokens.new_session_id', return_value=''):
            old = issue_token_pair(self.user)

        rotated = rotate_refresh_token(old.refresh, TokenClient.WEB)

        self.assertEqual(session_of(old.refresh), '')
        self.assertEqual(len(session_of(rotated.access)), 32)


class WindowRuleTests(TestCase):
    """창의 규칙. 시각을 넘겨 준다."""

    def setUp(self):
        self.user = make_user()
        self.now = timezone.now()

    def open_window(self, session_id: str = 's1', at=None):
        at = at or self.now
        code = issue_email_code(user=self.user, purpose=EmailCodePurpose.STEP_UP)
        return verify_step_up(self.user, session_id, code, at)

    def test_verifying_opens_the_session_for_ten_minutes(self):
        expires_at = self.open_window()

        self.assertEqual(expires_at, self.now + STEP_UP_WINDOW)
        self.assertTrue(window_status(self.user, 's1', self.now).open)
        self.assertFalse(window_status(self.user, 's2', self.now).open)
        self.assertFalse(window_status(self.user, 's1', expires_at).open)

    def test_a_sensitive_action_extends_the_window_by_ten_minutes(self):
        self.open_window()
        later = self.now + timedelta(minutes=8)

        state, expires_at = check_step_up(self.user, 's1', later)

        self.assertEqual(state, StepUpState.OPEN)
        self.assertEqual(expires_at, later + STEP_UP_WINDOW)

    def test_extending_stops_an_hour_after_the_real_check(self):
        self.open_window()
        at = self.now
        for _ in range(7):
            at += timedelta(minutes=9)
            state, _expires = check_step_up(self.user, 's1', at)
            if state != StepUpState.OPEN:
                break

        self.assertEqual(state, StepUpState.REQUIRED)
        self.assertEqual(StepUpWindow.objects.get(user=self.user).expires_at, self.now + STEP_UP_CAP)

    def test_a_closed_or_missing_window_requires_a_check(self):
        self.assertEqual(check_step_up(self.user, 's1', self.now), (StepUpState.REQUIRED, None))
        self.open_window()

        self.assertEqual(check_step_up(self.user, 's1', self.now + STEP_UP_WINDOW)[0], StepUpState.REQUIRED)

    def test_a_disabled_user_is_never_asked(self):
        self.user.step_up_disabled = True
        self.user.save(update_fields=['step_up_disabled'])

        self.assertEqual(check_step_up(self.user, 's1', self.now), (StepUpState.DISABLED, None))

    def test_turning_it_off_needs_an_open_window(self):
        with self.assertRaises(StepUpRequiredError):
            set_step_up_enabled(self.user, 's1', False, self.now)
        self.open_window()

        set_step_up_enabled(self.user, 's1', False, self.now)
        self.user.refresh_from_db()
        self.assertTrue(self.user.step_up_disabled)

        set_step_up_enabled(self.user, 's2', True, self.now)
        self.user.refresh_from_db()
        self.assertFalse(self.user.step_up_disabled)

    def test_verifying_clears_windows_past_their_cap(self):
        self.open_window('old', at=self.now - STEP_UP_CAP - timedelta(minutes=1))

        self.open_window('new')

        self.assertEqual(list(StepUpWindow.objects.values_list('session_id', flat=True)), ['new'])


class MyStepUpViewTests(TestCase):
    """사용자의 주소."""

    def setUp(self):
        self.user = make_user()
        self.client = APIClient()
        self.pair = issue_token_pair(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.pair.access}')
        mail.outbox.clear()

    def send_and_read_code(self) -> str:
        response = self.client.post(CODE_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return code_from(mail.outbox[-1])

    def test_the_code_goes_to_the_account_email_and_opens_this_session(self):
        code = self.send_and_read_code()

        response = self.client.post(STEP_UP_URL, {'code': code}, format='json')

        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn('본인 확인', mail.outbox[0].subject)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['open'])
        self.assertTrue(response.data['enabled'])
        window = StepUpWindow.objects.get(user=self.user)
        self.assertEqual(window.session_id, session_of(self.pair.access))

    def test_asking_again_within_a_minute_reuses_the_code_already_sent(self):
        self.send_and_read_code()

        again = self.client.post(CODE_URL)

        self.assertEqual(again.status_code, status.HTTP_200_OK)
        self.assertFalse(again.data['sent'])
        self.assertEqual(len(mail.outbox), 1)

    def test_a_wrong_code_is_refused_without_saying_why(self):
        code = self.send_and_read_code()

        response = self.client.post(STEP_UP_URL, {'code': wrong_code_for(code)}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'step_up_code_invalid')
        self.assertFalse(StepUpWindow.objects.exists())

    def test_the_status_of_this_session(self):
        before = self.client.get(STEP_UP_URL)
        self.client.post(STEP_UP_URL, {'code': self.send_and_read_code()}, format='json')
        after = self.client.get(STEP_UP_URL)

        self.assertEqual((before.data['open'], before.data['expires_at']), (False, None))
        self.assertTrue(after.data['open'])
        self.assertIsNotNone(after.data['expires_at'])

    def test_another_device_does_not_share_the_window(self):
        self.client.post(STEP_UP_URL, {'code': self.send_and_read_code()}, format='json')
        other = APIClient()
        other.credentials(HTTP_AUTHORIZATION=f'Bearer {issue_token_pair(self.user).access}')

        self.assertFalse(other.get(STEP_UP_URL).data['open'])

    def test_a_token_without_a_session_asks_to_refresh(self):
        with patch('accounts.tokens.new_session_id', return_value=''):
            old = issue_token_pair(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {old.access}')

        response = self.client.get(STEP_UP_URL)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'step_up_session_unknown')

    def test_turning_it_off_needs_a_check_first(self):
        refused = self.client.put(SETTING_URL, {'enabled': False}, format='json')
        self.client.post(STEP_UP_URL, {'code': self.send_and_read_code()}, format='json')
        turned_off = self.client.put(SETTING_URL, {'enabled': False}, format='json')
        turned_on = self.client.put(SETTING_URL, {'enabled': True}, format='json')

        self.assertEqual(refused.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(refused.data['code'], 'step_up_required')
        self.assertFalse(turned_off.data['enabled'])
        self.assertTrue(turned_on.data['enabled'])

    def test_needs_a_login(self):
        self.client.credentials()

        self.assertEqual(self.client.get(STEP_UP_URL).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.post(CODE_URL).status_code, status.HTTP_401_UNAUTHORIZED)


@override_settings(BILLING_SECRET=SECRET)
class ServiceStepUpCheckTests(TestCase):
    """결제 서버가 묻는 주소."""

    def setUp(self):
        self.user = make_user()
        self.client = APIClient()

    def ask(self, user_id: str, session_id: str, *, secret: str = SECRET):
        body = json.dumps({'user_id': user_id, 'session_id': session_id}).encode()
        signature = sign_request(
            secret=secret, method='POST', request_uri=CHECK_URL, body=body, sent_at=int(time.time())
        )
        return self.client.generic(
            'POST',
            CHECK_URL,
            body,
            content_type='application/json',
            **{'HTTP_' + SIGNATURE_HEADER.upper().replace('-', '_'): signature},
        )

    def test_an_open_window_is_extended(self):
        code = issue_email_code(user=self.user, purpose=EmailCodePurpose.STEP_UP)
        verify_step_up(self.user, 's1', code, timezone.now() - timedelta(minutes=5))

        response = self.ask(str(self.user.public_id), 's1')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['state'], 'open')
        self.assertGreater(StepUpWindow.objects.get().expires_at, timezone.now() + timedelta(minutes=9))

    def test_without_a_check_it_is_required_and_disabled_users_say_so(self):
        required = self.ask(str(self.user.public_id), 's1')
        self.user.step_up_disabled = True
        self.user.save(update_fields=['step_up_disabled'])
        disabled = self.ask(str(self.user.public_id), 's1')

        self.assertEqual((required.data['state'], required.data['expires_at']), ('required', None))
        self.assertEqual(disabled.data['state'], 'disabled')

    def test_refuses_a_bad_signature_and_an_unknown_user(self):
        forged = self.ask(str(self.user.public_id), 's1', secret='x' * 40)
        unknown = self.ask('00000000-0000-4000-8000-000000000000', 's1')

        self.assertEqual(forged.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(forged.data['code'], 'service_bad_signature')
        self.assertEqual(unknown.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(unknown.data['code'], 'service_user_unknown')
