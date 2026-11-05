# auth-server/accounts/tests/test_creator_search.py

"""
제작자를 닉네임으로 찾기(#984, GET /creators?q=)를 검증한다.

  - 소개를 쓴 사람만 나온다. 닉네임이 같은 것, 그것으로 시작하는 것, 나머지 차례다. 대소문자를 가리지 않는다
  - 닉네임과 소개만 나간다. 로그인 없이 연다. limit 만큼만 준다
  - 비운 계정(탈퇴)은 나오지 않는다. 검색어가 비었거나 20자를 넘으면 400 이다
"""

from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.erasure import blank_account
from accounts.models import User

SEARCH_URL = reverse('accounts:creator-search')


def make_user(number: int, nickname: str, bio: str = '') -> User:
    return User.objects.create_user(
        username=f'player_{number:02d}',
        email=f'player{number}@example.com',
        nickname=nickname,
        password='correct-horse-battery',
        email_verified_at=timezone.now(),
        bio=bio,
    )


class CreatorSearchTests(APITestCase):
    def setUp(self):
        self.exact = make_user(1, '달빛', '밤의 이야기')
        self.prefix = make_user(2, '달빛여우', '여우 이야기')
        self.inside = make_user(3, '푸른달빛', '바다')
        self.quiet = make_user(4, '달빛없음')
        self.other = make_user(5, '해님', '낮')

    def names(self, **params) -> list[str]:
        response = self.client.get(SEARCH_URL, params)
        assert response.status_code == status.HTTP_200_OK, response.data
        return [item['nickname'] for item in response.data['items']]

    def test_finds_creators_with_a_bio_in_order(self):
        self.assertEqual(self.names(q=' 달빛 '), ['달빛', '달빛여우', '푸른달빛'])
        self.assertEqual(self.names(q='달빛', limit=2), ['달빛', '달빛여우'])
        self.assertEqual(self.names(q='없는 이름'), [])

    def test_ignores_case_and_shows_only_public_fields(self):
        make_user(6, 'Moon', '영어 이름')

        response = self.client.get(SEARCH_URL, {'q': 'moon'})

        self.assertEqual(
            response.data['items'],
            [{'public_id': str(User.objects.get(nickname='Moon').public_id), 'nickname': 'Moon', 'bio': '영어 이름'}],
        )

    def test_an_emptied_account_is_not_found(self):
        with transaction.atomic():
            blank_account(User.objects.select_for_update().get(pk=self.exact.pk))

        self.assertEqual(self.names(q='달빛'), ['달빛여우', '푸른달빛'])

    def test_rejects_a_bad_query(self):
        for params in ({}, {'q': '  '}, {'q': '가' * 21}, {'q': '달빛', 'limit': 0}, {'q': '달빛', 'limit': 21}):
            response = self.client.get(SEARCH_URL, params)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, params)
