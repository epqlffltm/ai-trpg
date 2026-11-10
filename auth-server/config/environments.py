# auth-server/config/environments.py

"""
APP_ENVIRONMENT 의 이름과, 그 이름이 어떤 환경인지를 정한다. 설정의 검사들(config/security.py 등)이 부른다.

환경은 둘로 가른다.
  - 운영(production)        실제 사용자가 쓴다. 가짜 본인인증과 터미널 메일도 막는다
  - 바깥에 연 환경(deployed)  staging 과 production. 도메인과 HTTPS 뒤에 있다(VM 의 nginx 가 TLS 를 끝낸다)

바깥에 연 환경에서는 전송의 안전(DEBUG, refresh 쿠키의 Secure, https 인 쿠키의 출처)을 고를 수 없다.
staging 은 운영자 혼자 쓰는 서버라 가짜 본인인증과 터미널 메일은 허용한다.
남이 들어오는 것은 nginx 의 허용 주소가 막는다.
"""

from django.core.exceptions import ImproperlyConfigured

DEVELOPMENT = 'development'
TEST = 'test'
PRODUCTION = 'production'
STAGING = 'staging'
# 받는 이름은 이 넷뿐이다(#1261). 보호는 이름이 staging, production 과 정확히 같을 때만 걸린다.
# 모르는 이름(prod, stage, live)을 받으면 그 환경은 조용히 개발 환경처럼 뜬다. DEBUG 금지, Secure 쿠키,
# 가짜 본인인증 금지가 모두 꺼진 채다. 그래서 모르는 이름으로는 뜨지 않게 한다
KNOWN = (DEVELOPMENT, TEST, STAGING, PRODUCTION)
# 도메인과 HTTPS 뒤에 둔 환경
DEPLOYED = frozenset({STAGING, PRODUCTION})


def is_production(environment: str) -> bool:
    """이 환경이 운영인가."""
    return environment == PRODUCTION


def is_deployed(environment: str) -> bool:
    """이 환경을 바깥에 열었는가(staging, production)."""
    return environment in DEPLOYED


def require_known(environment: str) -> None:
    """환경의 이름이 받는 이름(KNOWN) 가운데 하나인지 확인한다. 아니면 ImproperlyConfigured(서버가 뜨지 않는다)."""
    if environment not in KNOWN:
        raise ImproperlyConfigured(
            f'APP_ENVIRONMENT 는 {", ".join(KNOWN)} 가운데 하나여야 합니다: {environment!r}. '
            '다른 이름은 개발 환경처럼 떠서 운영의 보호가 걸리지 않습니다.'
        )
