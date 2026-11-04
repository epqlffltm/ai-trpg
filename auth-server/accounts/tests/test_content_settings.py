# auth-server/accounts/tests/test_content_settings.py

"""
목록을 거르는 내 설정(#986, #987)을 검증한다. /me 에 실리고, PATCH /me/content-settings 로 고친다.

  - 처음에는 성인 작품 표시가 켜져 있고 성향은 전체다
  - 보낸 칸만 바뀐다. 성인 확인 전에는 성인 작품 표시를 켤 수 없다(끄는 것은 된다)
"""

from datetime import date

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from accounts.tests.helpers import authorize, identity_token, verify_identity

ME_URL = reverse('accounts:me')
SETTINGS_URL = reverse('accounts:my-content-settings')
# 성인용 내용을 볼 수 있는 생일과 아직 볼 수 없는 생일(만 14세 이상)
ADULT = date(1990, 1, 1)
TEEN = date(timezone.localdate().year - 16, 1, 1)


def make_user(number: int = 1) -> User:
    return User.objects.create_user(
        username=f'player_{number:02d}',
        email=f'player{number}@example.com',
        nickname=f'플레이어{number}',
        password='correct-horse-battery',
        email_verified_at=timezone.now(),
    )


class ContentSettingsTests(APITestCase):
    def setUp(self):
        self.user = make_user()
        authorize(self.client, self.user)

    def verified(self, birth_date: date) -> None:
        response = verify_identity(self.client, identity_token('person-1', birth_date))
        assert response.status_code == status.HTTP_201_CREATED, response.data

    def test_me_has_the_defaults(self):
        response = self.client.get(ME_URL)

        self.assertEqual(response.data['content_settings'], {'show_adult_content': True, 'orientation': 'all'})

    def test_changes_only_what_was_sent(self):
        self.verified(ADULT)

        hidden = self.client.patch(SETTINGS_URL, {'show_adult_content': False}, format='json')
        oriented = self.client.patch(SETTINGS_URL, {'orientation': 'female'}, format='json')

        self.assertEqual(hidden.data, {'show_adult_content': False, 'orientation': 'all'})
        self.assertEqual(oriented.data, {'show_adult_content': False, 'orientation': 'female'})
        self.assertEqual(self.client.get(ME_URL).data['content_settings'], oriented.data)

    def test_an_adult_turns_it_back_on(self):
        self.verified(ADULT)
        self.client.patch(SETTINGS_URL, {'show_adult_content': False}, format='json')

        response = self.client.patch(SETTINGS_URL, {'show_adult_content': True}, format='json')

        self.assertEqual((response.status_code, response.data['show_adult_content']), (status.HTTP_200_OK, True))

    def test_it_cannot_be_turned_on_without_adult_content(self):
        for setup in (lambda: None, lambda: self.verified(TEEN)):
            with self.subTest(setup=setup):
                setup()
                User.objects.filter(pk=self.user.pk).update(show_adult_content=False)

                refused = self.client.patch(SETTINGS_URL, {'show_adult_content': True}, format='json')
                turned_off = self.client.patch(SETTINGS_URL, {'show_adult_content': False}, format='json')

                self.assertEqual(refused.status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(refused.data['code'], 'adult_content_required')
                self.assertEqual(turned_off.status_code, status.HTTP_200_OK)
                self.user.refresh_from_db()
                self.assertFalse(self.user.show_adult_content)

    def test_rejects_an_unknown_orientation(self):
        response = self.client.patch(SETTINGS_URL, {'orientation': 'both'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_needs_login(self):
        self.client.credentials()

        self.assertEqual(self.client.patch(SETTINGS_URL, {}, format='json').status_code, status.HTTP_401_UNAUTHORIZED)
