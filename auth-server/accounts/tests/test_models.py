# auth-server/accounts/tests/test_models.py

"""
User 모델의 규칙을 검증한다.

실제 PostgreSQL 에서 돈다. 대소문자를 무시하는 이메일 중복 검사는
DB 제약이라서 DB 없이는 확인할 수 없다.
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User
from accounts.reserved import is_reserved_name
from accounts.validators import validate_username_format, validate_username_not_reserved


def create_user(**overrides) -> User:
    """테스트마다 달라지는 값만 넘기고 나머지는 기본값을 쓴다."""
    fields = {
        'username': 'tester01',
        'email': 'tester01@example.com',
        'nickname': '테스터',
        'password': 'correct-horse-battery',
    }
    fields.update(overrides)
    return User.objects.create_user(**fields)


class UsernameFormatTests(TestCase):
    def test_accepts_lowercase_digits_underscore(self):
        validate_username_format('player_01')

    def test_rejects_invalid_usernames(self):
        invalid_usernames = [
            'abc',                # 4자 미만
            'a' * 21,             # 20자 초과
            'Player01',           # 대문자
            'user@example.com',   # 이메일 형태
            'user.name',          # 마침표
            'player 01',          # 공백
            '플레이어01',          # 한글
            'player01\n',         # 끝의 줄바꿈
        ]
        for username in invalid_usernames:
            with self.subTest(username=username):
                with self.assertRaises(ValidationError):
                    validate_username_format(username)


class ReservedNameTests(TestCase):
    def test_exact_match_is_reserved(self):
        self.assertTrue(is_reserved_name('admin'))
        self.assertTrue(is_reserved_name(' Admin '))
        self.assertTrue(is_reserved_name('운영자'))

    def test_partial_match_is_not_reserved(self):
        self.assertFalse(is_reserved_name('badminton'))
        self.assertFalse(is_reserved_name('admin123'))

    def test_reserved_username_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_username_not_reserved('admin')


class UserModelTests(TestCase):
    def test_username_is_stored_in_lowercase(self):
        user = create_user(username='Tester01')
        self.assertEqual(user.username, 'tester01')

    def test_password_is_hashed(self):
        user = create_user()
        self.assertNotEqual(user.password, 'correct-horse-battery')
        self.assertTrue(user.check_password('correct-horse-battery'))

    def test_public_id_differs_per_user(self):
        first = create_user()
        second = create_user(username='tester02', email='tester02@example.com', nickname='테스터2')
        self.assertNotEqual(first.public_id, second.public_id)

    def test_email_is_unique_regardless_of_case(self):
        create_user(email='same@example.com')
        # 실패한 쿼리가 테스트의 트랜잭션을 망가뜨리지 않도록 따로 감싼다
        with self.assertRaises(IntegrityError), transaction.atomic():
            create_user(username='tester02', email='SAME@example.com', nickname='테스터2')

    def test_duplicate_nickname_is_rejected(self):
        create_user()
        with self.assertRaises(IntegrityError), transaction.atomic():
            create_user(username='tester02', email='tester02@example.com')