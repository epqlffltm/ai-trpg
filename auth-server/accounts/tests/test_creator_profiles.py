# auth-server/accounts/tests/test_creator_profiles.py

"""
제작자의 프로필(#992)을 검증한다. 내 소개를 /me 에서 읽고 PATCH /me/profile 로 고친다. 남은 /creators/<공개 ID> 로 본다.

  - 소개는 200자까지, 비울 수 있다. 앞뒤 공백은 지운다
  - 프로필은 로그인 없이 본다. 닉네임과 소개만 나간다
  - 없는 공개 ID 와 비운 계정(탈퇴, 만 14세 미만)은 같은 404 다. 비우면 소개도 지워진다
"""

import uuid

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.erasure import blank_account
from accounts.models import User
from accounts.tests.helpers import authorize

ME_URL = reverse('accounts:me')
PROFILE_URL = reverse('accounts:my-profile')


def make_user(number: int = 1) -> User:
    return User.objects.create_user(
        username=f'maker_{number:02d}',
        email=f'maker{number}@example.com',
        nickname=f'제작자{number}',
        password='correct-horse-battery',
        email_verified_at=timezone.now(),
    )


def creator_url(public_id: uuid.UUID) -> str:
    return reverse('accounts:creator', kwargs={'public_id': public_id})


class MyProfileTests(APITestCase):
    def setUp(self):
        self.user = make_user()
        authorize(self.client, self.user)

    def test_the_bio_starts_empty(self):
        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['bio'], '')

    def test_writes_and_clears_the_bio(self):
        written = self.client.patch(PROFILE_URL, {'bio': '  밤의 이야기를 씁니다  '}, format='json')
        shown = self.client.get(ME_URL)
        cleared = self.client.patch(PROFILE_URL, {'bio': ''}, format='json')

        self.assertEqual(written.status_code, status.HTTP_200_OK)
        self.assertEqual(written.data, {'bio': '밤의 이야기를 씁니다'})
        self.assertEqual(shown.data['bio'], '밤의 이야기를 씁니다')
        self.assertEqual(cleared.data, {'bio': ''})
        self.user.refresh_from_db()
        self.assertEqual(self.user.bio, '')

    def test_rejects_a_long_or_missing_bio(self):
        long = self.client.patch(PROFILE_URL, {'bio': '가' * 201}, format='json')
        missing = self.client.patch(PROFILE_URL, {}, format='json')
        just_fits = self.client.patch(PROFILE_URL, {'bio': '가' * 200}, format='json')

        self.assertEqual(long.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(just_fits.status_code, status.HTTP_200_OK)

    def test_needs_login(self):
        self.client.credentials()

        response = self.client.patch(PROFILE_URL, {'bio': '소개'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class CreatorTests(APITestCase):
    def setUp(self):
        self.user = make_user()
        self.user.bio = '밤의 이야기를 씁니다'
        self.user.save(update_fields=['bio'])

    def test_anyone_sees_the_name_and_bio_only(self):
        response = self.client.get(creator_url(self.user.public_id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data, {'public_id': str(self.user.public_id), 'nickname': '제작자1', 'bio': '밤의 이야기를 씁니다'}
        )
        self.assertIn('public', response['Cache-Control'])

    def test_an_unknown_creator_is_404(self):
        response = self.client.get(creator_url(uuid.uuid4()))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['code'], 'creator_not_found')

    def test_a_removed_account_is_404_and_loses_its_bio(self):
        blank_account(self.user)

        response = self.client.get(creator_url(self.user.public_id))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.user.refresh_from_db()
        self.assertEqual(self.user.bio, '')

    def test_a_bad_address_is_404(self):
        response = self.client.get('/api/v1/auth/creators/not-a-uuid')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
