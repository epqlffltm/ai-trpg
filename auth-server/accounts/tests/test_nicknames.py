# auth-server/accounts/tests/test_nicknames.py

"""
본인의 닉네임 바꾸기(accounts/nicknames.py, POST /me/nickname)를 검증한다.

  - 비밀번호를 다시 받는다. 틀린 횟수는 비밀번호 변경과 같은 한도로 센다
  - 30일에 한 번 바꾼다. 다음에 바꿀 수 있는 시각은 /me 와 바꾼 답에 있다
  - 버린 이름은 30일 동안 다른 사람이 가입하거나 바꾸며 가져가지 못한다. 버린 사람은 되찾을 수 있다
  - 바꾼 뒤에 받는 access 토큰에 새 이름이 실린다(다른 서버가 그것을 본다)
"""

from datetime import timedelta

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from accounts.attempt_policies import PASSWORD_CHANGE_FAILURES_PER_USER
from accounts.models import ReleasedNickname, User
from accounts.nicknames import NICKNAME_CHANGE_INTERVAL, RELEASED_NICKNAME_HOLD
from accounts.tests.helpers import (
    authorize,
    delete_attempt_keys,
    request_signup_ticket,
    reset_redis_breaker,
)
from accounts.tests.helpers import complete_signup as send_signup_complete
from accounts.tokens import issue_token_pair

ME_URL = reverse('accounts:me')
NICKNAME_URL = reverse('accounts:my-nickname')
PASSWORD = 'correct-horse-battery'


def make_user(number: int, nickname: str) -> User:
    return User.objects.create_user(
        username=f'player_{number:02d}',
        email=f'player{number}@example.com',
        nickname=nickname,
        password=PASSWORD,
        email_verified_at=timezone.now(),
    )


def push_back_last_change(user: User, by: timedelta) -> None:
    """마지막으로 바꾼 시각을 그만큼 앞으로 당긴다. 30일을 기다리는 대신 쓴다."""
    user.refresh_from_db()
    user.nickname_changed_at -= by
    user.save(update_fields=['nickname_changed_at'])


def end_hold(nickname: str) -> None:
    """버린 이름을 묶어 둔 끝을 지난 것으로 만든다."""
    ReleasedNickname.objects.filter(nickname=nickname).update(held_until=timezone.now() - timedelta(seconds=1))


class NicknameTestCase(APITestCase):
    def setUp(self):
        self.user = make_user(1, '첫이름')
        authorize(self.client, self.user)

    def change(self, nickname: str, password: str = PASSWORD):
        return self.client.post(NICKNAME_URL, {'nickname': nickname, 'password': password}, format='json')


