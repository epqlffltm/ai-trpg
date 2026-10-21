# auth-server/accounts/urls.py

"""
accounts 앱의 URL.

config/urls.py 가 이 파일을 /api/v1/auth/ 아래에 연결한다.
"""

from django.urls import path

from accounts.views import (
    ConsentDocumentsView,
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
    MyWithdrawalView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PublicNamesView,
    RefreshView,
    ServiceGuardianNoticeView,
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
    path('logout', LogoutView.as_view(), name='logout'),
    path('logout-all', LogoutAllView.as_view(), name='logout-all'),
    path('jwks', JwksView.as_view(), name='jwks'),
    path('session-revocations', SessionRevocationsView.as_view(), name='session-revocations'),
    path('me', MeView.as_view(), name='me'),
    path('consents', ConsentDocumentsView.as_view(), name='consents'),
    path('public-names', PublicNamesView.as_view(), name='public-names'),
    path('me/consents', MyConsentsView.as_view(), name='my-consents'),
    path('me/consents/<str:item>', MyConsentView.as_view(), name='my-consent'),
    path('me/withdrawal', MyWithdrawalView.as_view(), name='my-withdrawal'),
    path('identity/verify', IdentityVerifyView.as_view(), name='identity-verify'),
    path('guardian/request', GuardianRequestView.as_view(), name='guardian-request'),
    path('guardian/consent', GuardianConsentView.as_view(), name='guardian-consent'),
    path('guardian/revoke', GuardianRevokeView.as_view(), name='guardian-revoke'),
    path('service/guardian-notices', ServiceGuardianNoticeView.as_view(), name='service-guardian-notices'),
]
