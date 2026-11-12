# auth-server/accounts/apps.py

"""
계정의 앱. 가입, 로그인, 토큰, 본인인증, 탈퇴처럼 인증 서버의 일 대부분이 이 앱에 있다.
Django 가 INSTALLED_APPS 의 'accounts' 로 이 설정을 찾는다. 뜰 때 따로 하는 일(ready)은 없다.
"""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'accounts'
