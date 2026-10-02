# auth-server/accounts/urls.py

"""
accounts 앱의 URL.

config/urls.py 가 이 파일을 /api/v1/auth/ 아래에 연결한다.
"""

from django.urls import path

from accounts.views import (
    JwksView,
    LoginView,
    LogoutAllView,
    LogoutView,
    MeView,
    RefreshView,
    SignupView,
)

app_name = 'accounts'

urlpatterns = [
    path('signup', SignupView.as_view(), name='signup'),
    path('login', LoginView.as_view(), name='login'),
    path('refresh', RefreshView.as_view(), name='refresh'),
    path('logout', LogoutView.as_view(), name='logout'),
    path('logout-all', LogoutAllView.as_view(), name='logout-all'),
    path('jwks', JwksView.as_view(), name='jwks'),
    path('me', MeView.as_view(), name='me'),
]