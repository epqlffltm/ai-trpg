# auth-server/accounts/tests/test_consents.py

"""
이용약관과 개인정보 수집·이용 같은 동의(#450)를 검증한다.

  - 지금의 판: 로그인 없이 읽는다
  - 가입: 필수 항목에 지금의 판으로 동의해야 한다. 선택 항목은 함께 받는다. 기록이 계정과 함께 생긴다
  - 본인: 항목마다의 상태를 읽고, 선택 항목을 동의하고 철회한다. 필수 항목은 철회하지 못한다
  - 판이 오르면 필수 항목을 다시 받아야 한다고 알린다(/me 의 consents_pending)
  - 기록은 덮어쓰지 않고 쌓는다. 만 14세 미만으로 막은 계정의 기록은 지운다
"""

from types import MappingProxyType
from unittest.mock import patch

from django.core import mail
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.consents import POLICIES, Policy
from accounts.identity import close_under_age_account
from accounts.models import ConsentAction, ConsentItem, ConsentRecord, User
from accounts.tests.helpers import authorize, code_from, required_consents

DOCUMENTS_URL = reverse('accounts:consents')
MY_CONSENTS_URL = reverse('accounts:my-consents')
ME_URL = reverse('accounts:me')
SIGNUP_URL = reverse('accounts:signup')
VERIFY_URL = reverse('accounts:signup-verify')
COMPLETE_URL = reverse('accounts:signup-complete')

PASSWORD = 'correct-horse-battery'
EMAIL = 'someone@example.com'


def my_consent_url(item: str) -> str:
    return reverse('accounts:my-consent', kwargs={'item': item})


def make_user() -> User:
    return User.objects.create_user(
        username='player_01',
        email=EMAIL,
        nickname='플레이어',
        password=PASSWORD,
        email_verified_at=timezone.now(),
    )


def with_terms_version(version: int):
    """이용약관의 판을 올린 표로 바꾼다. 중요한 변경으로 판이 오른 때를 흉내 낸다."""
    terms = POLICIES[ConsentItem.TERMS]
    raised = {**POLICIES, ConsentItem.TERMS: Policy(terms.item, version, terms.effective_on, terms.required)}
    return patch('accounts.consents.POLICIES', MappingProxyType(raised))


def states_by_item(response) -> dict[str, dict]:
    return {state['item']: state for state in response.data['items']}


