# auth-server/accounts/tests/test_session_revocations.py

"""
끊긴 세션의 목록(GET /api/v1/auth/session-revocations, #274)을 검증한다.

다른 서버가 이 목록으로 만료 전의 access 토큰을 거부한다.
목록의 모양은 서버 사이의 약속이다(README 의 "다른 서버에서 토큰을 검증하는 방법").
"""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from accounts.session_revocations import REFRESH_INTERVAL_SECONDS, revocation_window, sub_digest
from accounts.tests.test_refresh import LOGOUT_ALL_URL, RefreshTestCase, create_user
from accounts.tokens import revoke_all_sessions

REVOCATIONS_URL = reverse('accounts:session-revocations')


class SessionRevocationsTestCase(RefreshTestCase):
    def revocations(self) -> list[dict]:
        # 다른 서버는 로그인 없이, 쿠키 없이 부른다
        response = APIClient().get(REVOCATIONS_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.json()['revocations']

    def entry_for(self, user: User) -> dict | None:
        digest = sub_digest(str(user.public_id))
        return next((entry for entry in self.revocations() if entry['sub_sha256'] == digest), None)

    def revoked_ago(self, user: User, ago: timedelta) -> None:
        """세션을 끊은 시각을 그만큼 앞으로 옮긴다."""
        User.objects.filter(pk=user.pk).update(sessions_revoked_at=timezone.now() - ago)


class DigestTests(SessionRevocationsTestCase):
    def test_the_digest_is_the_sha256_of_the_sub(self):
        # 다른 서버(Python, TypeScript, Go)가 같은 값을 계산해야 한다. 바꾸면 그쪽이 모두 틀린다
        self.assertEqual(
            sub_digest('0d3f7a52-6f0a-4c1e-9d55-2b8a4c1f7e90'),
            '08f6625d1aecc747bd6122bbf85ef9fb3fc0f25f7986169f057f12639fe6c0ed',
        )


class ListTests(SessionRevocationsTestCase):
    def test_revoking_records_when(self):
        before = timezone.now()
        revoke_all_sessions(self.user)

        self.user.refresh_from_db()
        self.assertGreaterEqual(self.user.sessions_revoked_at, before)

    def test_a_revoked_user_is_listed_with_the_current_version(self):
        revoke_all_sessions(self.user)
        revoke_all_sessions(self.user)

        self.user.refresh_from_db()
        self.assertEqual(self.entry_for(self.user), {'sub_sha256': sub_digest(str(self.user.public_id)), 'min_ver': 2})

    def test_logging_out_everywhere_is_listed(self):
        access_token = self.login_response.data['access_token']
        self.client.post(LOGOUT_ALL_URL, HTTP_AUTHORIZATION=f'Bearer {access_token}')

        self.assertIsNotNone(self.entry_for(self.user))

    def test_a_user_never_revoked_is_not_listed(self):
        self.assertIsNone(self.entry_for(self.user))

    def test_revocations_older_than_the_access_lifetime_drop_out(self):
        # 그 전에 발급된 access 토큰은 이미 만료되었다. 목록이 끝없이 길어지지 않는다
        revoke_all_sessions(self.user)
        other = create_user(username='player_02', email='other@example.com', nickname='다른사람')
        revoke_all_sessions(other)

        self.revoked_ago(self.user, revocation_window() - timedelta(seconds=1))
        self.revoked_ago(other, revocation_window() + timedelta(seconds=1))

        self.assertIsNotNone(self.entry_for(self.user))
        self.assertIsNone(self.entry_for(other))

    def test_the_window_covers_the_access_lifetime(self):
        self.assertGreater(revocation_window(), timedelta(minutes=15))


class DocumentTests(SessionRevocationsTestCase):
    def test_the_document_is_open_and_not_cached(self):
        response = APIClient().get(REVOCATIONS_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(response.json()['refresh_interval_seconds'], REFRESH_INTERVAL_SECONDS)

    def test_the_document_does_not_name_the_user(self):
        revoke_all_sessions(self.user)

        body = APIClient().get(REVOCATIONS_URL).content.decode()

        for revealing in (str(self.user.public_id), self.user.username, self.user.email, self.user.nickname):
            self.assertNotIn(revealing, body)
