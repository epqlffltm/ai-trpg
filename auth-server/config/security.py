# auth-server/config/security.py

"""
운영 환경에서 켜야 하는 보안 설정을 정한다. 설정을 읽을 때 부른다(config/settings.py).

APP_ENVIRONMENT=production 이면 안전한 값이 저절로 켜진다. 하나씩 켜는 환경 변수를 두지 않았다.
운영에서 하나라도 켜기를 잊으면 그 빈틈이 그대로 남기 때문이다. 안전하지 않은 값을 운영에서 고르면 서버가 뜨지 않는다.

refresh 쿠키의 Secure 와 쿠키의 출처는 staging 에서도 같이 검사한다. staging 도 도메인과 HTTPS 뒤에 있다
(바깥에 연 환경, config/environments.py). 관리자 화면의 쿠키는 운영에서만 Secure 다. 둘 다 SSH 터널(localhost)로 연다.

HTTPS 로 넘기기(SECURE_SSL_REDIRECT)와 HSTS 는 여기서 하지 않는다. 서버 넷 앞의 nginx 가 TLS 와 함께 맡는다.
  - HSTS 는 도메인 전체에 거는 약속이다. 인증 서버가 내면 인증 서버의 응답에만 붙는다.
  - 인증 서버가 HTTPS 로 넘기면, 컨테이너끼리 HTTP 로 부르는 것(다른 서버가 공개키를 받는 것, 상태 확인)이
    301 로 튕긴다.
그래서 manage.py check --deploy 의 두 경고(W004, W008)는 이유를 적어 끈다(SILENCED_DEPLOY_CHECKS).
"""

import re

from django.core.exceptions import ImproperlyConfigured

from config.environments import is_deployed, is_production

# 프록시가 넘기는 "원래 요청이 HTTPS 였다"는 머리말. nginx 가 X-Forwarded-Proto 로 넘긴다(docker/nginx/)
FORWARDED_PROTO_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# check --deploy 에서 끄는 경고. 위의 이유로 nginx 가 맡는 일이다
SILENCED_DEPLOY_CHECKS = [
    # HSTS(SECURE_HSTS_SECONDS)
    'security.W004',
    # HTTPS 로 넘기기(SECURE_SSL_REDIRECT)
    'security.W008',
]


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
    바깥에 연 환경(staging, production)인데 refresh 토큰 쿠키의 Secure 를 껐으면 서버가 뜨지 않게 한다.

    Secure 가 없으면 브라우저가 HTTP 로도 쿠키를 보낸다. refresh 토큰이 평문으로 지나간다.
    .env.example 은 로컬 개발에 맞춰 false 라서, 옮겨 적으면 틀린 채로 뜨지 않게 staging 도 막는다.
    """
    if not secure and is_deployed(environment):
        raise ImproperlyConfigured(
            f'바깥에 연 환경(APP_ENVIRONMENT={environment})에서는 REFRESH_COOKIE_SECURE 를 끌 수 없습니다.'
        )


# 개발 환경에서 REFRESH_COOKIE_ALLOWED_ORIGINS 를 적지 않았을 때 허용하는 출처.
# docker compose 의 nginx 주소(PROXY_PORT 의 기본값 8080)다. 바깥에 연 환경(staging, production)에는 기본값이 없다
DEVELOPMENT_COOKIE_ORIGINS = ('http://localhost:8080', 'http://127.0.0.1:8080')

# 출처는 "scheme://host[:port]" 다. 경로, 물음표, 사용자 정보는 들어가지 않는다(브라우저의 Origin 머리말과 같은 모양).
# 호스트는 도메인, IPv4, 대괄호로 싼 IPv6 다
ORIGIN_PATTERN = re.compile(r'https?://(?:[a-z0-9.-]+|\[[0-9a-f:.]+\])(?::[0-9]{1,5})?')


def default_cookie_origins(environment: str) -> list[str]:
    """
    REFRESH_COOKIE_ALLOWED_ORIGINS 를 적지 않았을 때의 값. 바깥에 연 환경이면 비어 있다(그러면 뜨지 않는다).

    개발의 기본값(http://localhost:8080)이 staging 에 들어가면 화면의 도메인과 맞지 않아 refresh 가 늘 거절된다.
    """
    if is_deployed(environment):
        return []
    return list(DEVELOPMENT_COOKIE_ORIGINS)


def parse_cookie_origin(value: str) -> str:
    """
    설정에 적힌 출처 하나를 브라우저가 보내는 모양(소문자, 끝의 / 없음)으로 바꾼다. 모양이 틀리면 뜨지 않는다.

    끝의 / 는 떼어 준다. 브라우저의 Origin 에는 붙지 않아 그대로 두면 영영 맞지 않는다.
    경로가 붙은 값은 고쳐 주지 않고 거부한다. 무엇을 뜻했는지 짐작하지 않는다.
    """
    origin = value.strip().lower().removesuffix('/')
    if not ORIGIN_PATTERN.fullmatch(origin):
        raise ImproperlyConfigured(
            f'REFRESH_COOKIE_ALLOWED_ORIGINS 의 값은 https://example.com 처럼 경로 없이 적습니다: {value!r}'
        )
    return origin


def require_cookie_origins(origins: list[str], environment: str) -> None:
    """
    refresh 쿠키를 받을 출처의 목록을 확인한다. 비어 있거나, 바깥에 연 환경인데 https 가 아닌 것이 있으면 뜨지 않는다.

    비어 있으면 refresh 와 logout 이 늘 거부된다. 운영에서 http 출처를 허용하면 쿠키를 쓰는 요청을
    평문 페이지가 보낼 수 있다.
    """
    if not origins:
        raise ImproperlyConfigured('REFRESH_COOKIE_ALLOWED_ORIGINS 가 비어 있습니다. 화면을 여는 주소를 적습니다.')
    if is_deployed(environment):
        insecure = [origin for origin in origins if not origin.startswith('https://')]
        if insecure:
            raise ImproperlyConfigured(
                f'바깥에 연 환경(APP_ENVIRONMENT={environment})에서는 REFRESH_COOKIE_ALLOWED_ORIGINS 에 '
                f'https 출처만 적습니다: {", ".join(insecure)}'
            )


def proxy_ssl_header(trusted_proxy_count: int) -> tuple[str, str] | None:
    """
    "원래 요청이 HTTPS 였다"를 프록시의 머리말로 알지(SECURE_PROXY_SSL_HEADER). 앞에 프록시가 있을 때만 믿는다.

    IP 를 프록시의 머리말로 알 때(TRUSTED_PROXY_COUNT)와 같은 규칙이다. 프록시가 없는데 믿으면
    누구나 그 머리말을 적어 HTTPS 로 온 척할 수 있다. 우리 nginx 는 이 머리말을 늘 제 값으로 덮어쓴다.
    """
    if trusted_proxy_count > 0:
        return FORWARDED_PROTO_HEADER
    return None
