# auth-server/accounts/tests/test_identity.py

"""
휴대폰 본인인증(#336)을 검증한다. 가짜 본인확인 업체로 실제 주소(POST identity/verify)를 지난다.

  - 업체: 가짜 업체의 token 읽기, 꺼 둔 업체
  - 인증: 날짜 둘, 한 계정 한 번, 한 사람 한 계정, 만 14세 미만 막기
  - 상태: 내 정보와 토큰의 adult_content, 날짜가 지나면 저절로 바뀌기
  - 동시에: 두 계정이 같은 사람으로 함께 인증하기
"""

import threading
from datetime import date, timedelta
from unittest.mock import patch

import jwt
from django.db import connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.age import adult_content_from, korean_today, legal_adult_from
from accounts.cookies import REFRESH_COOKIE_NAME
from accounts.identity import (
    IdentityInUseError,
    person_key,
    verify_identity,
)
from accounts.identity_providers import (
    DisabledIdentityProvider,
    FakeIdentityProvider,
    IdentityResult,
    IdentityTokenError,
    IdentityUnavailableError,
    get_identity_provider,
)
from accounts.identity_status import UNVERIFIED, IdentityStatus, identity_status_of, status_from
from accounts.models import (
    EmailCode,
    IdentityVerification,
    OutgoingMail,
    SecurityEvent,
    SecurityEventKind,
    SignupCode,
    User,
)
from accounts.tests.helpers import (
    ADULT_BIRTH_DATE,
    BrowserClient,
    authorize,
    identity_token,
    log_in,
)
from accounts.tests.helpers import (
    verify_identity as post_verify,
)
from accounts.tokens import ADULT_CONTENT_CLAIM, issue_token_pair

ME_URL = reverse('accounts:me')
REFRESH_URL = reverse('accounts:refresh')
PASSWORD = 'correct-horse-battery'


def make_user(number: int = 1) -> User:
    return User.objects.create_user(
        username=f'player_{number:02d}',
        email=f'player{number}@example.com',
        nickname=f'플레이어{number}',
        password=PASSWORD,
        email_verified_at=timezone.now(),
    )


def born_years_ago(years: int, days: int = 0) -> date:
    """
    한국의 오늘에서 years 년 전, 다시 days 일 전에 태어난 날. days 가 음수면 그만큼 뒤다.

    오늘이 2월 29일이고 그해에 그날이 없으면 2월 28일에서 센다.
    """
    today = korean_today()
    try:
        same_day = today.replace(year=today.year - years)
    except ValueError:
        same_day = today.replace(year=today.year - years, day=28)
    return same_day - timedelta(days=days)


def claims_of(access_token: str) -> dict:
    return jwt.decode(access_token, options={'verify_signature': False})


class FakeProviderTests(SimpleTestCase):
    def test_reads_the_di_and_the_birth_date(self):
        result = FakeIdentityProvider().verify('fake:Abc+/=_-123:2001-02-03')

        self.assertEqual(result, IdentityResult(di='Abc+/=_-123', birth_date=date(2001, 2, 3)))

    def test_refuses_anything_else(self):
        refused = [
            '',
            'fake::2001-02-03',
            'fake:abc',
            'fake:abc:2001-2-3',
            'fake:abc:2001-02-30',
            'fake:a b:2001-02-03',
            'fake:abc:2001-02-03\n',
            'real:abc:2001-02-03',
            f'fake:{"a" * 129}:2001-02-03',
        ]
        for token in refused:
            with self.subTest(token), self.assertRaises(IdentityTokenError):
                FakeIdentityProvider().verify(token)

    def test_a_disabled_provider_never_verifies(self):
        with self.assertRaises(IdentityUnavailableError):
            DisabledIdentityProvider().verify(identity_token())

    def test_the_setting_picks_the_provider(self):
        with override_settings(IDENTITY_PROVIDER='disabled'):
            self.assertIsInstance(get_identity_provider(), DisabledIdentityProvider)
        with override_settings(IDENTITY_PROVIDER='fake'):
            self.assertIsInstance(get_identity_provider(), FakeIdentityProvider)


