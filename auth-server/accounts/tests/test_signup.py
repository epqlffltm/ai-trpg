# auth-server/accounts/tests/test_signup.py

"""
회원가입 API 를 검증한다.

실제 URL 로 요청을 보내 뷰, Serializer, service, DB 를 한 번에 거친다.
"""

from unittest.mock import patch

from django.db import IntegrityError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User

SIGNUP_URL = reverse('accounts:signup')


def signup_payload(**overrides) -> dict:
    """테스트마다 달라지는 값만 넘기고 나머지는 기본값을 쓴다."""
    payload = {
        'username': 'player_01',
        'email': 'someone@example.com',
        'nickname': '플레이어',
        'password': 'correct-horse-battery',
    }
    payload.update(overrides)
    return payload


class SignupSuccessTests(APITestCase):
    def test_creates_user_and_returns_201(self):
        response = self.client.post(SIGNUP_URL, signup_payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username='player_01').exists())

    def test_response_exposes_only_public_fields(self):
        response = self.client.post(SIGNUP_URL, signup_payload(), format='json')

        # 정수 PK, 이메일, 비밀번호가 응답에 섞여 나가지 않는지 필드 목록 전체를 고정한다
        self.assertEqual(set(response.data), {'public_id', 'username', 'nickname'})

    def test_password_is_stored_hashed(self):
        self.client.post(SIGNUP_URL, signup_payload(), format='json')

        user = User.objects.get(username='player_01')
        self.assertNotEqual(user.password, 'correct-horse-battery')
        self.assertTrue(user.check_password('correct-horse-battery'))

    def test_email_is_stored_in_lowercase(self):
        self.client.post(SIGNUP_URL, signup_payload(email='Someone@Example.com'), format='json')

        user = User.objects.get(username='player_01')
        self.assertEqual(user.email, 'someone@example.com')

    def test_new_user_has_no_admin_rights(self):
        # 요청 본문에 권한 필드를 끼워 넣어도 무시되어야 한다
        payload = signup_payload(is_staff=True, is_superuser=True)
        self.client.post(SIGNUP_URL, payload, format='json')

        user = User.objects.get(username='player_01')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)


class SignupValidationTests(APITestCase):
    def assert_rejected(self, payload: dict, field: str) -> None:
        """400 으로 거부되고, 오류가 해당 필드에 달려 있고, 계정이 만들어지지 않았는지 확인한다."""
        response = self.client.post(SIGNUP_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(field, response.data)
        self.assertFalse(User.objects.filter(username=payload.get('username')).exists())

    def test_rejects_uppercase_username(self):
        self.assert_rejected(signup_payload(username='Player_01'), 'username')

    def test_rejects_reserved_username(self):
        self.assert_rejected(signup_payload(username='admin'), 'username')

    def test_rejects_username_equal_to_email_local_part(self):
        payload = signup_payload(username='someone', email='someone@example.com')
        self.assert_rejected(payload, 'username')

    def test_rejects_reserved_nickname(self):
        self.assert_rejected(signup_payload(nickname='운영자'), 'nickname')
        self.assert_rejected(signup_payload(nickname='GM'), 'nickname')

    def test_rejects_nickname_with_space(self):
        self.assert_rejected(signup_payload(nickname='운 영 자'), 'nickname')

    def test_rejects_invalid_email(self):
        self.assert_rejected(signup_payload(email='not-an-email'), 'email')

    def test_rejects_weak_passwords(self):
        weak_passwords = [
            'short1!',          # 8자 미만
            '1234567890',       # 숫자만
            'password123',      # 흔한 비밀번호
            'player_01',        # 아이디와 같음
        ]
        for password in weak_passwords:
            with self.subTest(password=password):
                self.assert_rejected(signup_payload(password=password), 'password')

    def test_rejects_missing_field(self):
        payload = signup_payload()
        del payload['nickname']
        self.assert_rejected(payload, 'nickname')


class SignupDuplicateTests(APITestCase):
    def setUp(self):
        self.client.post(SIGNUP_URL, signup_payload(), format='json')

    def post_second_user(self, **overrides):
        """첫 번째 회원과 겹치지 않는 값에서 시작해, 테스트하려는 값만 겹치게 한다."""
        payload = signup_payload(
            username='player_02',
            email='another@example.com',
            nickname='다른사람',
        )
        payload.update(overrides)
        return self.client.post(SIGNUP_URL, payload, format='json')

    def test_rejects_duplicate_username(self):
        response = self.post_second_user(username='player_01')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data)

    def test_rejects_duplicate_email_regardless_of_case(self):
        response = self.post_second_user(email='SOMEONE@example.com')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

    def test_rejects_duplicate_nickname(self):
        response = self.post_second_user(nickname='플레이어')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('nickname', response.data)

    def test_returns_409_when_database_rejects_duplicate(self):
        # 동시 요청으로 사전 조회를 둘 다 통과한 상황을 흉내 낸다.
        # 사전 조회는 통과시키고, 저장 단계에서 DB 제약이 터지게 한다
        with patch.object(User.objects, 'create_user', side_effect=IntegrityError):
            response = self.post_second_user()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(User.objects.filter(username='player_02').exists())


class SignupMethodTests(APITestCase):
    def test_get_is_not_allowed(self):
        response = self.client.get(SIGNUP_URL)

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)