# auth-server/accounts/serializers.py

"""
accounts 앱의 요청 검증과 응답 형식.

Serializer 는 검증과 변환만 한다. 계정을 만드는 일은 services.py 가 한다.
"""

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


class EmailSerializer(serializers.Serializer):
    """이메일 주소 하나만 받는 요청. 가입의 1단계(코드 보내기와 다시 보내기)와 비밀번호 재설정 요청에 쓴다."""

    email = serializers.EmailField()

    def validate_email(self, email: str) -> str:
        """이메일을 소문자로 통일한다."""
        return email.lower()


class SignupSerializer(EmailSerializer):
    """가입의 1단계. 이메일만 받는다. 아이디와 비밀번호는 코드를 맞힌 뒤에 받는다(#271)."""


class SignupVerifySerializer(EmailSerializer):
    """가입 인증 요청을 검증한다."""

    # 형식이 맞지 않는 코드는 DB 까지 가지 않고 여기서 거른다
    code = serializers.RegexField(
        regex=rf'\A[0-9]{{{CODE_LENGTH}}}\Z',
        error_messages={'invalid': f'인증 코드는 숫자 {CODE_LENGTH}자리입니다.'},
    )


class SignupVerifiedSerializer(serializers.Serializer):
    """가입 2단계의 응답. 3단계에 쓸 가입 티켓을 준다."""

    detail = serializers.CharField()
    signup_ticket = serializers.CharField()


class SignupCompleteSerializer(serializers.Serializer):
    """
    가입의 3단계. 가입 티켓과 가입 내용의 형식을 검증한다.

    티켓이 맞는지, 아이디가 이메일과 겹치는지, 비밀번호가 강한지는 여기서 보지 않는다.
    셋 다 티켓 속의 이메일이 있어야 판단할 수 있어서 services.py 가 티켓을 읽은 뒤에 본다.
    중복도 services.py 가 본다.
    """

    signup_ticket = serializers.CharField()
    username = serializers.CharField(
        validators=[validate_username_format, validate_username_not_reserved],
    )
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


class LoginTicketSerializer(serializers.Serializer):
    """로그인 티켓 하나만 받는 요청. 로그인 코드 재발송에 쓴다."""

    login_ticket = serializers.CharField()


class LoginVerifySerializer(LoginTicketSerializer):
    """로그인 2단계 요청을 검증한다."""

    code = serializers.RegexField(
        regex=rf'\A[0-9]{{{CODE_LENGTH}}}\Z',
        error_messages={'invalid': f'인증 코드는 숫자 {CODE_LENGTH}자리입니다.'},
    )


class LoginChallengeSerializer(serializers.Serializer):
    """로그인 1단계 응답. 토큰이 아니라 다음 단계에 쓸 티켓을 준다."""

    detail = serializers.CharField()
    login_ticket = serializers.CharField()


class PasswordChangeSerializer(serializers.Serializer):
    """
    비밀번호 변경 요청의 형식을 검증한다.

    새 비밀번호의 강도는 여기서 보지 않는다. services.py 가 사용자와 함께 검사한다.
    """

    current_password = serializers.CharField(
        max_length=PASSWORD_MAX_LENGTH,
        write_only=True,
        trim_whitespace=False,
    )
    new_password = serializers.CharField(
        max_length=PASSWORD_MAX_LENGTH,
        write_only=True,
        trim_whitespace=False,
    )


class PasswordResetConfirmSerializer(EmailSerializer):
    """비밀번호 재설정 요청의 형식을 검증한다."""

    # 토큰은 43글자다. 지나치게 긴 입력은 해시하기 전에 거른다
    token = serializers.CharField(max_length=200)
    new_password = serializers.CharField(
        max_length=PASSWORD_MAX_LENGTH,
        write_only=True,
        trim_whitespace=False,
    )


class LoginResponseSerializer(serializers.Serializer):
    """토큰을 발급하는 응답. 로그인 2단계와 토큰 갱신이 쓴다."""

    access_token = serializers.CharField()
    token_type = serializers.CharField()
    expires_in = serializers.IntegerField()


class UserSerializer(serializers.ModelSerializer):
    """로그인한 본인에게 보여 주는 계정 정보."""

    class Meta:
        model = User
        fields = ('public_id', 'username', 'email', 'nickname')
        read_only_fields = fields
