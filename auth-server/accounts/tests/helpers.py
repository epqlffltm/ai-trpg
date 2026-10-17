# auth-server/accounts/tests/helpers.py

"""
여러 테스트 파일이 함께 쓰는 도우미.

로그인이 두 단계가 되면서, "로그인한 상태" 를 만드는 과정이 여러 파일에 필요해졌다.
"""

import re

from django.conf import settings
from django.core import mail
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from config.redis_client import get_redis

LOGIN_URL = reverse('accounts:login')
LOGIN_VERIFY_URL = reverse('accounts:login-verify')
SIGNUP_URL = reverse('accounts:signup')
SIGNUP_VERIFY_URL = reverse('accounts:signup-verify')
SIGNUP_COMPLETE_URL = reverse('accounts:signup-complete')


class BrowserClient(APIClient):
    """
    우리 화면의 브라우저처럼 요청마다 Origin 을 붙이는 클라이언트.

    브라우저는 POST 에 Origin 을 늘 붙이고, refresh 와 logout 은 허용한 출처의 요청만 받는다(accounts/origin_check.py).
    붙이는 값은 허용 목록의 첫 출처다. 요청에 HTTP_ORIGIN 을 직접 주면 그 값이 쓰인다.
    """

    def __init__(self, *args, **defaults):
        defaults.setdefault('HTTP_ORIGIN', settings.REFRESH_COOKIE_ALLOWED_ORIGINS[0])
        super().__init__(*args, **defaults)


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


def request_signup_ticket(client, email: str) -> str:
    """
    가입의 1, 2단계(이메일 → 코드)를 지나 가입 티켓을 받는다.

    코드는 방금 나간 메일에서 꺼낸다. 테스트 중에는 메일이 mail.outbox 에 쌓인다.
    """
    started = client.post(SIGNUP_URL, {'email': email}, format='json')
    assert started.status_code == status.HTTP_202_ACCEPTED, started.data
    verified = client.post(SIGNUP_VERIFY_URL, {'email': email, 'code': code_from(mail.outbox[-1])}, format='json')
    assert verified.status_code == status.HTTP_200_OK, verified.data
    return verified.data['signup_ticket']


def complete_signup(client, ticket: str, *, username: str, nickname: str, password: str):
    """가입의 3단계만 보낸다."""
    payload = {'signup_ticket': ticket, 'username': username, 'nickname': nickname, 'password': password}
    return client.post(SIGNUP_COMPLETE_URL, payload, format='json')


def sign_up(client, *, username: str, email: str, nickname: str, password: str):
    """가입의 세 단계를 모두 지나고, 마지막 응답을 돌려준다."""
    ticket = request_signup_ticket(client, email)
    return complete_signup(client, ticket, username=username, nickname=nickname, password=password)


def delete_attempt_keys() -> None:
    """
    시도 횟수를 모두 지운다. 테스트용 앞머리가 붙은 키만 지워서, 개발용 횟수는 건드리지 않는다.

    제한을 켜고 도는 테스트가 앞뒤로 부른다. 지우지 않으면 앞 테스트의 횟수가 다음 테스트를 막는다.
    """
    client = get_redis()
    for key in client.scan_iter(match=f'{settings.ATTEMPT_LIMIT_KEY_PREFIX}:*'):
        client.delete(key)
