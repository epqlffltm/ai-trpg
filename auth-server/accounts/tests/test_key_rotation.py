# auth-server/accounts/tests/test_key_rotation.py

"""
JWT 키 교체(#21)를 검증한다. 서명 키를 바꾸는 동안 옛 키의 토큰을 계속 받고, 검증 목록에서 뺀 키의 토큰은 거부하는지.

교체는 설정(서명 키, 검증 키 목록)을 바꿔 흉내 낸다. 실제 운영에서는 설정 파일을 고치고 서버를 다시 띄운다.
"""

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from accounts.cookies import REFRESH_COOKIE_NAME
from accounts.tests.test_refresh import REFRESH_URL, RefreshTestCase
from config.jwt_keys import canonical_public_key_pem, compute_key_id

JWKS_URL = reverse('accounts:jwks')


def new_key() -> tuple[str, str, str]:
    """새 RSA 키 쌍. (개인키 PEM, 공개키 PEM, kid)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode('ascii')
    public_pem = canonical_public_key_pem(private_key.public_key())
    return private_pem, public_pem, compute_key_id(public_pem)


def keys_in_use(signing: tuple[str, str, str], *verify_only: tuple[str, str, str]):
    """signing 으로 서명하고, signing 과 verify_only 로 검증하는 설정."""
    private_pem, public_pem, key_id = signing
    verification = {key_id: public_pem}
    verification.update({other_id: other_public for _, other_public, other_id in verify_only})
    return override_settings(
        JWT_SIGNING_KEY_PEM=private_pem,
        JWT_KEY_ID=key_id,
        JWT_VERIFICATION_KEYS=verification,
    )


def key_id_of(token: str) -> str:
    return jwt.get_unverified_header(token)['kid']


class RotationTests(RefreshTestCase):
    """setUp 이 지금의 키(설정의 서명 키)로 로그인해 둔다. 그 키를 "옛 키"로 쓴다."""

    def setUp(self):
        super().setUp()
        self.old = (settings.JWT_SIGNING_KEY_PEM, settings.JWT_PUBLIC_KEY_PEM, settings.JWT_KEY_ID)
        self.new = new_key()
        self.old_refresh = self.refresh_cookie_value()
        self.old_access = self.login_response.data['access_token']

    def test_the_next_key_is_published_before_it_signs(self):
        # 1단계: 새 키를 검증 목록에만 넣는다. JWKS 에 둘 다 실리고, 서명은 옛 키로 한다
        with keys_in_use(self.old, self.new):
            keys = self.client.get(JWKS_URL).data['keys']
            response = self.client_with_refresh_token(self.old_refresh).post(REFRESH_URL)

        self.assertEqual([key['kid'] for key in keys], [self.old[2], self.new[2]])
        self.assertEqual(key_id_of(response.data['access_token']), self.old[2])

    def test_old_tokens_keep_working_after_the_signing_key_changes(self):
        # 2단계: 새 키로 서명하고 옛 키는 검증만 한다. 옛 키의 refresh 토큰(14일)으로 갱신하면 새 키의 토큰이 나온다
        with keys_in_use(self.new, self.old):
            refreshed = self.client_with_refresh_token(self.old_refresh).post(REFRESH_URL)
            me = self.get_me(self.old_access)

        self.assertEqual(refreshed.status_code, status.HTTP_200_OK)
        self.assertEqual(key_id_of(refreshed.data['access_token']), self.new[2])
        self.assertEqual(key_id_of(refreshed.cookies[REFRESH_COOKIE_NAME].value), self.new[2])
        self.assertEqual(me.status_code, status.HTTP_200_OK)

    def test_tokens_of_a_removed_key_are_refused(self):
        # 3단계(또는 긴급 폐기): 옛 키를 목록에서 뺀다. 그 키로 서명한 토큰은 받지 않는다
        with keys_in_use(self.new):
            refreshed = self.client_with_refresh_token(self.old_refresh).post(REFRESH_URL)
            me = self.get_me(self.old_access)
            keys = self.client.get(JWKS_URL).data['keys']

        self.assertEqual(refreshed.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(me.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual([key['kid'] for key in keys], [self.new[2]])

    def test_a_token_without_a_key_id_is_refused(self):
        claims = jwt.decode(self.old_access, options={'verify_signature': False})
        unnamed = jwt.encode(claims, self.old[0], algorithm='RS256')

        self.assertEqual(self.get_me(unnamed).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_token_signed_by_an_unknown_key_is_refused(self):
        # 서명은 맞지만 이 서버가 모르는 키다. 남이 만든 키로 kid 만 흉내 내도 서명이 맞지 않는다
        stranger = new_key()
        claims = jwt.decode(self.old_access, options={'verify_signature': False})
        forged = jwt.encode(claims, stranger[0], algorithm='RS256', headers={'kid': self.old[2]})
        unknown = jwt.encode(claims, stranger[0], algorithm='RS256', headers={'kid': stranger[2]})

        self.assertEqual(self.get_me(forged).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.get_me(unknown).status_code, status.HTTP_401_UNAUTHORIZED)
