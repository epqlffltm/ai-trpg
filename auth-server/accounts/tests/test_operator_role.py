# auth-server/accounts/tests/test_operator_role.py

"""
access 토큰의 역할(roles)을 시험한다(#389).

  - 운영자의 그룹은 마이그레이션이 만든다
  - 그룹 operators 에 든 계정만 ["operator"] 다. is_staff 나 다른 그룹은 운영자가 아니다
  - 갱신할 때마다 그룹을 다시 읽는다. 빼면 다음 갱신부터 빠진다
  - refresh 토큰에는 싣지 않는다
"""

import jwt
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from accounts.models import User
from accounts.roles import OPERATOR_ROLE, OPERATORS_GROUP, roles_of
from accounts.tests.helpers import BrowserClient, log_in
from accounts.tokens import ROLES_CLAIM, issue_token_pair

REFRESH_URL = reverse('accounts:refresh')
PASSWORD = 'correct-horse-battery'


def make_user(number: int = 1, **fields) -> User:
    return User.objects.create_user(
        username=f'player_{number:02d}',
        email=f'player{number}@example.com',
        nickname=f'플레이어{number}',
        password=PASSWORD,
        email_verified_at=timezone.now(),
        **fields,
    )


def claims_of(token: str) -> dict:
    """서명은 다른 테스트가 본다. 여기서는 실린 값만 읽는다."""
    return jwt.decode(token, options={'verify_signature': False})


def operators() -> Group:
    return Group.objects.get(name=OPERATORS_GROUP)


class RolesClaimTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def roles(self) -> object:
        return claims_of(issue_token_pair(self.user).access)[ROLES_CLAIM]

    def test_the_migration_makes_the_operators_group(self):
        self.assertTrue(Group.objects.filter(name=OPERATORS_GROUP).exists())

    def test_a_player_has_no_roles(self):
        self.assertEqual(self.roles(), [])

    def test_a_member_of_the_operators_group_is_an_operator(self):
        self.user.groups.add(operators())

        self.assertEqual(self.roles(), [OPERATOR_ROLE])

    def test_staff_without_the_group_is_not_an_operator(self):
        # 관리자 화면에 들어가는 권한과 서비스의 운영 권한은 다르다
        staff = make_user(2, is_staff=True, is_superuser=True)

        self.assertEqual(roles_of(staff), [])

    def test_another_group_is_not_an_operator(self):
        self.user.groups.add(Group.objects.create(name='editors'))

        self.assertEqual(self.roles(), [])

    def test_the_refresh_token_does_not_carry_it(self):
        self.user.groups.add(operators())

        self.assertNotIn(ROLES_CLAIM, claims_of(issue_token_pair(self.user).refresh))


class RolesRefreshTests(TestCase):
    def test_refreshing_reads_the_group_again(self):
        user = make_user()
        user.groups.add(operators())
        client = BrowserClient()
        logged_in = log_in(client, 'player_01', PASSWORD)
        self.assertEqual(claims_of(logged_in.data['access_token'])[ROLES_CLAIM], [OPERATOR_ROLE])

        user.groups.remove(operators())
        refreshed = client.post(REFRESH_URL)

        self.assertEqual(refreshed.status_code, status.HTTP_200_OK)
        self.assertEqual(claims_of(refreshed.data['access_token'])[ROLES_CLAIM], [])
