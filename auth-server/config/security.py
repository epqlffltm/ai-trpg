# auth-server/config/security.py

"""
운영 환경에서 켜야 하는 보안 설정을 정한다. 설정을 읽을 때 부른다(config/settings.py).

APP_ENVIRONMENT=production 이면 안전한 값이 저절로 켜진다. 하나씩 켜는 환경 변수를 두지 않았다.
운영에서 하나라도 켜기를 잊으면 그 빈틈이 그대로 남기 때문이다. 안전하지 않은 값을 운영에서 고르면 서버가 뜨지 않는다.

HTTPS 로 넘기기(SECURE_SSL_REDIRECT)와 HSTS 는 여기서 하지 않는다. 서버 넷 앞의 nginx 가 TLS 와 함께 맡는다.
  - HSTS 는 도메인 전체에 거는 약속이다. 인증 서버가 내면 인증 서버의 응답에만 붙는다.
  - 인증 서버가 HTTPS 로 넘기면, 컨테이너끼리 HTTP 로 부르는 것(다른 서버가 공개키를 받는 것, 상태 확인)이 301 로 튕긴다.
그래서 manage.py check --deploy 의 두 경고(W004, W008)는 이유를 적어 끈다(SILENCED_DEPLOY_CHECKS).
"""

from django.core.exceptions import ImproperlyConfigured

from config.mail_backends import PRODUCTION

# 프록시가 넘기는 "원래 요청이 HTTPS 였다"는 머리말. nginx 가 X-Forwarded-Proto 로 넘긴다(docker/nginx/)
FORWARDED_PROTO_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# check --deploy 에서 끄는 경고. 위의 이유로 nginx 가 맡는 일이다
SILENCED_DEPLOY_CHECKS = [
    # HSTS(SECURE_HSTS_SECONDS)
    'security.W004',
    # HTTPS 로 넘기기(SECURE_SSL_REDIRECT)
    'security.W008',
]


def is_production(environment: str) -> bool:
    """이 환경이 운영인가."""
    return environment == PRODUCTION


def secure_cookies(environment: str) -> bool:
    """
    세션 쿠키와 CSRF 쿠키에 Secure 를 붙일지. 운영이면 붙인다.

    두 쿠키는 관리자 화면에만 쓰인다. API 는 쿠키 대신 access 토큰을 쓴다.
    관리자 화면은 SSH 터널로 http://localhost 에서 연다. 브라우저는 localhost 를 안전한 곳으로 보아
    HTTP 여도 Secure 쿠키를 주고받는다.
    """
    return is_production(environment)


def require_secure_refresh_cookie(secure: bool, environment: str) -> None:
    """
    운영 환경인데 refresh 토큰 쿠키의 Secure 를 껐으면 서버가 뜨지 않게 한다.

    Secure 가 없으면 브라우저가 HTTP 로도 쿠키를 보낸다. refresh 토큰이 평문으로 지나간다.
    """
    if not secure and is_production(environment):
        raise ImproperlyConfigured('운영 환경(APP_ENVIRONMENT=production)에서는 REFRESH_COOKIE_SECURE 를 끌 수 없습니다.')


def proxy_ssl_header(trusted_proxy_count: int) -> tuple[str, str] | None:
    """
    "원래 요청이 HTTPS 였다"를 프록시의 머리말로 알지(SECURE_PROXY_SSL_HEADER). 앞에 프록시가 있을 때만 믿는다.

    IP 를 프록시의 머리말로 알 때(TRUSTED_PROXY_COUNT)와 같은 규칙이다. 프록시가 없는데 믿으면
    누구나 그 머리말을 적어 HTTPS 로 온 척할 수 있다. 우리 nginx 는 이 머리말을 늘 제 값으로 덮어쓴다.
    """
    if trusted_proxy_count > 0:
        return FORWARDED_PROTO_HEADER
    return None
