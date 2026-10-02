# auth-server/accounts/urls.py

"""
accounts 앱의 URL.

config/urls.py 가 이 파일을 /api/v1/auth/ 아래에 연결한다.
"""

from django.urls import path

from accounts.views import SignupView

app_name = 'accounts'

urlpatterns = [
    path('signup', SignupView.as_view(), name='signup'),
]