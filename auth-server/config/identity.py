# auth-server/config/identity.py

"""
본인확인 업체의 설정(IDENTITY_PROVIDER)을 검사한다. 설정을 읽을 때 부른다(config/settings.py).

업체는 둘 중 하나다(#336).
  - fake      가짜 업체. 받은 글자를 그대로 믿는다. 개발과 테스트용이다
  - disabled  본인인증을 받지 않는다. 인증 요청이 503 으로 끝난다

실제 업체(NICE, KCB 같은 휴대폰 본인확인 기관)는 사업자 계약이 있어야 붙일 수 있다. 붙이면 이 목록에 더한다.
그때까지 운영은 disabled 로 뜬다. 가짜 업체를 운영에서 쓰면 누구나 아무 생일이나 적어 성인이 될 수 있다.
"""

from django.core.exceptions import ImproperlyConfigured

from config.environments import is_production

FAKE = 'fake'
DISABLED = 'disabled'
KNOWN_PROVIDERS = (FAKE, DISABLED)


def default_identity_provider(environment: str) -> str:
    """IDENTITY_PROVIDER 를 적지 않았을 때의 값. 운영이면 disabled, 아니면 fake 다."""
    if is_production(environment):
        return DISABLED
    return FAKE


def validate_identity_provider(name: str, environment: str) -> str:
    """업체의 이름을 확인하고 돌려준다. 모르는 이름이거나 운영에서 가짜 업체를 고르면 서버가 뜨지 않는다."""
    if name not in KNOWN_PROVIDERS:
        raise ImproperlyConfigured(f'IDENTITY_PROVIDER 는 {", ".join(KNOWN_PROVIDERS)} 중 하나입니다: {name!r}')
    if name == FAKE and is_production(environment):
        raise ImproperlyConfigured(
            '운영 환경(APP_ENVIRONMENT=production)에서는 IDENTITY_PROVIDER=fake 를 쓸 수 없습니다.'
        )
    return name
