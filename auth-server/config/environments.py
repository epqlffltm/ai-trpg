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

PRODUCTION = 'production'
STAGING = 'staging'
# 도메인과 HTTPS 뒤에 둔 환경
DEPLOYED = frozenset({STAGING, PRODUCTION})


def is_production(environment: str) -> bool:
    """이 환경이 운영인가."""
    return environment == PRODUCTION


def is_deployed(environment: str) -> bool:
    """이 환경을 바깥에 열었는가(staging, production)."""
    return environment in DEPLOYED
