# auth-server/accounts/tests/test_refresh_rotation.py

"""
refresh 토큰을 바꾼 답을 잃었을 때(다시 읽기, 탭 닫기, 망이 끊김)의 갱신을 본다(accounts/tokens.py 의 lost_answer).

서버는 옛 토큰을 폐기하고 새 쌍을 줬는데 화면이 새 쿠키를 받지 못하면, 다음 요청에 옛 토큰이 다시 온다.
처음 바꾼 지 REFRESH_REUSE_GRACE 안이고 바꿔 준 토큰이 아직 쓰이지 않았으면 탈취가 아니라 답을 잃은 것으로 보고
새 쌍을 다시 준다. 하나라도 어긋나면 지금처럼 탈취로 보아 모든 세션을 끊는다(test_refresh.py 의 RefreshReuseTests).
"""

import threading
from datetime import timedelta

from django.db import connection
from django.test import TestCase, TransactionTestCase
from rest_framework import status
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from accounts.cookies import REFRESH_COOKIE_NAME
from accounts.models import RefreshRotation, TokenClient, User
from accounts.tests.test_refresh import REFRESH_URL, RefreshTestCase, create_user
from accounts.tokens import (
    REFRESH_REUSE_GRACE,
    InvalidRefreshTokenError,
    issue_token_pair,
    revoke_all_sessions,
    revoke_refresh_token,
    rotate_refresh_token,
)


def live_tokens(user: User) -> int:
    """그 사람의 지금 세대에서 폐기되지 않은 refresh 토큰의 수. 살아 있는 세션의 수다."""
    revoked = BlacklistedToken.objects.values('token_id')
    return OutstandingToken.objects.filter(user=user).exclude(id__in=revoked).count()


def version_of(user: User) -> int:
    return User.objects.get(pk=user.pk).token_version


def age_rotations(by: timedelta) -> None:
    """바꾼 기록의 처음 바꾼 시각을 그만큼 앞으로 당긴다. 시간이 지난 것과 같다."""
    for rotation in RefreshRotation.objects.all():
        RefreshRotation.objects.filter(pk=rotation.pk).update(rotated_at=rotation.rotated_at - by)


class LostAnswerTests(TestCase):
    def setUp(self):
        self.user = create_user()
        self.old = issue_token_pair(self.user).refresh
        # 서버는 바꿔 줬지만 화면은 이 답을 받지 못했다
        self.lost = rotate_refresh_token(self.old)
        self.version = version_of(self.user)

    def test_the_old_token_gets_a_new_pair_while_the_lost_one_is_unused(self):
        again = rotate_refresh_token(self.old)

        self.assertNotEqual(again.refresh, self.lost.refresh)
        self.assertEqual(version_of(self.user), self.version)
        # 받지 못한 토큰은 폐기되고 새로 준 것 하나만 살아 있다
        self.assertEqual(live_tokens(self.user), 1)
        with self.assertRaises(InvalidRefreshTokenError):
            rotate_refresh_token(self.lost.refresh)

    def test_the_new_pair_keeps_working(self):
        again = rotate_refresh_token(self.old)

        rotated = rotate_refresh_token(again.refresh)

        self.assertTrue(rotated.refresh)
        self.assertEqual(live_tokens(self.user), 1)

    def test_other_sessions_are_not_cut(self):
        other = issue_token_pair(self.user).refresh

        rotate_refresh_token(self.old)

        self.assertTrue(rotate_refresh_token(other).refresh)

    def test_after_the_grace_it_is_theft(self):
        age_rotations(REFRESH_REUSE_GRACE + timedelta(seconds=1))

        with self.assertRaises(InvalidRefreshTokenError):
            rotate_refresh_token(self.old)

        self.assertEqual(version_of(self.user), self.version + 1)

    def test_once_the_new_token_was_used_it_is_theft(self):
        # 정상 사용자는 답을 받아 새 토큰을 이미 썼다. 지금 옛 토큰을 보낸 쪽은 다른 사람이다
        rotate_refresh_token(self.lost.refresh)

        with self.assertRaises(InvalidRefreshTokenError):
            rotate_refresh_token(self.old)

        self.assertEqual(version_of(self.user), self.version + 1)

    def test_the_grace_counts_from_the_first_rotation(self):
        # 다시 줘도 유예는 늘지 않는다. 옛 토큰을 되풀이해 보내 끝없이 새 쌍을 받지 못한다
        age_rotations(REFRESH_REUSE_GRACE - timedelta(seconds=5))
        rotate_refresh_token(self.old)
        age_rotations(timedelta(seconds=6))

        with self.assertRaises(InvalidRefreshTokenError):
            rotate_refresh_token(self.old)

        self.assertEqual(version_of(self.user), self.version + 1)

    def test_a_logged_out_token_has_no_grace(self):
        # 로그아웃으로 폐기한 토큰은 바꾼 기록이 없다. 다시 오면 탈취다
        current = issue_token_pair(self.user).refresh
        revoke_refresh_token(current)

        with self.assertRaises(InvalidRefreshTokenError):
            rotate_refresh_token(current)

        self.assertEqual(version_of(self.user), self.version + 1)

    def test_a_token_from_an_earlier_generation_is_only_refused(self):
        revoke_all_sessions(self.user)
        version = version_of(self.user)

        with self.assertRaises(InvalidRefreshTokenError):
            rotate_refresh_token(self.old)

        self.assertEqual(version_of(self.user), version)

    def test_a_deactivated_account_gets_nothing(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)

        with self.assertRaises(InvalidRefreshTokenError):
            rotate_refresh_token(self.old)

    def test_the_other_client_is_refused_without_cutting(self):
        with self.assertRaises(InvalidRefreshTokenError):
            rotate_refresh_token(self.old, client=TokenClient.APP)

        self.assertEqual(version_of(self.user), self.version)
        self.assertTrue(rotate_refresh_token(self.old).refresh)