class StatusTests(SimpleTestCase):
    def test_an_unverified_account_is_no_adult(self):
        self.assertEqual(status_from(None, date(2026, 10, 17)), UNVERIFIED)

    def test_a_minor_grows_up_without_verifying_again(self):
        # 2008년 3월생. 2027년 1월 1일에 성인용 내용이, 2027년 3월 생일에 결제가 열린다
        verification = IdentityVerification(
            legal_adult_from=date(2027, 3, 15), adult_content_from=date(2027, 1, 1), provider='fake'
        )

        self.assertEqual(status_from(verification, date(2026, 12, 31)), IdentityStatus(True, False, False))
        self.assertEqual(status_from(verification, date(2027, 1, 1)), IdentityStatus(True, False, True))
        self.assertEqual(status_from(verification, date(2027, 3, 15)), IdentityStatus(True, True, True))

    def test_an_adult_has_no_dates(self):
        verification = IdentityVerification(legal_adult_from=None, adult_content_from=None, provider='fake')

        self.assertEqual(status_from(verification, date(2026, 10, 17)), IdentityStatus(True, True, True))


class VerifyTestCase(APITestCase):
    def setUp(self):
        self.user = make_user()
        authorize(self.client, self.user)

    def verify(self, birth_date: date = ADULT_BIRTH_DATE, di: str = 'person-1'):
        return post_verify(self.client, identity_token(di, birth_date))


class VerifyTests(VerifyTestCase):
    def test_an_adult_is_verified(self):
        response = self.verify()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['identity'], {'verified': True, 'legal_adult': True, 'adult_content': True})
        verification = IdentityVerification.objects.get(user=self.user)
        self.assertEqual(verification.provider, 'fake')
        self.assertEqual(verification.person_key, person_key('person-1'))

    def test_an_adults_dates_are_not_kept(self):
        # 이미 지난 날짜를 적어 두면 그것이 곧 생일이다
        self.verify()

        verification = IdentityVerification.objects.get()
        self.assertIsNone(verification.legal_adult_from)
        self.assertIsNone(verification.adult_content_from)

    def test_a_minor_keeps_the_dates_to_grow_up_on(self):
        birth_date = born_years_ago(17)

        response = self.verify(birth_date)

        self.assertEqual(response.data['identity'], {'verified': True, 'legal_adult': False, 'adult_content': False})
        verification = IdentityVerification.objects.get()
        self.assertEqual(verification.legal_adult_from, legal_adult_from(birth_date))
        self.assertEqual(verification.adult_content_from, adult_content_from(birth_date))

    def test_an_eighteen_year_old_in_the_year_of_turning_nineteen_sees_adult_content(self):
        # 올해 만 19세가 되는데 생일이 아직 오지 않았다. 성인용 내용은 되고 결제는 아직이다
        today = korean_today()
        if today.month == 12 and today.day == 31:
            self.skipTest('올해의 남은 날이 없다')
        # 19년 전의 내일. 내일이 만 19세 생일이다
        birth_date = born_years_ago(19, days=-1)

        response = self.verify(birth_date)

        self.assertEqual(response.data['identity'], {'verified': True, 'legal_adult': False, 'adult_content': True})
        verification = IdentityVerification.objects.get()
        self.assertEqual(verification.legal_adult_from, legal_adult_from(birth_date))
        self.assertIsNone(verification.adult_content_from)

    def test_the_di_and_the_birth_date_are_not_stored(self):
        birth_date = born_years_ago(17)

        self.verify(birth_date, di='secret-di-value')

        row = ' '.join(str(value) for value in IdentityVerification.objects.values().get().values())
        self.assertNotIn('secret-di-value', row)
        self.assertNotIn(birth_date.isoformat(), row)

    def test_needs_a_logged_in_user(self):
        self.client.credentials()

        response = self.verify()

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(IdentityVerification.objects.exists())

    def test_a_missing_token_is_a_field_error(self):
        response = self.client.post(reverse('accounts:identity-verify'), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('token', response.data['errors'])

    def test_an_unknown_token_is_refused(self):
        response = post_verify(self.client, 'fake:abc:2001-02-30')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'identity_token_invalid')
        self.assertFalse(IdentityVerification.objects.exists())

    @override_settings(IDENTITY_PROVIDER='disabled')
    def test_a_disabled_provider_answers_503(self):
        response = self.verify()

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data['code'], 'identity_unavailable')


