# auth-server/accounts/serializers.py

"""
accounts 앱의 요청 검증과 응답 형식.

Serializer 는 검증과 변환만 한다. 계정을 만드는 일은 services.py 가 한다.
"""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.email_codes import CODE_LENGTH
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
    """
    회원가입 요청의 형식을 검증한다.

    중복은 여기서 보지 않는다. 미인증 계정은 교체될 수 있어서
    "겹치는지" 의 판단이 필드 하나로 끝나지 않는다. services.py 가 한다.
    """

    username = serializers.CharField(
        validators=[validate_username_format, validate_username_not_reserved],
    )
    email = serializers.EmailField()
    nickname = serializers.CharField(
        validators=[validate_nickname_format, validate_nickname_not_reserved],
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


class EmailSerializer(serializers.Serializer):
    """이메일 주소 하나만 받는 요청. 인증 코드 재발송에 쓴다."""

    email = serializers.EmailField()

    def validate_email(self, email: str) -> str:
        return email.lower()


class SignupVerifySerializer(EmailSerializer):
    """가입 인증 요청을 검증한다."""

    # 형식이 맞지 않는 코드는 DB 까지 가지 않고 여기서 거른다
    code = serializers.RegexField(
        regex=rf'\A[0-9]{{{CODE_LENGTH}}}\Z',
        error_messages={'invalid': f'인증 코드는 숫자 {CODE_LENGTH}자리입니다.'},
    )


class LoginSerializer(serializers.Serializer):
    """
    로그인 요청을 검증한다.

    형식만 본다. 아이디 규칙이나 비밀번호 강도는 검사하지 않는다.
    규칙에 어긋난 입력에 다른 오류를 주면 "이런 아이디는 존재할 수 없다" 를 알려 주게 된다.
    """

    username = serializers.CharField()
    password = serializers.CharField(
        max_length=PASSWORD_MAX_LENGTH,
        write_only=True,
        trim_whitespace=False,
    )

    def validate_username(self, username: str) -> str:
        """아이디는 소문자로 저장되어 있다. 입력도 소문자로 바꿔 대소문자를 무시한다."""
        return username.lower()


class LoginResponseSerializer(serializers.Serializer):
    """로그인 응답."""

    access_token = serializers.CharField()
    token_type = serializers.CharField()
    expires_in = serializers.IntegerField()


class UserSerializer(serializers.ModelSerializer):
    """로그인한 본인에게 보여 주는 계정 정보."""

    class Meta:
        model = User
        fields = ('public_id', 'username', 'email', 'nickname')
        read_only_fields = fields