# auth-server/accounts/urls.py

"""
accounts 앱의 URL.

config/urls.py 가 이 파일을 /api/v1/auth/ 아래에 연결한다.
"""

from django.urls import path

from accounts.views import (
    JwksView,
    LoginResendView,
    LoginVerifyView,
    LoginView,
    LogoutAllView,
    LogoutView,
    MeView,
    RefreshView,
    SignupResendView,
    SignupVerifyView,
    SignupView,
)

app_name = 'accounts'

urlpatterns = [
    path('signup', SignupView.as_view(), name='signup'),
    path('signup/verify', SignupVerifyView.as_view(), name='signup-verify'),
    path('signup/resend', SignupResendView.as_view(), name='signup-resend'),
    path('login', LoginView.as_view(), name='login'),
    path('login/verify', LoginVerifyView.as_view(), name='login-verify'),
    path('login/resend', LoginResendView.as_view(), name='login-resend'),
    path('refresh', RefreshView.as_view(), name='refresh'),
    path('logout', LogoutView.as_view(), name='logout'),
    path('logout-all', LogoutAllView.as_view(), name='logout-all'),
    path('jwks', JwksView.as_view(), name='jwks'),
    path('me', MeView.as_view(), name='me'),
]