class OncePerAccountTests(VerifyTestCase):
    def test_an_account_verifies_once(self):
        self.verify()

        response = self.verify(di='person-2')

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'identity_already_verified')
        self.assertEqual(IdentityVerification.objects.get().person_key, person_key('person-1'))

    def test_a_verified_account_does_not_ask_the_provider_again(self):
        self.verify()

        with patch('accounts.identity.get_identity_provider') as provider:
            self.verify()

        provider.assert_not_called()


class OnceAccountPerPersonTests(VerifyTestCase):
    def test_another_account_of_the_same_person_is_refused(self):
        self.verify()
        other = make_user(2)
        authorize(self.client, other)

        response = self.verify()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'identity_in_use')
        self.assertFalse(IdentityVerification.objects.filter(user=other).exists())

    def test_the_refusal_is_kept_as_a_security_event(self):
        self.verify()
        other = make_user(2)
        authorize(self.client, other)

        self.verify()

        event = SecurityEvent.objects.get(kind=SecurityEventKind.IDENTITY_IN_USE)
        self.assertEqual(event.user, other)
        self.assertEqual(event.ip, '127.0.0.1')

    def test_deleting_the_account_frees_the_person(self):
        self.verify()
        self.user.delete()
        again = make_user(2)
        authorize(self.client, again)

        response = self.verify()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(IdentityVerification.objects.get().user, again)


