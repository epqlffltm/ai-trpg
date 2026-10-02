# auth-server/accounts/tests/test_login.py

"""
로그인(비밀번호 → 이메일 코드), JWKS, 토큰 검증을 확인한다.

토큰을 받는 쪽(게임 서버)의 입장도 여기서 검증한다.
JWKS 에서 공개키를 가져와 서명을 확인하는 과정을 그대로 따라 한다.
"""

import base64
import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.core import mail, signing
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.cookies import REFRESH_COOKIE_NAME
from accounts.email_codes import (
    CODE_LIFETIME,
    ISSUE_COOLDOWN,
    MAX_FAILED_ATTEMPTS,
    MAX_ISSUES_PER_WINDOW,
    issue_email_code,
)
from accounts.login_tickets import LOGIN_TICKET_LIFETIME, LOGIN_TICKET_SALT
from accounts.models import EmailCodePurpose, User
from accounts.tests.helpers import (
    LOGIN_URL,
    LOGIN_VERIFY_URL,
    code_from,
    log_in,
    start_login,
    wrong_code_for,
)
from accounts.tokens import AccessToken, issue_token_pair, revoke_all_sessions

LOGIN_RESEND_URL = reverse('accounts:login-resend')
JWKS_URL = reverse('accounts:jwks')
ME_URL = reverse('accounts:me')

PASSWORD = 'correct-horse-battery'
GAME_SERVER_AUDIENCE = 'ai-trpg-game'


def create_user(**overrides) -> User:
    fields = {
        'username': 'player_01',
        'email': 'someone@example.com',
        'nickname': '플레이어',
        'password': PASSWORD,
        # 이메일 인증을 끝낸 계정이어야 로그인할 수 있다
        'email_verified_at': timezone.now(),
    }
    fields.update(overrides)
    return User.objects.create_user(**fields)

def issue_access_token(user: User) -> str:
    """테스트에서는 access 토큰만 필요한 경우가 많다."""
    return issue_token_pair(user).access

def base64url(data: bytes) -> str:
    """JWT 가 쓰는 base64url 인코딩. 끝의 = 를 뗀다."""
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


class LoginTestCase(APITestCase):
    def setUp(self):
        self.user = create_user()

    def start(self, username: str = 'player_01', password: str = PASSWORD):
        """1단계: 아이디와 비밀번호."""
        return start_login(self.client, username, password)

    def verify(self, login_ticket: str, code: str):
        """2단계: 티켓과 인증 코드."""
        return self.client.post(
            LOGIN_VERIFY_URL,
            {'login_ticket': login_ticket, 'code': code},
            format='json',
        )

    def resend(self, login_ticket: str):
        return self.client.post(LOGIN_RESEND_URL, {'login_ticket': login_ticket}, format='json')

    def after(self, elapsed: timedelta):
        """인증 코드 쪽의 시계를 elapsed 만큼 뒤로 옮긴다."""
        return patch(
            'accounts.email_codes.timezone.now',
            return_value=timezone.now() + elapsed,
        )


