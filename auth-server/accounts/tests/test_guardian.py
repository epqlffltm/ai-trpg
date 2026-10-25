# auth-server/accounts/tests/test_guardian.py

"""
보호자 동의(#336)를 검증한다. 실제 주소로 요청을 보내고, 보호자에게 간 메일에서 링크를 꺼내 쓴다.

  - 요청: 본인인증한 미성년자만, 자기 이메일이 아닌 곳으로, 발송 제한, 동의한 동안에는 바꿀 수 없음
  - 동의: 링크 확인, 보호자는 성년이고 미성년자 본인이 아님, 결제 자격이 바뀜
  - 철회: 한 번 더 열어도 같음, 이메일을 비움, 결제 자격이 바뀜
"""

import re
from datetime import date, timedelta
from unittest.mock import patch
from urllib.parse import unquote

from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.age import korean_today
from accounts.guardian import MAX_REQUESTS_PER_WINDOW, REQUEST_COOLDOWN
from accounts.guardian_links import CONSENT_LINK_LIFETIME, issue_revoke_token
from accounts.identity import person_key, verify_identity
from accounts.models import GuardianConsent, GuardianConsentStatus, PaymentEligibility, User
from accounts.tests.helpers import ADULT_BIRTH_DATE, authorize, identity_token

REQUEST_URL = reverse('accounts:guardian-request')
CONSENT_URL = reverse('accounts:guardian-consent')
REVOKE_URL = reverse('accounts:guardian-revoke')
ME_URL = reverse('accounts:me')
PASSWORD = 'correct-horse-battery'
GUARDIAN_EMAIL = 'parent@example.com'


def make_user(number: int = 1) -> User:
    return User.objects.create_user(
        username=f'player_{number:02d}',
        email=f'player{number}@example.com',
        nickname=f'플레이어{number}',
        password=PASSWORD,
        email_verified_at=timezone.now(),
    )


def born_years_ago(years: int) -> date:
    """한국의 오늘에서 years 년 전. 2월 29일이면 28일로 센다."""
    today = korean_today()
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, day=28)


def token_in(message, base_url: str) -> str:
    """메일 본문의 링크에서 토큰을 꺼낸다."""
    found = re.search(re.escape(base_url) + r'#token=(\S+)', message.body)
    assert found, message.body
    return unquote(found.group(1))


class GuardianTestCase(APITestCase):
    """본인인증을 마친 미성년자(17세)가 로그인한 상태에서 시작한다."""

    def setUp(self):
        self.minor = make_user()
        verify_identity(user=self.minor, token=identity_token('minor-di', born_years_ago(17)))
        authorize(self.client, self.minor)
        # 보호자는 계정이 없다. 로그인하지 않은 클라이언트로 부른다
        self.guardian = APIClient()

    def request_consent(self, email: str = GUARDIAN_EMAIL):
        return self.client.post(REQUEST_URL, {'guardian_email': email}, format='json')

    def consent_link(self) -> str:
        """보호자에게 간 마지막 요청 메일의 링크."""
        requests = [message for message in mail.outbox if message.subject.endswith('보호자 동의 요청')]
        return token_in(requests[-1], 'http://localhost:5173/guardian/consent')

    def consent(self, consent_token: str | None = None, di: str = 'parent-di', birth_date: date = ADULT_BIRTH_DATE):
        return self.guardian.post(
            CONSENT_URL,
            {'consent_token': consent_token or self.consent_link(), 'identity_token': identity_token(di, birth_date)},
            format='json',
        )

    def revoke_link(self) -> str:
        consented = [message for message in mail.outbox if message.subject.endswith('보호자 동의가 적혔습니다')]
        return token_in(consented[-1], 'http://localhost:5173/guardian/revoke')

    def revoke(self, revoke_token: str | None = None):
        return self.guardian.post(REVOKE_URL, {'revoke_token': revoke_token or self.revoke_link()}, format='json')

    def stored(self) -> GuardianConsent:
        return GuardianConsent.objects.get(minor=self.minor)

    def eligibility_version(self) -> int:
        return PaymentEligibility.objects.get(user=self.minor).version


