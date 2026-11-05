# auth-server/accounts/serializers.py

"""
accounts 앱의 요청 검증과 응답 형식.

Serializer 는 검증과 변환만 한다. 계정을 만드는 일은 services.py 가 한다.
"""

from rest_framework import serializers

from accounts.consents import signup_consent_problems
from accounts.creator_profiles import BIO_MAX_LENGTH, SEARCH_DEFAULT_LIMIT, SEARCH_MAX_LIMIT
from accounts.email_codes import CODE_LENGTH
from accounts.invites import INVITE_CODE_INPUT_MAX_LENGTH
from accounts.models import GuardianNoticeKind, Orientation, User
from accounts.validators import (
    NICKNAME_MAX_LENGTH,
    validate_nickname_format,
    validate_nickname_not_reserved,
    validate_username_format,
    validate_username_not_reserved,
)

# Django 는 비밀번호를 해싱하기 전에 길이를 제한하지 않는다.
# 아주 긴 입력으로 해싱 비용을 키우는 요청을 막는다
PASSWORD_MAX_LENGTH = 128
# 앱이 본문으로 보내는 refresh 토큰의 길이 상한. 서명한 JWT 는 1천 자 안팎이다. 터무니없이 긴 값을 디코딩하지 않는다
APP_REFRESH_TOKEN_MAX_LENGTH = 4096


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
    # "만 14세 이상입니다" 확인(#336). 참이어야 가입된다. 자기 신고라 거짓말을 막지는 못한다.
    # 실제 나이는 본인인증에서 알고, 그때 만 14세 미만이면 계정을 막는다(identity.py)
    age_over_14 = serializers.BooleanField()
    # 동의한 항목과 그 판(#450). {"terms": 1, "privacy": 1, "marketing": 1}. 넣지 않은 선택 항목은 동의하지 않은 것이다.
    # 판을 받는 까닭은 화면이 보인 문서가 지금의 판인지 보려는 것이다. 옛 판이면 400 이다
    consents = serializers.DictField(child=serializers.IntegerField(min_value=1), allow_empty=True)
    # 초대 코드(#990). 고를 수 있다. 공백과 하이픈, 대소문자는 가리지 않는다(invites.py)
    # 적지 않으면 services.complete_signup 의 기본값(빈 글)이다. 기본값을 여기 두면 API 목록에서 꼭 적을 칸이 된다
    invite_code = serializers.CharField(required=False, allow_blank=True, max_length=INVITE_CODE_INPUT_MAX_LENGTH)

    def validate_consents(self, consents: dict[str, int]) -> dict[str, int]:
        problems = signup_consent_problems(consents)
        if problems:
            raise serializers.ValidationError(problems, code='consent_invalid')
        return consents

    def validate_age_over_14(self, confirmed: bool) -> bool:
        if not confirmed:
            raise serializers.ValidationError('만 14세 이상만 가입할 수 있습니다.', code='under_min_age')
        return confirmed

    def validate(self, attrs: dict) -> dict:
        """확인은 여기서 끝난다. 계정에 적는 값이 아니라 services.py 에 넘기지 않는다."""
        attrs.pop('age_over_14')
        return attrs


class IdentityVerifySerializer(serializers.Serializer):
    """본인인증. 본인확인 업체의 화면에서 받은 글자 하나를 받는다. 모양은 업체가 정한다(identity_providers.py)."""

    token = serializers.CharField(max_length=1000)


class GuardianRequestSerializer(serializers.Serializer):
    """보호자에게 동의를 부탁한다. 보호자의 이메일 하나를 받는다."""

    guardian_email = serializers.EmailField()


class GuardianConsentSerializer(serializers.Serializer):
    """보호자의 동의. 메일의 동의 링크에서 꺼낸 글자와, 보호자가 본인확인 업체에서 받은 글자를 받는다."""

    consent_token = serializers.CharField(max_length=500)
    identity_token = serializers.CharField(max_length=1000)


