# auth-server/accounts/tests/test_login.py

"""
로그인, JWKS, 토큰 검증을 확인한다.

토큰을 받는 쪽(게임 서버)의 입장도 여기서 검증한다.
JWKS 에서 공개키를 가져와 서명을 확인하는 과정을 그대로 따라 한다.
"""

import base64
import hashlib
import hmac
import json
from datetime import timedelta

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from accounts.tokens import AccessToken, issue_token_pair

LOGIN_URL = reverse('accounts:login')
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
    }
    fields.update(overrides)
    return User.objects.create_user(**fields)

def issue_access_token(user: User) -> str:
    """테스트에서는 access 토큰만 필요한 경우가 많다."""
    return issue_token_pair(user).access

def base64url(data: bytes) -> str:
    """JWT 가 쓰는 base64url 인코딩. 끝의 = 를 뗀다."""
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


class LoginTests(APITestCase):
    def setUp(self):
        self.user = create_user()

    def login(self, username: str = 'player_01', password: str = PASSWORD):
        return self.client.post(
            LOGIN_URL,
            {'username': username, 'password': password},
            format='json',
        )

    def test_returns_access_token(self):
        response = self.login()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {'access_token', 'token_type', 'expires_in'})
        self.assertEqual(response.data['token_type'], 'Bearer')
        self.assertEqual(response.data['expires_in'], 15 * 60)

    def test_username_is_case_insensitive(self):
        response = self.login(username='Player_01')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_wrong_password_and_unknown_user_get_the_same_response(self):
        wrong_password = self.login(password='wrong-password')
        unknown_user = self.login(username='nobody_here')

        self.assertEqual(wrong_password.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(unknown_user.status_code, status.HTTP_401_UNAUTHORIZED)
        # 응답 본문이 완전히 같아야 가입 여부가 드러나지 않는다
        self.assertEqual(wrong_password.data, unknown_user.data)

    def test_inactive_user_cannot_log_in(self):
        self.user.is_active = False
        self.user.save()

        response = self.login()

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rejects_missing_password(self):
        response = self.client.post(LOGIN_URL, {'username': 'player_01'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


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