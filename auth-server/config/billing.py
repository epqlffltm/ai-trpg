# auth-server/config/billing.py

"""
다른 서버를 부르는 데 쓰는 설정(주소와 서명의 비밀)을 검사한다. 설정을 읽을 때 부른다(config/settings.py).
결제 서버에서 시작했고, 탈퇴를 알릴 서버들(#603)의 주소와 비밀도 같은 규칙으로 본다.

틀린 값은 서버가 뜨기 전에 드러나야 한다. 뜬 뒤 첫 가입자의 환영 크레딧에서야 알게 되면 늦다.
"""

from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

# 서명에 쓰는 비밀의 가장 짧은 길이. 결제 서버가 이보다 짧은 비밀로 만든 서명을 받지 않는다
MIN_SERVICE_SECRET_LENGTH = 32


def validate_billing_url(url: str, name: str = 'BILLING_URL') -> str:
    """
    다른 서버의 주소가 http(s) 주소인지 보고, 끝의 빗금을 뗀 주소를 돌려준다. name 은 오류에 적을 설정의 이름이다.

    file:// 같은 주소를 받으면 요청을 보내는 함수가 서버의 파일을 읽게 된다.
    """
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.netloc:
        raise ImproperlyConfigured(f'{name} 은 http:// 나 https:// 로 시작하는 주소여야 합니다.')
    return url.rstrip('/')


def validate_service_secret(secret: str, name: str = 'BILLING_SECRET') -> str:
    """
    다른 서버와 함께 아는 비밀의 길이를 본다. 비어 있는 것은 받는다. name 은 오류에 적을 설정의 이름이다.

    BILLING_SECRET 이 비어 있으면 환영 크레딧을 맡기는 워커만 돌지 못한다. 가입과 로그인은 이 값 없이 된다.
    탈퇴를 알릴 서버의 비밀이 비어 있으면 그 서버에는 알리지 않는다(알릴 줄은 쌓여 기다린다).
    오류에는 값을 싣지 않는다.
    """
    if secret and len(secret) < MIN_SERVICE_SECRET_LENGTH:
        raise ImproperlyConfigured(f'{name} 은 {MIN_SERVICE_SECRET_LENGTH}자 이상이어야 합니다.')
    return secret
