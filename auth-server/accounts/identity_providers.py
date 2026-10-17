# auth-server/accounts/identity_providers.py

"""
본인확인 업체(#336). 사용자가 업체의 화면에서 휴대폰으로 인증하고 받은 글자(token)를 업체에 물어 결과를 받는다.

결과 가운데 쓰는 것은 둘이다.
  - DI: 업체가 이 서비스에 주는 사람의 식별값. 같은 사람이면 언제 인증해도 같다. 한 사람 한 계정을 지키는 데 쓴다
  - 생일: 나이를 가르는 데 쓴다(age.py)
이름, 전화번호, 성별 같은 다른 결과는 받더라도 쓰지 않고 넘기지 않는다. 쓰지 않는 개인정보는 모으지 않는다.

DB 를 보지 않는다. 결과를 어떻게 쓰는지는 identity.py 가 정한다.
업체를 바꾸거나 더할 때 이 파일만 고친다. 고르는 것은 설정(IDENTITY_PROVIDER, config/identity.py)이다.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from django.conf import settings

from config.identity import DISABLED, FAKE

# 가짜 업체의 token 모양: fake:<DI>:<생일 YYYY-MM-DD>. 실제 DI 는 base64 로 88자다
FAKE_TOKEN = re.compile(r'fake:(?P<di>[A-Za-z0-9+/=_-]{1,128}):(?P<birth_date>\d{4}-\d{2}-\d{2})')


class IdentityTokenError(Exception):
    """업체가 그 token 을 모른다. 위조, 만료, 이미 쓴 token 을 가리지 않는다."""


class IdentityUnavailableError(Exception):
    """지금은 본인인증을 받을 수 없다. 업체를 꺼 두었거나 업체가 답하지 않는다."""


@dataclass(frozen=True)
class IdentityResult:
    """업체가 확인해 준 사람. 이 서비스가 쓰는 것만 담는다."""

    di: str
    birth_date: date


class IdentityProvider(Protocol):
    # 인증 기록에 남는 업체의 이름(IdentityVerification.provider)
    name: str

    def verify(self, token: str) -> IdentityResult:
        """token 으로 업체에 물어 결과를 받는다. 모르는 token 이면 IdentityTokenError."""
        ...


class FakeIdentityProvider:
    """
    가짜 업체. token 에 적힌 DI 와 생일을 그대로 믿는다. 개발과 테스트용이다.

    결제 서버의 가짜 결제 대행사와 같은 생각이다. 계약 없이 흐름 전체를 만들고 시험한다.
    운영에서는 고를 수 없다(config/identity.py).
    """

    name = FAKE

    def verify(self, token: str) -> IdentityResult:
        matched = FAKE_TOKEN.fullmatch(token)
        if matched is None:
            raise IdentityTokenError
        try:
            birth_date = date.fromisoformat(matched['birth_date'])
        except ValueError as exc:
            raise IdentityTokenError from exc
        return IdentityResult(di=matched['di'], birth_date=birth_date)


class DisabledIdentityProvider:
    """본인인증을 받지 않는다. 실제 업체가 붙기 전의 운영이다."""

    name = DISABLED

    def verify(self, token: str) -> IdentityResult:
        raise IdentityUnavailableError


_PROVIDERS: dict[str, type] = {
    FAKE: FakeIdentityProvider,
    DISABLED: DisabledIdentityProvider,
}


def get_identity_provider() -> IdentityProvider:
    """설정이 고른 업체. 이름은 설정을 읽을 때 확인했다."""
    return _PROVIDERS[settings.IDENTITY_PROVIDER]()