class ConsentDocumentsTest(APITestCase):
    def test_lists_every_item_with_its_version_without_a_login(self):
        response = self.client.get(DOCUMENTS_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = {item['item']: item for item in response.data['items']}
        self.assertEqual(set(items), {'terms', 'privacy', 'marketing', 'ai_training'})
        self.assertEqual({item for item, body in items.items() if body['required']}, {'terms', 'privacy'})
        self.assertEqual(items['terms']['version'], POLICIES[ConsentItem.TERMS].version)
        self.assertIn('effective_on', items['terms'])


class SignupConsentTest(APITestCase):
    def setUp(self):
        self.client.post(SIGNUP_URL, {'email': EMAIL}, format='json')
        verified = self.client.post(VERIFY_URL, {'email': EMAIL, 'code': code_from(mail.outbox[-1])}, format='json')
        self.ticket = verified.data['signup_ticket']

    def complete(self, consents):
        payload = {
            'signup_ticket': self.ticket,
            'username': 'player_01',
            'nickname': '플레이어',
            'password': PASSWORD,
            'age_over_14': True,
        }
        if consents is not None:
            payload['consents'] = consents
        return self.client.post(COMPLETE_URL, payload, format='json')

    def test_records_the_required_and_chosen_items(self):
        response = self.complete({**required_consents(), 'marketing': 1})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username='player_01')
        records = ConsentRecord.objects.filter(user=user)
        self.assertEqual({record.item for record in records}, {'terms', 'privacy', 'marketing'})
        self.assertTrue(all(record.action == ConsentAction.AGREED for record in records))

    def test_refuses_a_signup_without_a_required_item(self):
        for missing in ('terms', 'privacy'):
            with self.subTest(missing=missing):
                consents = required_consents()
                del consents[missing]

                response = self.complete(consents)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('consents', response.data['errors'])
        self.assertEqual(User.objects.count(), 0)

    def test_refuses_an_old_version_an_unknown_item_and_no_consents(self):
        cases = {
            'old version': {**required_consents(), 'terms': POLICIES[ConsentItem.TERMS].version + 1},
            'unknown item': {**required_consents(), 'newsletter': 1},
            'no consents': None,
        }
        for name, consents in cases.items():
            with self.subTest(name):
                response = self.complete(consents)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('consents', response.data['errors'])
        self.assertEqual(ConsentRecord.objects.count(), 0)

    def test_a_refused_signup_keeps_the_ticket_usable(self):
        self.complete({})

        response = self.complete(required_consents())

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class MyConsentsTest(APITestCase):
    def setUp(self):
        self.user = make_user()
        ConsentRecord.objects.bulk_create(
            ConsentRecord(user=self.user, item=item, version=version, action=ConsentAction.AGREED, at=timezone.now())
            for item, version in required_consents().items()
        )
        authorize(self.client, self.user)

    def test_reads_the_state_of_every_item(self):
        response = self.client.get(MY_CONSENTS_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        states = states_by_item(response)
        self.assertEqual(states['terms']['agreed_version'], POLICIES[ConsentItem.TERMS].version)
        self.assertFalse(states['terms']['pending'])
        self.assertIsNone(states['marketing']['agreed_version'])
        self.assertIsNone(states['marketing']['agreed_at'])

    def test_needs_a_login(self):
        self.client.credentials()

        self.assertEqual(self.client.get(MY_CONSENTS_URL).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            self.client.put(my_consent_url('marketing'), {'version': 1}, format='json').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_agrees_to_an_optional_item_once(self):
        first = self.client.put(my_consent_url('marketing'), {'version': 1}, format='json')
        again = self.client.put(my_consent_url('marketing'), {'version': 1}, format='json')

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(states_by_item(again)['marketing']['agreed_version'], 1)
        self.assertEqual(ConsentRecord.objects.filter(user=self.user, item='marketing').count(), 1)

    def test_withdrawing_adds_a_line_and_keeps_the_agreement(self):
        self.client.put(my_consent_url('ai_training'), {'version': 1}, format='json')

        response = self.client.delete(my_consent_url('ai_training'))
        self.client.delete(my_consent_url('ai_training'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(states_by_item(response)['ai_training']['agreed_version'])
        actions = list(
            ConsentRecord.objects.filter(user=self.user, item='ai_training')
            .order_by('id')
            .values_list('action', 'version')
        )
        self.assertEqual(actions, [(ConsentAction.AGREED, 1), (ConsentAction.WITHDRAWN, 1)])

    def test_a_required_item_cannot_be_withdrawn(self):
        response = self.client.delete(my_consent_url('terms'))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'consent_required')

    def test_refuses_an_old_version_and_an_unknown_item(self):
        old = self.client.put(my_consent_url('marketing'), {'version': 2}, format='json')
        unknown = self.client.put(my_consent_url('newsletter'), {'version': 1}, format='json')
        unknown_withdrawal = self.client.delete(my_consent_url('newsletter'))

        self.assertEqual(old.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(old.data['code'], 'consent_outdated')
        self.assertEqual(unknown.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(unknown_withdrawal.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(unknown.data['code'], 'consent_item_unknown')

    def test_a_new_terms_version_asks_for_the_consent_again(self):
        version = POLICIES[ConsentItem.TERMS].version + 1
        with with_terms_version(version):
            self.assertEqual(self.client.get(ME_URL).data['consents_pending'], ['terms'])

            response = self.client.put(my_consent_url('terms'), {'version': version}, format='json')

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(self.client.get(ME_URL).data['consents_pending'], [])
        # 앞의 판에 한 동의는 그대로 남는다
        self.assertEqual(ConsentRecord.objects.filter(user=self.user, item='terms').count(), 2)

    def test_an_account_without_records_is_asked_for_the_required_items(self):
        # 이 기능 전에 가입한 계정이다
        ConsentRecord.objects.filter(user=self.user).delete()

        self.assertEqual(self.client.get(ME_URL).data['consents_pending'], ['terms', 'privacy'])


class UnderAgeConsentTest(APITestCase):
    def test_closing_an_under_age_account_erases_its_consents(self):
        user = make_user()
        ConsentRecord.objects.create(user=user, item='terms', version=1, action=ConsentAction.AGREED, at=timezone.now())

        close_under_age_account(user)

        self.assertFalse(ConsentRecord.objects.filter(user=user).exists())