class ChangeTests(NicknameTestCase):
    def test_changes_the_nickname_and_tells_when_it_can_change_again(self):
        before = timezone.now()

        response = self.change('새이름')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['nickname'], '새이름')
        self.user.refresh_from_db()
        self.assertEqual(self.user.nickname, '새이름')
        self.assertGreaterEqual(self.user.nickname_changed_at, before)
        expected = (self.user.nickname_changed_at + NICKNAME_CHANGE_INTERVAL).isoformat().replace('+00:00', 'Z')
        self.assertEqual(response.data['nickname_change_available_at'], expected)
        self.assertEqual(self.client.get(ME_URL).json()['nickname_change_available_at'], expected)

    def test_a_new_account_can_change_right_away(self):
        response = self.client.get(ME_URL)

        self.assertIsNone(response.data['nickname_change_available_at'])

    def test_the_next_access_token_carries_the_new_nickname(self):
        # 다른 서버는 토큰의 닉네임을 본다. 화면은 바꾼 뒤 갱신해 새 토큰을 받는다
        self.change('새이름')
        self.user.refresh_from_db()

        token = AccessToken(issue_token_pair(self.user).access)

        self.assertEqual(token['nickname'], '새이름')

    def test_does_not_end_the_sessions(self):
        # 이름은 비밀이 아니다. 바꿔도 이 기기와 다른 기기의 로그인은 이어진다
        version = self.user.token_version

        self.change('새이름')

        self.user.refresh_from_db()
        self.assertEqual(self.user.token_version, version)
        self.assertEqual(self.client.get(ME_URL).status_code, status.HTTP_200_OK)

    def test_needs_login(self):
        self.client.credentials()

        response = self.change('새이름')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class RefusalTests(NicknameTestCase):
    def test_refuses_a_wrong_password(self):
        response = self.change('새이름', password='wrong-password')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data['errors'])
        self.user.refresh_from_db()
        self.assertEqual(self.user.nickname, '첫이름')
        self.assertIsNone(self.user.nickname_changed_at)

    def test_refuses_a_nickname_against_the_rules(self):
        # 가입과 같은 규칙이다. 공백, 너무 짧은 이름, 운영자를 사칭하는 이름
        for nickname in ('새 이름', '가', '운영자', 'admin1'):
            with self.subTest(nickname=nickname):
                response = self.change(nickname)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('nickname', response.data['errors'])

    def test_refuses_the_same_nickname(self):
        response = self.change('첫이름')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['errors']['nickname'], ['지금의 닉네임과 같습니다.'])
        self.user.refresh_from_db()
        self.assertIsNone(self.user.nickname_changed_at)

    def test_refuses_a_nickname_someone_uses(self):
        make_user(2, '남의이름')

        response = self.change('남의이름')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['errors']['nickname'], ['이미 사용 중인 닉네임입니다.'])

    def test_refuses_a_second_change_within_30_days(self):
        self.change('새이름')

        response = self.change('또새이름')

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'nickname_change_too_soon')
        self.user.refresh_from_db()
        self.assertEqual(self.user.nickname, '새이름')

    def test_allows_the_next_change_after_30_days(self):
        self.change('새이름')
        push_back_last_change(self.user, NICKNAME_CHANGE_INTERVAL)

        response = self.change('또새이름')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # 방금 다시 바꿨으니 또 30일을 기다린다
        self.assertIsNotNone(self.client.get(ME_URL).data['nickname_change_available_at'])

    def test_a_refused_change_does_not_spend_the_30_days(self):
        make_user(2, '남의이름')
        self.change('남의이름')

        response = self.change('새이름')

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ReleasedNicknameTests(NicknameTestCase):
    def setUp(self):
        super().setUp()
        self.other = make_user(2, '다른사람')
        self.assertEqual(self.change('새이름').status_code, status.HTTP_200_OK)

    def test_holds_the_old_nickname_for_30_days(self):
        held = ReleasedNickname.objects.get(nickname='첫이름')

        self.assertEqual(held.released_by, self.user)
        self.assertEqual(held.held_until, self.user_changed_at() + RELEASED_NICKNAME_HOLD)

    def test_others_cannot_take_a_held_nickname(self):
        authorize(self.client, self.other)

        response = self.change('첫이름')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # 쓰이고 있는 것과 같은 글이다. 누가 버린 이름인지 드러내지 않는다
        self.assertEqual(response.data['errors']['nickname'], ['이미 사용 중인 닉네임입니다.'])

    def test_a_new_account_cannot_take_a_held_nickname(self):
        self.client.credentials()
        ticket = request_signup_ticket(self.client, 'arrival@example.com')

        response = send_signup_complete(
            self.client, ticket, username='newcomer', nickname='첫이름', password='another-horse-battery'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('nickname', response.data['errors'])
        self.assertFalse(User.objects.filter(username='newcomer').exists())

    def test_others_can_take_it_after_the_hold(self):
        end_hold('첫이름')
        authorize(self.client, self.other)

        response = self.change('첫이름')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_the_owner_can_take_it_back(self):
        push_back_last_change(self.user, NICKNAME_CHANGE_INTERVAL)

        response = self.change('첫이름')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # 되찾은 이름은 더 묶지 않는다. 방금 버린 이름이 묶인다
        self.assertEqual(
            list(ReleasedNickname.objects.values_list('nickname', flat=True)),
            ['새이름'],
        )

    def test_releasing_the_same_name_again_renews_the_hold(self):
        end_hold('첫이름')
        push_back_last_change(self.user, NICKNAME_CHANGE_INTERVAL)
        self.change('첫이름')
        push_back_last_change(self.user, NICKNAME_CHANGE_INTERVAL)

        self.change('세번째')

        held = ReleasedNickname.objects.get(nickname='첫이름')
        self.assertGreater(held.held_until, timezone.now())
        self.assertEqual(ReleasedNickname.objects.filter(nickname='첫이름').count(), 1)

    def user_changed_at(self):
        self.user.refresh_from_db()
        return self.user.nickname_changed_at


@override_settings(ATTEMPT_LIMITS_ENABLED=True, TRUSTED_PROXY_COUNT=0)
class AttemptLimitTests(NicknameTestCase):
    """틀린 비밀번호는 비밀번호 변경과 같은 한도다. 빼앗긴 토큰으로 이 길에서 비밀번호를 맞혀 보지 못한다."""

    def setUp(self):
        delete_attempt_keys()
        self.addCleanup(delete_attempt_keys)
        reset_redis_breaker()
        self.addCleanup(reset_redis_breaker)
        super().setUp()

    def test_blocks_after_too_many_wrong_passwords(self):
        for _ in range(PASSWORD_CHANGE_FAILURES_PER_USER.max_attempts):
            self.assertEqual(self.change('새이름', password='wrong-password').status_code, status.HTTP_400_BAD_REQUEST)

        response = self.change('새이름')

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data['code'], 'too_many_attempts')
        self.user.refresh_from_db()
        self.assertEqual(self.user.nickname, '첫이름')

    def test_the_right_password_clears_the_count(self):
        for _ in range(PASSWORD_CHANGE_FAILURES_PER_USER.max_attempts - 1):
            self.change('새이름', password='wrong-password')

        self.assertEqual(self.change('새이름').status_code, status.HTTP_200_OK)
        push_back_last_change(self.user, NICKNAME_CHANGE_INTERVAL)
        self.change('또새이름', password='wrong-password')

        self.assertEqual(self.change('또새이름').status_code, status.HTTP_200_OK)