class LostCookieTests(RefreshTestCase):
    """쿠키의 길로. 갱신의 답을 받지 못한 화면이 옛 쿠키로 다시 갱신한다."""

    def test_a_browser_that_lost_the_answer_stays_logged_in(self):
        old_cookie = self.refresh_cookie_value()
        # 서버는 바꿔 줬지만 이 답(새 쿠키)은 화면에 닿지 않았다
        self.client.post(REFRESH_URL)
        reloaded = self.client_with_refresh_token(old_cookie)

        response = reloaded.post(REFRESH_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(response.cookies[REFRESH_COOKIE_NAME].value, '')
        self.assertEqual(reloaded.post(REFRESH_URL).status_code, status.HTTP_200_OK)


class ConcurrentLostAnswerTests(TransactionTestCase):
    """같은 옛 토큰이나 받지 못한 토큰으로 요청이 동시에 와도 살아 있는 토큰은 하나다(행 잠금)."""

    def setUp(self):
        self.user = create_user()
        self.old = issue_token_pair(self.user).refresh
        self.lost = rotate_refresh_token(self.old).refresh

    def run_together(self, tokens: list[str]) -> list[str | None]:
        """refresh 토큰마다 스레드 하나로 함께 갱신한다. 받은 refresh 토큰, 거부되면 None 이다."""
        barrier = threading.Barrier(len(tokens))
        results: list[str | None] = [None] * len(tokens)
        errors: list[BaseException] = []

        def work(index: int, token: str) -> None:
            barrier.wait()
            try:
                results[index] = rotate_refresh_token(token).refresh
            except InvalidRefreshTokenError:
                results[index] = None
            except BaseException as error:  # 교착 같은 DB 오류는 테스트를 떨어뜨린다
                errors.append(error)
            finally:
                connection.close()

        threads = [threading.Thread(target=work, args=(index, token)) for index, token in enumerate(tokens)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        return results

    def test_two_reloads_with_the_old_token_leave_one_session(self):
        results = self.run_together([self.old, self.old])

        self.assertEqual(sum(result is not None for result in results), 2)
        self.assertEqual(live_tokens(self.user), 1)

    def test_the_old_and_the_new_token_together_never_leave_two_sessions(self):
        version = version_of(self.user)

        self.run_together([self.old, self.lost])

        # 어느 쪽이 먼저 잠그든 살아 있는 쪽은 하나다. 새 토큰이 먼저 쓰였으면 옛 토큰이 탈취로 보여 모두 끊긴다
        if version_of(self.user) == version:
            self.assertEqual(live_tokens(self.user), 1)
        else:
            self.assertEqual(version_of(self.user), version + 1)