class UnderAgeTests(VerifyTestCase):
    def setUp(self):
        super().setUp()
        self.email = self.user.email

    def refuse(self):
        response = self.verify(born_years_ago(14, days=-1))
        self.user.refresh_from_db()
        return response

    def test_a_day_before_the_fourteenth_birthday_is_refused(self):
        response = self.refuse()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'identity_under_age')
        self.assertFalse(IdentityVerification.objects.exists())

    def test_the_fourteenth_birthday_is_old_enough(self):
        response = self.verify(born_years_ago(14))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_the_account_is_blocked_and_its_sessions_cut(self):
        version = self.user.token_version

        self.refuse()

        self.assertFalse(self.user.is_active)
        self.assertEqual(self.user.token_version, version + 1)
        self.assertIsNotNone(self.user.sessions_revoked_at)
        self.assertEqual(self.client.get(ME_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_what_was_collected_is_erased(self):
        SignupCode.objects.create(
            email=self.email,
            expires_at=self.user.date_joined,
            last_issued_at=self.user.date_joined,
            window_started_at=self.user.date_joined,
        )
        EmailCode.objects.create(
            user=self.user,
            purpose='login',
            expires_at=self.user.date_joined,
            last_issued_at=self.user.date_joined,
            window_started_at=self.user.date_joined,
        )
        OutgoingMail.objects.create(
            to_email=self.email.upper(),
            subject='코드',
            body='x',
            next_attempt_at=self.user.date_joined,
            expires_at=self.user.date_joined,
        )

        self.refuse()

        self.assertEqual(self.user.username, f'removed-{self.user.pk}')
        self.assertEqual(self.user.nickname, f'removed-{self.user.pk}')
        self.assertEqual(self.user.email, f'{self.user.pk}@removed.invalid')
        self.assertFalse(self.user.has_usable_password())
        self.assertFalse(SignupCode.objects.exists())
        self.assertFalse(EmailCode.objects.exists())
        self.assertFalse(OutgoingMail.objects.exists())

    def test_the_names_are_free_again(self):
        # 같은 이메일, 아이디, 닉네임으로 다시 가입할 수 있다. 막은 계정이 붙들고 있지 않다
        self.refuse()

        again = make_user(1)

        self.assertNotEqual(again.pk, self.user.pk)

    def test_it_is_kept_as_a_security_event_without_the_ip(self):
        self.refuse()

        event = SecurityEvent.objects.get(kind=SecurityEventKind.IDENTITY_UNDER_AGE)
        self.assertEqual(event.user, self.user)
        self.assertEqual(event.ip, '')

    def test_the_refresh_cookie_is_cleared(self):
        response = self.refuse()

        self.assertEqual(response.cookies[REFRESH_COOKIE_NAME].value, '')


class StatusInResponsesTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_me_shows_the_identity(self):
        client = BrowserClient()
        authorize(client, self.user)

        before = client.get(ME_URL).data['identity']
        post_verify(client, identity_token(birth_date=born_years_ago(17)))
        after = client.get(ME_URL).data['identity']

        self.assertEqual(before, {'verified': False, 'legal_adult': False, 'adult_content': False})
        self.assertEqual(after, {'verified': True, 'legal_adult': False, 'adult_content': False})

    def test_status_reads_the_record(self):
        self.assertEqual(identity_status_of(self.user, date(2026, 10, 17)), UNVERIFIED)


class AdultContentClaimTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def adult_content(self) -> bool:
        return claims_of(issue_token_pair(self.user).access)[ADULT_CONTENT_CLAIM]

    def verify(self, birth_date: date) -> None:
        verify_identity(user=self.user, token=identity_token(birth_date=birth_date))

    def test_unverified_accounts_see_no_adult_content(self):
        self.assertIs(self.adult_content(), False)

    def test_verified_adults_see_adult_content(self):
        self.verify(ADULT_BIRTH_DATE)

        self.assertIs(self.adult_content(), True)

    def test_minors_see_it_from_january_first_of_the_year_they_turn_nineteen(self):
        birth_date = born_years_ago(17)
        self.verify(birth_date)
        opens_on = adult_content_from(birth_date)

        with patch('accounts.tokens.korean_today', return_value=opens_on - timedelta(days=1)):
            self.assertIs(self.adult_content(), False)
        with patch('accounts.tokens.korean_today', return_value=opens_on):
            self.assertIs(self.adult_content(), True)

    def test_the_refresh_token_does_not_carry_it(self):
        refresh = claims_of(issue_token_pair(self.user).refresh)

        self.assertNotIn(ADULT_CONTENT_CLAIM, refresh)

    def test_refreshing_after_verifying_carries_it(self):
        # 인증의 응답은 토큰을 주지 않는다. 화면이 갱신을 부르면 실린다
        client = BrowserClient()
        logged_in = log_in(client, 'player_01', PASSWORD)
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {logged_in.data["access_token"]}')
        self.assertIs(claims_of(logged_in.data['access_token'])[ADULT_CONTENT_CLAIM], False)

        post_verify(client)
        refreshed = client.post(REFRESH_URL)

        self.assertEqual(refreshed.status_code, status.HTTP_200_OK)
        self.assertIs(claims_of(refreshed.data['access_token'])[ADULT_CONTENT_CLAIM], True)


class ServiceTests(TestCase):
    def test_in_use_is_an_error_of_the_service(self):
        verify_identity(user=make_user(1), token=identity_token())

        with self.assertRaises(IdentityInUseError):
            verify_identity(user=make_user(2), token=identity_token())


class TwoAccountsAtOnceTests(TransactionTestCase):
    """두 계정이 같은 사람으로 함께 인증한다. 진짜 트랜잭션 둘이 있어야 해서 테스트를 트랜잭션으로 감싸지 않는다."""

    def test_only_one_account_gets_the_person(self):
        users = [make_user(1), make_user(2)]
        barrier = threading.Barrier(2)
        results = [None, None]
        real_create = IdentityVerification.objects.create

        def create_together(**fields):
            # 둘 다 "아직 아무도 그 사람이 아니다" 를 본 뒤에 함께 적는다
            barrier.wait(timeout=10)
            return real_create(**fields)

        def run(index: int) -> None:
            try:
                verify_identity(user=users[index], token=identity_token())
                results[index] = 'ok'
            except IdentityInUseError:
                results[index] = 'in_use'
            finally:
                connection.close()

        with patch.object(IdentityVerification.objects, 'create', side_effect=create_together):
            threads = [threading.Thread(target=run, args=(index,)) for index in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=20)

        self.assertEqual(sorted(results), ['in_use', 'ok'])
        self.assertEqual(IdentityVerification.objects.count(), 1)