class RequestTests(GuardianTestCase):
    def test_a_minor_asks_the_guardian(self):
        response = self.request_consent()

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED, response.data)
        self.assertEqual(response.data['guardian_consent'], 'requested')
        self.assertEqual(self.stored().status, GuardianConsentStatus.REQUESTED)
        message = mail.outbox[-1]
        self.assertEqual(message.to, [GUARDIAN_EMAIL])
        # 보호자에게는 닉네임만 보인다. 아이디와 이메일은 보이지 않는다
        self.assertIn('플레이어1', message.body)
        self.assertNotIn('player_01', message.body)
        self.assertNotIn('player1@example.com', message.body)

    def test_needs_a_logged_in_user(self):
        self.client.credentials()

        self.assertEqual(self.request_consent().status_code, status.HTTP_401_UNAUTHORIZED)

    def test_an_unverified_account_must_verify_first(self):
        authorize(self.client, make_user(2))

        response = self.request_consent()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'identity_verification_required')

    def test_an_adult_needs_no_guardian(self):
        adult = make_user(2)
        verify_identity(user=adult, token=identity_token('adult-di', ADULT_BIRTH_DATE))
        authorize(self.client, adult)

        response = self.request_consent()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'guardian_not_needed')

    def test_the_own_email_is_refused(self):
        response = self.request_consent('Player1@Example.com')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('guardian_email', response.data['errors'])
        self.assertFalse(GuardianConsent.objects.exists())

    def test_asking_again_too_soon_waits(self):
        self.request_consent()

        response = self.request_consent('other@example.com')

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data['code'], 'guardian_request_unavailable')
        self.assertEqual(response['Retry-After'], str(int(REQUEST_COOLDOWN.total_seconds())))
        self.assertEqual(self.stored().guardian_email, GUARDIAN_EMAIL)

    def test_a_new_request_kills_the_old_link(self):
        self.request_consent()
        old_link = self.consent_link()

        with patch('accounts.guardian.timezone.now', return_value=timezone.now() + REQUEST_COOLDOWN):
            self.request_consent('other@example.com')

        self.assertEqual(self.consent(old_link).data['code'], 'guardian_link_invalid')
        self.assertEqual(self.consent().status_code, status.HTTP_200_OK)

    def test_at_most_a_few_requests_a_day(self):
        start = timezone.now()
        for index in range(MAX_REQUESTS_PER_WINDOW):
            with patch('accounts.guardian.timezone.now', return_value=start + REQUEST_COOLDOWN * index):
                self.assertEqual(self.request_consent().status_code, status.HTTP_202_ACCEPTED)

        with patch('accounts.guardian.timezone.now', return_value=start + REQUEST_COOLDOWN * MAX_REQUESTS_PER_WINDOW):
            refused = self.request_consent()
        with patch('accounts.guardian.timezone.now', return_value=start + timedelta(days=1)):
            next_day = self.request_consent()

        self.assertEqual(refused.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(next_day.status_code, status.HTTP_202_ACCEPTED)

    def test_the_guardian_cannot_be_changed_while_consenting(self):
        # 바꾸게 하면 아무 성인에게 다시 동의를 받아 보호자의 철회를 피할 수 있다
        self.request_consent()
        self.consent()

        with patch('accounts.guardian.timezone.now', return_value=timezone.now() + REQUEST_COOLDOWN):
            response = self.request_consent('other@example.com')

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'guardian_consent_active')
        self.assertEqual(self.stored().guardian_email, GUARDIAN_EMAIL)

    def test_after_revoking_the_minor_may_ask_again(self):
        self.request_consent()
        self.consent()
        self.revoke()

        with patch('accounts.guardian.timezone.now', return_value=timezone.now() + REQUEST_COOLDOWN):
            response = self.request_consent('other@example.com')

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(self.stored().status, GuardianConsentStatus.REQUESTED)


