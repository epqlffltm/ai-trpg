# auth-server/accounts/identity_status.py

"""
계정의 본인인증 상태를 읽는다(#336). 고치지 않는다. 토큰(tokens.py)과 내 정보(views.MeView)가 함께 쓴다.

인증하는 쪽(identity.py)과 나눈 까닭: 인증하는 쪽은 세션을 끊으려고 tokens.py 를 부른다.
tokens.py 가 상태를 읽으려고 인증하는 쪽을 부르면 서로를 부르게 된다.
"""

from dataclasses import dataclass
from datetime import date

from accounts.age import has_reached
from accounts.models import IdentityVerification, User


@dataclass(frozen=True)
class IdentityStatus:
    """한 계정의 본인인증 상태. 날짜를 지난 것은 오늘 기준이다."""

    # 휴대폰 본인인증을 마쳤다
    verified: bool
    # 민법의 성년이다. 결제는 이것을 본다
    legal_adult: bool
    # 성인용 내용을 볼 수 있다(청소년 보호법). 토큰의 adult_content 가 이것이다
    adult_content: bool


# 본인인증을 하지 않은 계정. 나이를 모르니 어느 쪽도 성인으로 보지 않는다
UNVERIFIED = IdentityStatus(verified=False, legal_adult=False, adult_content=False)


def identity_status_of(user: User, today: date) -> IdentityStatus:
    """그 계정의 today 의 상태. 인증 기록을 한 번 읽는다."""
    verification = IdentityVerification.objects.filter(user=user).first()
    return status_from(verification, today)


def status_from(verification: IdentityVerification | None, today: date) -> IdentityStatus:
    """인증 기록에서 today 의 상태를 만든다. DB 를 보지 않는다."""
    if verification is None:
        return UNVERIFIED
    return IdentityStatus(
        verified=True,
        legal_adult=has_reached(verification.legal_adult_from, today),
        adult_content=has_reached(verification.adult_content_from, today),
    )
