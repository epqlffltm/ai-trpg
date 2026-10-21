# auth-server/accounts/tests/test_consent_gate.py

"""
다시 동의할 필수 항목이 남은 사람을 다른 서버에서 막는 것(#450, accounts/tokens.py 의 audience_for)을 검증한다.

  - 동의가 지금의 판이면 access 토큰의 대상(aud)이 모든 서버다. 응답의 consents_pending 이 비어 있다
  - 판이 오르거나 기록이 없으면 대상이 인증 서버뿐이다. 다른 서버는 그 토큰을 받지 않는다
  - 그 토큰으로 인증 서버에서 동의를 마치고, 갱신하면 모든 서버에 통하는 토큰이 온다
  - refresh 토큰은 그대로다. 막힌 사람도 갱신과 로그아웃을 한다
"""

import jwt
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.cookies import REFRESH_COOKIE_NAME
from accounts.models import ConsentItem, User
from accounts.tests.helpers import BrowserClient, agree_to_required, log_in
from accounts.tests.test_consents import with_terms_version
from accounts.tokens import audience_for, issue_token_pair

REFRESH_URL = reverse('accounts:refresh')
LOGOUT_URL = reverse('accounts:logout')
ME_URL = reverse('accounts:me')
MY_CONSENTS_URL = reverse('accounts:my-consents')
TERMS_URL = reverse('accounts:my-consent', kwargs={'item': ConsentItem.TERMS})

PASSWORD = 'correct-horse-battery'
GAME_SERVER = 'ai-trpg-game'


def make_user(*, consented: bool) -> User:
    """로그인할 수 있는 계정. consented 면 필수 항목에 지금의 판으로 동의해 두었다."""
    user = User.objects.create_user(
        username='player_01',
        email='someone@example.com',
        nickname='플레이어',
        password=PASSWORD,
        email_verified_at=timezone.now(),
    )
    if consented:
        agree_to_required(user)
    return user


def audience_of(access_token: str) -> list[str]:
    """access 토큰에 실린 대상. 서명은 보지 않는다(내용만 본다)."""
    return jwt.decode(access_token, options={'verify_signature': False})['aud']


def verify_as(access_token: str, server: str) -> dict:
    """다른 서버처럼 공개키와 자기 이름으로 검증한다. 대상에 그 이름이 없으면 jwt.InvalidAudienceError."""
    return jwt.decode(
        access_token,
        settings.JWT_PUBLIC_KEY_PEM,
        algorithms=['RS256'],
        audience=server,
        issuer=settings.SIMPLE_JWT['ISSUER'],
    )


class AudienceTests(APITestCase):
    def test_a_consented_account_reaches_every_server(self):
        pair = issue_token_pair(make_user(consented=True))

        self.assertEqual(pair.consents_pending, ())
        self.assertEqual(audience_of(pair.access), list(settings.SIMPLE_JWT['AUDIENCE']))
        verify_as(pair.access, GAME_SERVER)

    def test_a_raised_version_limits_the_token_to_this_server(self):
        user = make_user(consented=True)

        with with_terms_version(2):
            pair = issue_token_pair(user)

        self.assertEqual(pair.consents_pending, ('terms',))
        self.assertEqual(audience_of(pair.access), [settings.JWT_OWN_AUDIENCE])
        # 다른 서버는 받지 않는다. 인증 서버의 이름으로는 맞는 토큰이다
        with self.assertRaises(jwt.InvalidAudienceError):
            verify_as(pair.access, GAME_SERVER)
        verify_as(pair.access, settings.JWT_OWN_AUDIENCE)

    def test_an_account_without_records_is_limited_too(self):
        # 동의를 받기 전에 가입한 계정이다
        pair = issue_token_pair(make_user(consented=False))

        self.assertEqual(pair.consents_pending, ('terms', 'privacy'))
        self.assertEqual(audience_of(pair.access), [settings.JWT_OWN_AUDIENCE])

    def test_the_refresh_token_keeps_every_name(self):
        # refresh 토큰은 인증 서버만 읽는다. 대상을 좁히지 않는다
        pair = issue_token_pair(make_user(consented=False))

        self.assertEqual(audience_of(pair.refresh), list(settings.SIMPLE_JWT['AUDIENCE']))

    def test_the_audience_follows_the_pending_items(self):
        self.assertEqual(audience_for(()), list(settings.SIMPLE_JWT['AUDIENCE']))
        self.assertEqual(audience_for(('terms',)), [settings.JWT_OWN_AUDIENCE])


class ConsentAgainFlowTests(APITestCase):
    """판이 오른 뒤 로그인한 사람이 인증 서버에서 다시 동의하고 모든 서버로 돌아오는 흐름."""

    client_class = BrowserClient

    def setUp(self):
        self.user = make_user(consented=True)
        raised = with_terms_version(2)
        raised.start()
        self.addCleanup(raised.stop)

    def test_the_login_says_what_to_agree_to(self):
        response = log_in(self.client, 'player_01', PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['consents_pending'], ['terms'])
        self.assertEqual(audience_of(response.data['access_token']), [settings.JWT_OWN_AUDIENCE])

    def test_the_limited_token_opens_this_server_to_finish(self):
        access = log_in(self.client, 'player_01', PASSWORD).data['access_token']
        bearer = {'HTTP_AUTHORIZATION': f'Bearer {access}'}

        me = self.client.get(ME_URL, **bearer)
        states = self.client.get(MY_CONSENTS_URL, **bearer)
        agreed = self.client.put(TERMS_URL, {'version': 2}, format='json', **bearer)

        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.data['consents_pending'], ['terms'])
        self.assertEqual(states.status_code, status.HTTP_200_OK)
        self.assertEqual(agreed.status_code, status.HTTP_200_OK)

    def test_refreshing_after_agreeing_reaches_every_server(self):
        access = log_in(self.client, 'player_01', PASSWORD).data['access_token']
        # 동의하기 전의 갱신은 아직 인증 서버뿐이다
        before = self.client.post(REFRESH_URL)
        self.client.put(TERMS_URL, {'version': 2}, format='json', HTTP_AUTHORIZATION=f'Bearer {access}')

        after = self.client.post(REFRESH_URL)

        self.assertEqual(before.status_code, status.HTTP_200_OK)
        self.assertEqual(before.data['consents_pending'], ['terms'])
        self.assertEqual(audience_of(before.data['access_token']), [settings.JWT_OWN_AUDIENCE])
        self.assertEqual(after.status_code, status.HTTP_200_OK)
        self.assertEqual(after.data['consents_pending'], [])
        verify_as(after.data['access_token'], GAME_SERVER)

    def test_a_limited_account_can_still_log_out(self):
        log_in(self.client, 'player_01', PASSWORD)

        response = self.client.post(LOGOUT_URL)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.client.cookies[REFRESH_COOKIE_NAME].value, '')