class ConsentTests(GuardianTestCase):
    def setUp(self):
        super().setUp()
        self.request_consent()

    def test_an_adult_guardian_consents(self):
        version = self.eligibility_version()

        response = self.consent()

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        consent = self.stored()
        self.assertEqual(consent.status, GuardianConsentStatus.CONSENTED)
        self.assertEqual(consent.guardian_person_key, person_key('parent-di'))
        self.assertIsNotNone(consent.consented_at)
        # 결제 서버에 알릴 일이 생겼다
        self.assertEqual(self.eligibility_version(), version + 1)

    def test_both_are_told(self):
        self.consent()

        subjects = {message.subject: message.to for message in mail.outbox[-2:]}
        self.assertEqual(subjects['[AI TRPG] 보호자 동의가 적혔습니다'], [GUARDIAN_EMAIL])
        self.assertEqual(subjects['[AI TRPG] 보호자가 결제에 동의했습니다'], [self.minor.email])
        self.assertTrue(self.revoke_link())

    def test_a_minor_cannot_be_the_guardian(self):
        response = self.consent(di='friend-di', birth_date=born_years_ago(18))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'guardian_not_adult')
        self.assertEqual(self.stored().status, GuardianConsentStatus.REQUESTED)

    def test_the_minor_cannot_consent_for_themself(self):
        # 같은 사람(DI)이다. 생일을 바꿔 적어도 사람 열쇠가 같다
        response = self.consent(di='minor-di')

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'guardian_is_minor')
        self.assertEqual(self.stored().status, GuardianConsentStatus.REQUESTED)

    def test_a_used_link_cannot_be_used_again(self):
        link = self.consent_link()
        self.consent(link)

        response = self.consent(link, di='someone-else')

        self.assertEqual(response.data['code'], 'guardian_link_invalid')
        self.assertEqual(self.stored().guardian_person_key, person_key('parent-di'))

    def test_a_link_expires_after_a_week(self):
        link = self.consent_link()

        with patch(
            'django.core.signing.time.time',
            return_value=timezone.now().timestamp() + 1 + CONSENT_LINK_LIFETIME.total_seconds(),
        ):
            response = self.consent(link)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'guardian_link_invalid')

    def test_forged_and_swapped_links_are_refused(self):
        revoke_token = issue_revoke_token(minor_public_id=self.minor.public_id, nonce=self.stored().link_nonce)
        for token in ('not-a-link', self.consent_link() + 'x', revoke_token):
            with self.subTest(token=token[:20]):
                self.assertEqual(self.consent(token).data['code'], 'guardian_link_invalid')

    def test_the_provider_is_not_asked_for_a_bad_link(self):
        # 서명이 틀린 링크와, 서명은 맞지만 새 요청으로 바뀐 링크. 보호자의 본인인증을 헛되이 쓰지 않는다
        stale = self.consent_link()
        with patch('accounts.guardian.timezone.now', return_value=timezone.now() + REQUEST_COOLDOWN):
            self.request_consent('other@example.com')

        with patch('accounts.guardian.get_identity_provider') as provider:
            self.consent('not-a-link')
            self.consent(stale)

        provider.assert_not_called()

    def test_a_bad_identity_token_is_refused(self):
        response = self.guardian.post(
            CONSENT_URL, {'consent_token': self.consent_link(), 'identity_token': 'fake:x:2001-02-30'}, format='json'
        )

        self.assertEqual(response.data['code'], 'identity_token_invalid')

    @override_settings(IDENTITY_PROVIDER='disabled')
    def test_a_disabled_provider_answers_503(self):
        self.assertEqual(self.consent().status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_a_blocked_minor_cannot_be_consented_for(self):
        User.objects.filter(pk=self.minor.pk).update(is_active=False)

        self.assertEqual(self.consent().data['code'], 'guardian_link_invalid')

    def test_a_minor_who_grew_up_needs_no_consent(self):
        grown = self.minor.identity_verification.legal_adult_from

        with patch('accounts.guardian.korean_today', return_value=grown):
            response = self.consent()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'guardian_not_needed')


class RevokeTests(GuardianTestCase):
    def setUp(self):
        super().setUp()
        self.request_consent()
        self.consent()

    def test_the_guardian_revokes(self):
        version = self.eligibility_version()

        response = self.revoke()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIs(response.data['revoked'], True)
        consent = self.stored()
        self.assertEqual(consent.status, GuardianConsentStatus.REVOKED)
        # 더 보낼 일이 없어 보호자의 이메일을 비운다. 누가 동의했는지는 남는다
        self.assertEqual(consent.guardian_email, '')
        self.assertEqual(consent.guardian_person_key, person_key('parent-di'))
        self.assertEqual(self.eligibility_version(), version + 1)
        self.assertEqual(
            {message.subject for message in mail.outbox[-2:]},
            {'[AI TRPG] 보호자 동의를 철회했습니다', '[AI TRPG] 보호자가 결제 동의를 철회했습니다'},
        )

    def test_revoking_twice_is_the_same(self):
        link = self.revoke_link()
        self.revoke(link)
        version = self.eligibility_version()

        response = self.revoke(link)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIs(response.data['revoked'], False)
        self.assertEqual(self.eligibility_version(), version)

    def test_forged_and_swapped_links_are_refused(self):
        for token in ('not-a-link', self.revoke_link() + 'x', self.consent_link()):
            with self.subTest(token=token[:20]):
                response = self.revoke(token)
                self.assertEqual(response.data['code'], 'guardian_link_invalid')
        self.assertEqual(self.stored().status, GuardianConsentStatus.CONSENTED)

    def test_an_old_revoke_link_does_not_touch_a_new_request(self):
        old_link = self.revoke_link()
        self.revoke(old_link)
        with patch('accounts.guardian.timezone.now', return_value=timezone.now() + REQUEST_COOLDOWN):
            self.request_consent('other@example.com')

        response = self.revoke(old_link)

        self.assertEqual(response.data['code'], 'guardian_link_invalid')
        self.assertEqual(self.stored().status, GuardianConsentStatus.REQUESTED)


class MeTests(GuardianTestCase):
    def guardian_consent(self) -> str:
        return self.client.get(ME_URL).data['guardian_consent']

    def test_me_follows_the_consent(self):
        seen = [self.guardian_consent()]
        self.request_consent()
        seen.append(self.guardian_consent())
        self.consent()
        seen.append(self.guardian_consent())
        self.revoke()
        seen.append(self.guardian_consent())

        self.assertEqual(seen, ['none', 'requested', 'consented', 'revoked'])