class GuardianRevokeSerializer(serializers.Serializer):
    """보호자의 철회. 메일의 철회 링크에서 꺼낸 글자를 받는다."""

    revoke_token = serializers.CharField(max_length=500)


class GuardianNoticeSerializer(serializers.Serializer):
    """결제 서버가 보낸 보호자 알림(#352). 본문의 모양만 본다. 서명은 뷰가 먼저 본다."""

    order_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=GuardianNoticeKind.choices)
    user_id = serializers.UUIDField()
    product_id = serializers.CharField(max_length=100)
    price = serializers.IntegerField(min_value=1)
    credits = serializers.IntegerField(min_value=1)
    occurred_at = serializers.DateTimeField()


class ReceiptNoticeSerializer(serializers.Serializer):
    """결제 서버가 보낸 본인 결제 알림(#553). 본문의 모양만 본다. 서명은 뷰가 먼저 본다."""

    order_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=GuardianNoticeKind.choices)
    user_id = serializers.UUIDField()
    product_id = serializers.CharField(max_length=100)
    price = serializers.IntegerField(min_value=1)
    credits = serializers.IntegerField(min_value=1)
    paid_at = serializers.DateTimeField()
    occurred_at = serializers.DateTimeField()
    refundable_until = serializers.DateTimeField()


class IdentityStatusSerializer(serializers.Serializer):
    """본인인증 상태(identity_status.IdentityStatus). 내 정보와 본인인증의 응답에 실린다."""

    verified = serializers.BooleanField()
    legal_adult = serializers.BooleanField()
    adult_content = serializers.BooleanField()


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


class WithdrawalRequestSerializer(serializers.Serializer):
    """탈퇴 요청(#603). 열린 채 둔 기기에서 남이 누르지 못하게 비밀번호를 다시 받는다."""

    password = serializers.CharField(max_length=PASSWORD_MAX_LENGTH, write_only=True, trim_whitespace=False)


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
    """
    토큰을 발급하는 응답. 로그인 2단계, 토큰 갱신, 비밀번호 변경이 쓴다.

    consents_pending 이 비어 있지 않으면 다시 동의할 필수 항목이 남았다(#450). 그 access 토큰은 인증 서버에만 통한다.
    화면은 동의를 받은 뒤(PUT /me/consents/<항목>) /refresh 로 모든 서버에 통하는 토큰을 받는다.
    """

    access_token = serializers.CharField()
    token_type = serializers.CharField()
    expires_in = serializers.IntegerField()
    consents_pending = serializers.ListField(
        child=serializers.CharField(),
        help_text='다시 동의할 필수 항목. 비어 있지 않으면 access 토큰이 인증 서버에만 통한다',
    )
    withdrawal_scheduled_at = serializers.DateTimeField(
        allow_null=True,
        help_text='탈퇴를 요청했으면 계정을 비울 시각(#603). 있으면 access 토큰이 인증 서버에만 통한다. 취소하면 null',
    )


class AppTokenResponseSerializer(LoginResponseSerializer):
    """
    앱(#429)에 토큰을 주는 응답. 웹의 응답에 refresh 토큰을 본문으로 더한다. 쿠키는 주지 않는다.

    앱은 refresh 토큰을 기기의 안전한 저장소에 두고, 화면의 스크립트에는 넘기지 않는다(docs/product/app-refresh.md).
    """

    refresh_token = serializers.CharField(
        help_text='refresh 토큰. 갱신과 로그아웃에 본문으로 보낸다. 쓸 때마다 새것으로 바뀐다'
    )
    refresh_expires_in = serializers.IntegerField(help_text='refresh 토큰이 끝나기까지의 초')


class AppRefreshTokenSerializer(serializers.Serializer):
    """앱이 갱신에 보내는 refresh 토큰."""

    refresh_token = serializers.CharField(max_length=APP_REFRESH_TOKEN_MAX_LENGTH, trim_whitespace=False)


