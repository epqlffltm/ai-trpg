# auth-server/accounts/admin.py

"""
관리자 화면에 accounts 앱의 모델을 등록한다.

User 는 Django 의 UserAdmin 을 상속해 비밀번호 해싱과 변경 화면을 그대로 쓰고,
화면에 보이는 필드 구성만 이 프로젝트의 User 모델에 맞춘다.
인증 코드, 보낼 메일, 보안 이벤트, 환영 크레딧은 조회만 한다.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from accounts.models import (
    EmailCode,
    GuardianConsent,
    IdentityVerification,
    OutgoingMail,
    PaymentEligibility,
    SecurityEvent,
    SignupCode,
    User,
    WelcomeCredit,
)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    # 목록 화면
    list_display = ('username', 'email', 'nickname', 'is_email_verified', 'is_staff', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'nickname')
    ordering = ('-date_joined',)

    # 값이 자동으로 정해지는 필드는 화면에서 고칠 수 없게 한다.
    # is_active 도 여기서 끄지 못한다. 정지는 관리 명령(suspend_account)으로 한다.
    # 화면에서 끄면 세션 버전이 오르지 않아, 다른 서버에서 옛 access 토큰이 만료(15분)까지 통한다
    readonly_fields = ('public_id', 'token_version', 'sessions_revoked_at', 'is_active', 'last_login', 'date_joined')

    # 수정 화면. 기본 구성에서 first_name, last_name 을 빼고 nickname, public_id 를 넣는다
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('프로필', {'fields': ('email', 'email_verified_at', 'nickname', 'public_id')}),
        ('권한', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('기록', {'fields': ('token_version', 'sessions_revoked_at', 'last_login', 'date_joined')}),
    )

    @admin.display(boolean=True, description='이메일 인증')
    def is_email_verified(self, user: User) -> bool:
        return user.is_email_verified

    # 추가 화면. 기본 구성은 아이디와 비밀번호만 묻는다.
    # email 과 nickname 이 필수라서 여기에 넣지 않으면 빈 값으로 저장된다
    add_fieldsets = (
        (
            None,
            {
                'classes': ('wide',),
                'fields': ('username', 'email', 'nickname', 'usable_password', 'password1', 'password2'),
            },
        ),
    )


@admin.register(EmailCode)
class EmailCodeAdmin(admin.ModelAdmin):
    """
    인증 코드의 상태를 조회만 한다.

    코드는 API 가 발급하고 소비한다. 관리자 화면에서 만들거나 고치면
    발급 제한과 틀린 횟수 제한을 우회하게 된다.
    """

    list_display = ('user', 'purpose', 'has_active_code', 'expires_at', 'failed_attempts', 'last_issued_at')
    list_filter = ('purpose',)
    search_fields = ('user__username', 'user__email')
    # 해시는 화면에 보여 주지 않는다
    exclude = ('code_hash',)

    @admin.display(boolean=True, description='쓸 수 있는 코드')
    def has_active_code(self, record: EmailCode) -> bool:
        return bool(record.code_hash)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(SignupCode)
class SignupCodeAdmin(admin.ModelAdmin):
    """가입 코드의 상태를 조회만 한다. 회원의 인증 코드와 같은 까닭으로 만들거나 고치지 못한다."""

    list_display = ('email', 'has_active_code', 'expires_at', 'failed_attempts', 'last_issued_at')
    search_fields = ('email',)
    # 해시는 화면에 보여 주지 않는다
    exclude = ('code_hash',)

    @admin.display(boolean=True, description='쓸 수 있는 코드')
    def has_active_code(self, record: SignupCode) -> bool:
        return bool(record.code_hash)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(OutgoingMail)
class OutgoingMailAdmin(admin.ModelAdmin):
    """
    발송함을 조회한다. 운영자가 보내지 못한 메일을 확인하는 곳이다.

    보낸 메일은 지워지므로 여기 보이는 것은 아직 대기 중이거나, 워커가 보내는 중이거나, 버려진 메일이다.
    보내는 중인 메일의 다음 시도 시각은 임대가 끝나는 시각이다. 그때까지 끝나지 않으면 다른 워커가 다시 가져간다.
    상태를 "버림" 으로 걸러 보면 끝내 보내지 못한 메일과 그 이유가 나온다.
    """

    list_display = ('to_email', 'subject', 'status', 'attempts', 'last_error', 'created_at', 'discarded_at')
    list_filter = ('status',)
    search_fields = ('to_email',)
    ordering = ('-created_at',)
    # 대기 중인 메일의 본문에는 인증 코드가 들어 있다. 화면에 보여 주지 않는다
    exclude = ('body',)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    # 삭제는 막지 않는다. 확인이 끝난 버려진 메일의 기록을 운영자가 지울 수 있어야 한다


@admin.register(SecurityEvent)
class SecurityEventAdmin(admin.ModelAdmin):
    """
    보안 이벤트를 조회만 한다. 운영자가 누가 시도 제한에 걸렸는지 확인하는 곳이다.

    기록이다. 관리자 화면에서 만들거나 고치거나 지울 수 있으면 기록으로서 믿을 수 없다.
    """

    list_display = ('created_at', 'kind', 'ip', 'user', 'note', 'reported_at')
    list_filter = ('kind',)
    search_fields = ('ip', 'user__username')
    date_hierarchy = 'created_at'
    # 목록을 그릴 때 행마다 계정을 따로 조회하지 않게 한다
    list_select_related = ('user',)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(WelcomeCredit)
class WelcomeCreditAdmin(admin.ModelAdmin):
    """
    환영 크레딧을 조회만 한다. 운영자가 결제 서버에 맡기지 못하고 밀려 있는 줄을 확인하는 곳이다.

    상태를 "맡기기 전" 으로 걸러 보면 아직 나가지 못한 줄과 마지막 오류가 나온다.
    줄을 지우면 그 사람이 환영 크레딧을 다시 받을 수 있게 된다. 그래서 지우는 것도 막는다.
    """

    list_display = (
        'user_public_id',
        'status',
        'attempts',
        'last_error',
        'created_at',
        'next_attempt_at',
        'finished_at',
    )
    list_filter = ('status',)
    search_fields = ('user_public_id',)
    ordering = ('-created_at',)
    # 받는 사람의 열쇠는 화면에 보여 주지 않는다. 볼 일이 없는 값이다
    exclude = ('recipient_key',)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(IdentityVerification)
class IdentityVerificationAdmin(admin.ModelAdmin):
    """
    본인인증의 기록을 조회만 한다(#336).

    만들거나 고치면 업체를 거치지 않고 성인이 된다. 지우면 같은 사람이 다른 계정에서 다시 인증할 수 있다.
    계정을 지우면 함께 지워진다.
    """

    list_display = ('user', 'provider', 'legal_adult_from', 'adult_content_from', 'verified_at')
    list_filter = ('provider',)
    search_fields = ('user__username',)
    ordering = ('-verified_at',)
    # 사람 열쇠는 화면에 보여 주지 않는다. 볼 일이 없는 값이다
    exclude = ('person_key',)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class ReadOnlyAdmin(admin.ModelAdmin):
    """조회만 하는 화면. 만들고 고치고 지우는 것은 API 와 워커가 한다."""

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(GuardianConsent)
class GuardianConsentAdmin(ReadOnlyAdmin):
    """
    보호자 동의를 조회만 한다(#336).

    고치면 보호자를 거치지 않고 결제가 열린다. 지우면 동의의 기록(누가 언제 동의했는지)이 사라진다.
    """

    list_display = ('minor', 'status', 'requested_at', 'consented_at', 'revoked_at')
    list_filter = ('status',)
    search_fields = ('minor__username',)
    ordering = ('-requested_at',)
    # 링크의 일회 값과 사람 열쇠는 보여 주지 않는다. 일회 값이 보이면 링크를 만들 수 있다
    exclude = ('link_nonce', 'guardian_person_key')


@admin.register(PaymentEligibility)
class PaymentEligibilityAdmin(ReadOnlyAdmin):
    """
    결제 서버에 알릴 결제 자격을 조회만 한다. 밀려 있는 줄을 확인하는 곳이다.

    알린 버전이 버전보다 작으면 아직 나가지 못한 것이다. 시도 횟수와 마지막 오류가 남아 있다.
    """

    list_display = ('user', 'version', 'delivered_version', 'attempts', 'last_error', 'next_attempt_at')
    search_fields = ('user__username',)
    ordering = ('next_attempt_at',)