class LoginStartTests(LoginTestCase):
    def test_returns_ticket_instead_of_tokens(self):
        response = self.start()

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(set(response.data), {'detail', 'login_ticket'})
        # 비밀번호만으로는 토큰도 쿠키도 나오지 않는다
        self.assertNotIn(REFRESH_COOKIE_NAME, response.cookies)

    def test_sends_login_code_to_the_email(self):
        self.start()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn('로그인', mail.outbox[0].subject)

    def test_username_is_case_insensitive(self):
        response = self.start(username='Player_01')

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def test_wrong_password_and_unknown_user_get_the_same_response(self):
        wrong_password = self.start(password='wrong-password')
        unknown_user = self.start(username='nobody_here')

        self.assertEqual(wrong_password.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(unknown_user.status_code, status.HTTP_401_UNAUTHORIZED)
        # 응답 본문이 완전히 같아야 가입 여부가 드러나지 않는다
        self.assertEqual(wrong_password.data, unknown_user.data)

    def test_wrong_password_sends_no_mail(self):
        self.start(password='wrong-password')

        # 비밀번호를 모르는 사람이 남의 메일함에 코드를 보낼 수 없어야 한다
        self.assertEqual(len(mail.outbox), 0)

    def test_inactive_user_cannot_log_in(self):
        self.user.is_active = False
        self.user.save()

        response = self.start()

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rejects_missing_password(self):
        response = self.client.post(LOGIN_URL, {'username': 'player_01'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_second_start_within_cooldown_reuses_the_sent_code(self):
        first = self.start()
        code = code_from(mail.outbox[0])

        second = self.start()

        # 새 메일은 가지 않지만, 방금 보낸 코드로 로그인을 이어 갈 수 있다
        self.assertEqual(second.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotEqual(second.data['detail'], first.data['detail'])
        self.assertEqual(self.verify(second.data['login_ticket'], code).status_code, status.HTTP_200_OK)

    def test_returns_429_when_no_code_can_be_sent(self):
        now = timezone.now()
        for index in range(MAX_ISSUES_PER_WINDOW):
            with patch('accounts.email_codes.timezone.now', return_value=now + CODE_LIFETIME * index):
                self.start()

        with patch('accounts.email_codes.timezone.now', return_value=now + CODE_LIFETIME * MAX_ISSUES_PER_WINDOW):
            response = self.start()

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data['code'], 'login_code_unavailable')
        self.assertEqual(response['Retry-After'], str(response.data['retry_after']))
        self.assertNotIn('login_ticket', response.data)


class LoginVerifyTests(LoginTestCase):
    def setUp(self):
        super().setUp()
        self.ticket = self.start().data['login_ticket']
        self.code = code_from(mail.outbox[0])

    def test_returns_access_token(self):
        response = self.verify(self.ticket, self.code)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # refresh 토큰은 본문에 싣지 않는다
        self.assertEqual(set(response.data), {'access_token', 'token_type', 'expires_in'})
        self.assertEqual(response.data['token_type'], 'Bearer')
        self.assertEqual(response.data['expires_in'], 15 * 60)
        self.assertIn(REFRESH_COOKIE_NAME, response.cookies)

    def test_rejects_wrong_code(self):
        response = self.verify(self.ticket, wrong_code_for(self.code))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn(REFRESH_COOKIE_NAME, response.cookies)

    def test_code_cannot_be_used_twice(self):
        self.verify(self.ticket, self.code)

        response = self.verify(self.ticket, self.code)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_code_is_discarded_after_too_many_wrong_attempts(self):
        for _ in range(MAX_FAILED_ATTEMPTS):
            self.verify(self.ticket, wrong_code_for(self.code))

        response = self.verify(self.ticket, self.code)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_malformed_code(self):
        response = self.verify(self.ticket, '12345')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('code', response.data)

    def test_signup_code_cannot_be_used_for_login(self):
        signup_code = issue_email_code(user=self.user, purpose=EmailCodePurpose.SIGNUP)

        response = self.verify(self.ticket, signup_code)

        # 두 코드가 우연히 같을 수 있다. 그때는 이 검증이 의미가 없으므로 건너뛴다
        if signup_code != self.code:
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_can_log_in_again_right_after_logging_in(self):
        self.verify(self.ticket, self.code)

        # 다른 기기에서 곧바로 로그인한다. 1분을 기다리게 하면 안 된다
        other_device = APIClient()
        response = log_in(other_device, 'player_01', PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 2)


class LoginTicketTests(LoginTestCase):
    """티켓이 없거나 쓸 수 없으면 2단계에 들어올 수 없다."""

    def setUp(self):
        super().setUp()
        self.ticket = self.start().data['login_ticket']
        self.code = code_from(mail.outbox[0])

    def assert_ticket_rejected(self, response) -> None:
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['code'], 'login_ticket_invalid')
        self.assertNotIn(REFRESH_COOKIE_NAME, response.cookies)

    def test_rejects_forged_ticket(self):
        self.assert_ticket_rejected(self.verify('not-a-real-ticket', self.code))

    def test_rejects_tampered_ticket(self):
        # 서명은 그대로 두고 내용의 한 글자만 바꾼다
        tampered = ('A' if self.ticket[0] != 'A' else 'B') + self.ticket[1:]

        self.assert_ticket_rejected(self.verify(tampered, self.code))

    def test_rejects_expired_ticket(self):
        with patch('django.core.signing.time.time', return_value=time.time() + LOGIN_TICKET_LIFETIME.total_seconds() + 1):
            response = self.verify(self.ticket, self.code)

        self.assert_ticket_rejected(response)

    def test_rejects_ticket_made_for_another_purpose(self):
        # 같은 비밀키로 서명했지만 용도(salt)가 다른 값은 티켓으로 쓸 수 없다
        other = signing.dumps({'sub': str(self.user.public_id), 'ver': 0}, salt='something.else')

        self.assert_ticket_rejected(self.verify(other, self.code))

    def test_rejects_ticket_after_all_sessions_are_revoked(self):
        revoke_all_sessions(self.user)

        self.assert_ticket_rejected(self.verify(self.ticket, self.code))

    def test_rejects_ticket_of_deactivated_user(self):
        self.user.is_active = False
        self.user.save()

        self.assert_ticket_rejected(self.verify(self.ticket, self.code))

    def test_wrong_code_without_ticket_does_not_burn_the_code(self):
        # 아이디만 아는 제3자가 남의 로그인을 방해할 수 없어야 한다
        for _ in range(MAX_FAILED_ATTEMPTS):
            self.verify('not-a-real-ticket', wrong_code_for(self.code))

        response = self.verify(self.ticket, self.code)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_ticket_does_not_carry_private_data(self):
        payload = signing.loads(self.ticket, salt=LOGIN_TICKET_SALT)

        # 티켓은 서명만 되어 있고 암호화되어 있지 않다
        self.assertEqual(set(payload), {'sub', 'ver'})
        self.assertNotIn(self.user.email, self.ticket)


class LoginResendTests(LoginTestCase):
    def setUp(self):
        super().setUp()
        self.ticket = self.start().data['login_ticket']
        self.first_code = code_from(mail.outbox[0])

    def test_sends_a_new_code_and_retires_the_old_one(self):
        with self.after(ISSUE_COOLDOWN):
            response = self.resend(self.ticket)
            new_code = code_from(mail.outbox[-1])
            old_code_response = self.verify(self.ticket, self.first_code)
            new_code_response = self.verify(self.ticket, new_code)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 2)
        if new_code != self.first_code:
            self.assertEqual(old_code_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(new_code_response.status_code, status.HTTP_200_OK)

    def test_returns_429_within_cooldown(self):
        response = self.resend(self.ticket)

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertGreaterEqual(response.data['retry_after'], 1)
        self.assertLessEqual(response.data['retry_after'], ISSUE_COOLDOWN.total_seconds())
        self.assertEqual(len(mail.outbox), 1)

    def test_requires_a_valid_ticket(self):
        with self.after(ISSUE_COOLDOWN):
            response = self.resend('not-a-real-ticket')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(len(mail.outbox), 1)


class AccessTokenContentTests(APITestCase):
    def setUp(self):
        self.user = create_user()
        self.token = issue_access_token(self.user)

    def test_header_has_rs256_and_key_id(self):
        header = jwt.get_unverified_header(self.token)

        self.assertEqual(header['alg'], 'RS256')
        self.assertEqual(header['kid'], settings.JWT_KEY_ID)

    def test_claims(self):
        claims = jwt.decode(self.token, options={'verify_signature': False})

        self.assertEqual(claims['sub'], str(self.user.public_id))
        self.assertEqual(claims['iss'], 'ai-trpg-auth')
        self.assertIn(GAME_SERVER_AUDIENCE, claims['aud'])
        self.assertEqual(claims['token_type'], 'access')
        self.assertEqual(claims['exp'] - claims['iat'], 15 * 60)

    def test_token_does_not_carry_private_data(self):
        claims = jwt.decode(self.token, options={'verify_signature': False})

        # 토큰은 서명만 되어 있고 암호화되어 있지 않다. 누구나 내용을 읽을 수 있다
        self.assertNotIn(self.user.email, json.dumps(claims))
        self.assertNotIn('user_id', claims)
        self.assertNotEqual(claims['sub'], str(self.user.pk))
class JwksTests(APITestCase):
    def test_is_public(self):
        response = self.client.get(JWKS_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('max-age', response['Cache-Control'])

    def test_exposes_only_the_public_key(self):
        response = self.client.get(JWKS_URL)
        key = response.data['keys'][0]

        self.assertEqual(key['kty'], 'RSA')
        self.assertEqual(key['kid'], settings.JWT_KEY_ID)
        self.assertEqual(key['alg'], 'RS256')
        self.assertEqual(key['use'], 'sig')
        # d, p, q 는 개인키의 값이다. 하나라도 있으면 개인키가 새는 것이다
        for private_field in ('d', 'p', 'q', 'dp', 'dq', 'qi'):
            self.assertNotIn(private_field, key)


class GameServerVerificationTests(APITestCase):
    """게임 서버가 하게 될 검증을 그대로 따라 한다."""

    def setUp(self):
        self.user = create_user()
        self.token = issue_access_token(self.user)

    def fetch_public_key(self, token: str):
        """JWKS 를 받아, 토큰 머리말의 kid 와 같은 키를 고른다."""
        key_id = jwt.get_unverified_header(token)['kid']
        keys = self.client.get(JWKS_URL).data['keys']
        matching_key = next(key for key in keys if key['kid'] == key_id)
        return jwt.PyJWK(matching_key).key

    def verify(self, token: str, audience: str = GAME_SERVER_AUDIENCE) -> dict:
        return jwt.decode(
            token,
            self.fetch_public_key(token),
            # 허용할 알고리즘을 검증하는 쪽이 정한다. 토큰이 적어 온 alg 를 믿지 않는다
            algorithms=['RS256'],
            audience=audience,
            issuer='ai-trpg-auth',
        )

    def test_verifies_with_key_from_jwks(self):
        claims = self.verify(self.token)

        self.assertEqual(claims['sub'], str(self.user.public_id))

    def test_rejects_other_audience(self):
        with self.assertRaises(jwt.InvalidAudienceError):
            self.verify(self.token, audience='some-other-server')

    def test_rejects_tampered_payload(self):
        header, payload, signature = self.token.split('.')
        claims = jwt.decode(self.token, options={'verify_signature': False})
        claims['sub'] = '00000000-0000-0000-0000-000000000000'
        forged_payload = base64url(json.dumps(claims).encode())

        with self.assertRaises(jwt.InvalidSignatureError):
            self.verify(f'{header}.{forged_payload}.{signature}')

    def test_rejects_token_signed_with_another_key(self):
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        claims = jwt.decode(self.token, options={'verify_signature': False})
        # kid 는 진짜 키의 것을 베껴 적고, 서명만 다른 키로 한다
        forged = jwt.encode(
            claims,
            other_key,
            algorithm='RS256',
            headers={'kid': settings.JWT_KEY_ID},
        )

        with self.assertRaises(jwt.InvalidSignatureError):
            self.verify(forged)


class MeTests(APITestCase):
    def setUp(self):
        self.user = create_user()

    def get_me(self, token: str | None = None):
        headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'} if token else {}
        return self.client.get(ME_URL, **headers)

    def test_returns_own_account(self):
        response = self.get_me(issue_access_token(self.user))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'player_01')
        self.assertEqual(set(response.data), {'public_id', 'username', 'email', 'nickname'})

    def test_requires_token(self):
        response = self.get_me()

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rejects_expired_token(self):
        # 정상 토큰을 읽어 들인 뒤 만료 시각만 과거로 바꿔 다시 서명한다
        token = AccessToken(issue_access_token(self.user))
        token.set_exp(lifetime=-timedelta(minutes=1))

        response = self.get_me(str(token))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rejects_token_of_deactivated_user(self):
        token = issue_access_token(self.user)
        self.user.is_active = False
        self.user.save()

        response = self.get_me(token)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rejects_unsigned_token(self):
        # alg 를 none 으로 적고 서명을 비운 토큰
        claims = jwt.decode(issue_access_token(self.user), options={'verify_signature': False})
        header = base64url(json.dumps({'alg': 'none', 'typ': 'JWT'}).encode())
        payload = base64url(json.dumps(claims).encode())

        response = self.get_me(f'{header}.{payload}.')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rejects_hs256_token_signed_with_public_key(self):
        # 알고리즘 혼동 공격.
        # 공개키는 누구나 얻을 수 있다. 서버가 토큰의 alg 를 그대로 믿으면,
        # 공개키를 HMAC 비밀키로 써서 만든 HS256 토큰을 진짜로 받아들이게 된다
        claims = jwt.decode(issue_access_token(self.user), options={'verify_signature': False})
        header = base64url(json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode())
        payload = base64url(json.dumps(claims).encode())
        signing_input = f'{header}.{payload}'.encode()
        signature = hmac.new(
            settings.JWT_PUBLIC_KEY_PEM.encode(),
            signing_input,
            hashlib.sha256,
        ).digest()

        response = self.get_me(f'{header}.{payload}.{base64url(signature)}')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)