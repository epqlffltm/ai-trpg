# auth-server/accounts/urls.py

"""
accounts 앱의 URL.

config/urls.py 가 이 파일을 /api/v1/auth/ 아래에 연결한다.
"""

from django.urls import path

from accounts.views import JwksView, LoginView, MeView, SignupView

app_name = 'accounts'

urlpatterns = [
    path('signup', SignupView.as_view(), name='signup'),
    path('login', LoginView.as_view(), name='login'),
    path('jwks', JwksView.as_view(), name='jwks'),
    path('me', MeView.as_view(), name='me'),
]