# auth-server/accounts/serializers.py

"""
accounts 앱의 요청 검증과 응답 형식.

Serializer 는 검증과 변환만 한다. 계정을 만드는 일은 services.py 가 한다.
"""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from accounts.models import User
from accounts.validators import (
    validate_nickname_format,
    validate_nickname_not_reserved,
    validate_username_format,
    validate_username_not_reserved,
)

# Django 는 비밀번호를 해싱하기 전에 길이를 제한하지 않는다.
# 아주 긴 입력으로 해싱 비용을 키우는 요청을 막는다
PASSWORD_MAX_LENGTH = 128


class SignupSerializer(serializers.Serializer):
    """회원가입 요청을 검증한다."""

    username = serializers.CharField(
        validators=[
            validate_username_format,
            validate_username_not_reserved,
            # 사전 조회. 사용자에게 어느 값이 겹쳤는지 알려 주는 용도다.
            # 동시에 들어온 요청은 이 검사를 둘 다 통과할 수 있고, 그 경우는 DB 제약이 막는다
            UniqueValidator(
                queryset=User.objects.all(),
                message='이미 사용 중인 아이디입니다.',
            ),
        ],
    )
    email = serializers.EmailField(
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                lookup='iexact',
                message='이미 사용 중인 이메일입니다.',
            ),
        ],
    )
    nickname = serializers.CharField(
        validators=[
            validate_nickname_format,
            validate_nickname_not_reserved,
            UniqueValidator(
                queryset=User.objects.all(),
                message='이미 사용 중인 닉네임입니다.',
            ),
        ],
    )
    password = serializers.CharField(
        max_length=PASSWORD_MAX_LENGTH,
        # 응답에 절대 실리지 않게 한다
        write_only=True,
        # 앞뒤 공백도 비밀번호의 일부다. 기본 동작인 공백 제거를 끈다
        trim_whitespace=False,
    )

    def validate_email(self, email: str) -> str:
        """이메일을 소문자로 통일한다."""
        return email.lower()

    def validate(self, attrs: dict) -> dict:
        """필드 하나만 봐서는 알 수 없는 규칙을 검사한다."""
        self._validate_username_differs_from_email(attrs['username'], attrs['email'])
        self._validate_password_strength(attrs)
        return attrs

    def _validate_username_differs_from_email(self, username: str, email: str) -> None:
        """
        아이디가 이메일의 @ 앞부분과 같으면 거부한다.

        같으면 아이디를 아는 사람이 이메일을 추측할 수 있어 둘을 분리한 의미가 줄어든다.
        """
        email_local_part = email.split('@')[0]
        if username == email_local_part:
            raise serializers.ValidationError(
                {'username': '아이디는 이메일의 @ 앞부분과 달라야 합니다.'},
            )

    def _validate_password_strength(self, attrs: dict) -> None:
        """
        settings 의 AUTH_PASSWORD_VALIDATORS 로 비밀번호를 검사한다.

        "아이디와 비슷한 비밀번호" 를 걸러내려면 검증기가 아이디를 알아야 한다.
        저장하지 않는 임시 User 객체에 값을 담아 넘긴다.
        """
        candidate = User(
            username=attrs['username'],
            email=attrs['email'],
            nickname=attrs['nickname'],
        )
        try:
            validate_password(attrs['password'], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': exc.messages}) from exc


class SignupResponseSerializer(serializers.ModelSerializer):
    """
    회원가입 응답.

    여기 적은 필드만 나간다. 정수 PK, 이메일, 비밀번호 해시는 목록에 없으므로
    실수로도 응답에 실리지 않는다.
    """

    class Meta:
        model = User
        fields = ('public_id', 'username', 'nickname')
        read_only_fields = fields