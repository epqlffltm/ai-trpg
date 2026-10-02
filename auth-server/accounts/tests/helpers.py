# auth-server/accounts/tests/helpers.py

"""
여러 테스트 파일이 함께 쓰는 도우미.

로그인이 두 단계가 되면서, "로그인한 상태" 를 만드는 과정이 여러 파일에 필요해졌다.
"""

import re

from django.core import mail
from django.urls import reverse
from rest_framework import status

LOGIN_URL = reverse('accounts:login')
LOGIN_VERIFY_URL = reverse('accounts:login-verify')


def code_from(message) -> str:
    """메일 본문에서 6자리 인증 코드를 꺼낸다."""
    return re.search(r'\b(\d{6})\b', message.body).group(1)


def wrong_code_for(code: str) -> str:
    return '000000' if code != '000000' else '111111'


def start_login(client, username: str, password: str):
    """로그인의 1단계만 보낸다."""
    return client.post(LOGIN_URL, {'username': username, 'password': password}, format='json')


def log_in(client, username: str, password: str):
    """
    로그인의 두 단계를 모두 거치고, 토큰이 담긴 마지막 응답을 돌려준다.

    코드는 방금 나간 메일에서 꺼낸다. 테스트 중에는 메일이 mail.outbox 에 쌓인다.
    """
    started = start_login(client, username, password)
    assert started.status_code == status.HTTP_202_ACCEPTED, started.data
    return client.post(
        LOGIN_VERIFY_URL,
        {'login_ticket': started.data['login_ticket'], 'code': code_from(mail.outbox[-1])},
        format='json',
    )