class AppLogoutSerializer(serializers.Serializer):
    """앱이 로그아웃에 보내는 refresh 토큰. 없어도 로그아웃은 성공한다(웹의 로그아웃과 같다)."""

    refresh_token = serializers.CharField(
        max_length=APP_REFRESH_TOKEN_MAX_LENGTH, trim_whitespace=False, required=False
    )


class UserSerializer(serializers.ModelSerializer):
    """로그인한 본인에게 보여 주는 계정 정보."""

    class Meta:
        model = User
        fields = ('public_id', 'username', 'email', 'nickname')
        read_only_fields = fields


class ConsentDocumentSerializer(serializers.Serializer):
    """동의를 받는 항목 하나의 지금의 판. 화면이 가입과 설정에서 보일 문서를 고른다."""

    item = serializers.CharField()
    version = serializers.IntegerField()
    effective_on = serializers.DateField()
    required = serializers.BooleanField()


class ConsentStateSerializer(serializers.Serializer):
    """본인의 항목 하나의 동의 상태. 동의하지 않았거나 철회했으면 agreed_version 과 agreed_at 이 null 이다."""

    item = serializers.CharField()
    required = serializers.BooleanField()
    version = serializers.IntegerField()
    agreed_version = serializers.IntegerField(allow_null=True)
    agreed_at = serializers.DateTimeField(allow_null=True)
    pending = serializers.BooleanField()


class ConsentAgreeSerializer(serializers.Serializer):
    """항목 하나에 동의한다. 화면이 보인 문서의 판을 보낸다."""

    version = serializers.IntegerField(min_value=1)


class PublicNameSerializer(serializers.Serializer):
    """다른 사람의 공개 ID 와 이름. 없거나 막은 계정이면 nickname 이 null 이다."""

    public_id = serializers.UUIDField()
    nickname = serializers.CharField(allow_null=True)


class MyInviteSerializer(serializers.Serializer):
    """내 초대 코드와 받은 보상(#990). 상한은 서버의 설정이다. 보상은 내가 본인인증을 마친 뒤부터 센다."""

    code = serializers.CharField()
    rewarded = serializers.IntegerField(help_text='초대한 사람으로서 받은 보상의 수')
    limit = serializers.IntegerField(help_text='받을 수 있는 보상의 수. 0 이면 초대 보상이 꺼져 있다')


class ContentSettingsSerializer(serializers.Serializer):
    """
    목록을 거르는 내 설정(#986, #987). 고칠 때는 보낸 칸만 바뀐다.

    show_adult_content: 성인 작품을 목록에 보일지. 성인 확인을 한 계정만 켤 수 있다(처음에는 켜져 있다).
    orientation: all(거르지 않음), male(남성향 태그만), female(여성향 태그만).
    """

    show_adult_content = serializers.BooleanField(required=False)
    orientation = serializers.ChoiceField(choices=Orientation.choices, required=False)


class MyProfileSerializer(serializers.Serializer):
    """제작자로서의 내 소개(#992). 200자까지, 비워 둘 수 있다. 앞뒤 공백은 지운다."""

    bio = serializers.CharField(max_length=BIO_MAX_LENGTH, allow_blank=True)


class CreatorSearchQuerySerializer(serializers.Serializer):
    """제작자를 이름으로 찾는 주소의 값(#984). q 는 앞뒤 공백을 뗀 1~20자(닉네임의 상한)다."""

    q = serializers.CharField(max_length=NICKNAME_MAX_LENGTH, trim_whitespace=True)
    limit = serializers.IntegerField(min_value=1, max_value=SEARCH_MAX_LIMIT, default=SEARCH_DEFAULT_LIMIT)


class CreatorSerializer(serializers.Serializer):
    """남에게 보이는 제작자(#992). 표시 이름은 닉네임이다."""

    public_id = serializers.UUIDField()
    nickname = serializers.CharField()
    bio = serializers.CharField()


class CreatorSearchResultSerializer(serializers.Serializer):
    """제작자를 이름으로 찾은 결과(#984). 닉네임이 같은 것, 그것으로 시작하는 것, 나머지 차례다."""

    items = CreatorSerializer(many=True)
