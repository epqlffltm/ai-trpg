# auth-server/accounts/urls.py

"""
accounts 앱의 URL.

config/urls.py 가 이 파일을 /api/v1/auth/ 아래에 연결한다.
"""

from django.urls import path

from accounts.app_views import AppLoginVerifyView, AppLogoutView, AppPasswordChangeView, AppRefreshView
from accounts.views import (
    ConsentDocumentsView,
    CreatorSearchView,
    CreatorView,
    GuardianConsentView,
    GuardianRequestView,
    GuardianRevokeView,
    IdentityVerifyView,
    JwksView,
    LoginResendView,
    LoginVerifyView,
    LoginView,
    LogoutAllView,
    LogoutView,
    MeView,
    MyConsentsView,
    MyConsentView,
    MyContentSettingsView,
    MyCreatorBlockView,
    MyInviteView,
    MyProfileView,
    MyTagBlockView,
    MyWithdrawalView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PublicNamesView,
    RefreshView,
    ServiceGuardianNoticeView,
    ServiceReceiptNoticeView,
    SessionRevocationsView,
    SignupCompleteView,
    SignupVerifyView,
    SignupView,
)

app_name = 'accounts'

urlpatterns = [
    path('signup', SignupView.as_view(), name='signup'),
    path('signup/verify', SignupVerifyView.as_view(), name='signup-verify'),
    path('signup/complete', SignupCompleteView.as_view(), name='signup-complete'),
    path('login', LoginView.as_view(), name='login'),
    path('login/verify', LoginVerifyView.as_view(), name='login-verify'),
    path('login/resend', LoginResendView.as_view(), name='login-resend'),
    path('password/change', PasswordChangeView.as_view(), name='password-change'),
    path('password/reset', PasswordResetRequestView.as_view(), name='password-reset'),
    path('password/reset/confirm', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('refresh', RefreshView.as_view(), name='refresh'),
    # 앱(#429). refresh 토큰을 쿠키 대신 본문으로 주고받는다(accounts/app_views.py)
    path('app/login/verify', AppLoginVerifyView.as_view(), name='app-login-verify'),
    path('app/refresh', AppRefreshView.as_view(), name='app-refresh'),
    path('app/logout', AppLogoutView.as_view(), name='app-logout'),
    path('app/password/change', AppPasswordChangeView.as_view(), name='app-password-change'),
    path('logout', LogoutView.as_view(), name='logout'),
    path('logout-all', LogoutAllView.as_view(), name='logout-all'),
    path('jwks', JwksView.as_view(), name='jwks'),
    path('session-revocations', SessionRevocationsView.as_view(), name='session-revocations'),
    path('me', MeView.as_view(), name='me'),
    path('consents', ConsentDocumentsView.as_view(), name='consents'),
    path('public-names', PublicNamesView.as_view(), name='public-names'),
    path('creators', CreatorSearchView.as_view(), name='creator-search'),
    path('creators/<uuid:public_id>', CreatorView.as_view(), name='creator'),
    path('me/consents', MyConsentsView.as_view(), name='my-consents'),
    path('me/consents/<str:item>', MyConsentView.as_view(), name='my-consent'),
    path('me/withdrawal', MyWithdrawalView.as_view(), name='my-withdrawal'),
    path('me/invite', MyInviteView.as_view(), name='my-invite'),
    path('me/content-settings', MyContentSettingsView.as_view(), name='my-content-settings'),
    path('me/profile', MyProfileView.as_view(), name='my-profile'),
    path('me/blocks/creators/<uuid:public_id>', MyCreatorBlockView.as_view(), name='my-creator-block'),
    path('me/blocks/tags/<path:tag>', MyTagBlockView.as_view(), name='my-tag-block'),
    path('identity/verify', IdentityVerifyView.as_view(), name='identity-verify'),
    path('guardian/request', GuardianRequestView.as_view(), name='guardian-request'),
    path('guardian/consent', GuardianConsentView.as_view(), name='guardian-consent'),
    path('guardian/revoke', GuardianRevokeView.as_view(), name='guardian-revoke'),
    path('service/guardian-notices', ServiceGuardianNoticeView.as_view(), name='service-guardian-notices'),
    path('service/receipt-notices', ServiceReceiptNoticeView.as_view(), name='service-receipt-notices'),
]
