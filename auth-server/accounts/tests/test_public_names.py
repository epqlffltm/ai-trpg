# auth-server/accounts/tests/test_public_names.py

"""
다른 사람의 공개 이름을 한꺼번에 찾는 주소(GET public-names, #532)를 검증한다.

  - 로그인 없이 읽는다. 받은 차례대로, 같은 것은 한 번만 답한다
  - 닉네임만 내준다. 없는 공개 ID 와 만 14세 미만으로 막은 계정은 이름이 null 이다. 정지된 계정은 이름이 보인다
  - 목록이 비었거나, UUID 가 아니거나, 100개를 넘으면 400 이다
"""

import uuid

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.identity import close_under_age_account
from accounts.models import User
from accounts.public_names import MAX_IDS
from accounts.suspension import suspend_account

URL = reverse('accounts:public-names')


def make_user(number: int) -> User:
    return User.objects.create_user(
        username=f'player_{number:02d}',
        email=f'player{number}@example.com',
        nickname=f'플레이어{number}',
        password='correct-horse-battery',
        email_verified_at=timezone.now(),
    )


def ids_param(*ids) -> str:
    return ','.join(str(public_id) for public_id in ids)


class PublicNamesTest(APITestCase):
    def setUp(self):
        self.first = make_user(1)
        self.second = make_user(2)

    def get(self, raw_ids: str):
        return self.client.get(URL, {'ids': raw_ids})

    def test_finds_names_in_the_asked_order_without_a_login(self):
        response = self.get(ids_param(self.second.public_id, self.first.public_id, self.second.public_id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                'names': [
                    {'public_id': str(self.second.public_id), 'nickname': '플레이어2'},
                    {'public_id': str(self.first.public_id), 'nickname': '플레이어1'},
                ]
            },
        )
        self.assertIn('max-age', response['Cache-Control'])

    def test_gives_nothing_but_the_nickname(self):
        response = self.get(ids_param(self.first.public_id))

        self.assertEqual(set(response.json()['names'][0]), {'public_id', 'nickname'})

    def test_an_unknown_id_and_a_removed_account_have_no_name(self):
        close_under_age_account(self.second)
        unknown = uuid.uuid4()

        response = self.get(ids_param(unknown, self.second.public_id))

        self.assertEqual([name['nickname'] for name in response.json()['names']], [None, None])

    def test_a_suspended_account_keeps_its_name(self):
        suspend_account(self.first, note='테스트')

        response = self.get(ids_param(self.first.public_id))

        self.assertEqual(response.json()['names'][0]['nickname'], '플레이어1')

    def test_a_bad_token_is_ignored(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer not-a-token')

        response = self.get(ids_param(self.first.public_id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_refuses_an_empty_list_a_bad_id_and_too_many(self):
        too_many = ids_param(*(uuid.uuid4() for _ in range(MAX_IDS + 1)))
        for name, raw in {'empty': '', 'commas only': ',,', 'not a uuid': 'abc', 'too many': too_many}.items():
            with self.subTest(name):
                response = self.get(raw)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data['code'], 'public_ids_invalid')

    def test_the_most_ids_are_one_query(self):
        raw = ids_param(*(uuid.uuid4() for _ in range(MAX_IDS)))

        with CaptureQueriesContext(connection) as queries:
            response = self.get(raw)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(queries), 1)
