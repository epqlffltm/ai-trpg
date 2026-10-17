# auth-server/accounts/guardian_links.py

"""
보호자에게 보내는 두 링크의 서명과 확인(#336). DB 를 보지 않는다.

  - 동의 링크: 미성년자가 요청하면 보호자에게 간다. 7일 동안 쓸 수 있다
  - 철회 링크: 동의를 알리는 메일과 결제 알림 메일에 붙는다. 기한이 없다. 동의가 이어지는 동안 언제든 쓸 수 있다

링크에는 미성년자의 공개 ID 와 일회 값(GuardianConsent.link_nonce)을 서명해 넣는다.
미성년자가 새로 요청하면 일회 값이 바뀌어 앞서 보낸 링크는 쓸 수 없게 된다. 맞는지는 guardian.py 가 DB 와 견준다.
정수 PK 가 아니라 공개 ID 를 넣는다. 링크는 남의 메일함에 남는다.
"""

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from django.core import signing

# 서명에 섞는 값. 두 링크를 서로의 자리에, 다른 용도의 서명(가입 티켓)을 이 자리에 쓸 수 없게 한다
CONSENT_SALT = 'accounts.guardian.consent'
REVOKE_SALT = 'accounts.guardian.revoke'

# 보호자가 동의 링크를 열 때까지의 시간. 바쁜 보호자가 주말을 넘겨도 되게 둔다
CONSENT_LINK_LIFETIME = timedelta(days=7)


class InvalidGuardianLinkError(Exception):
    """링크가 위조됐거나 만료됐다. 이유를 구분하지 않는다."""


@dataclass(frozen=True)
class GuardianLink:
    """링크에서 꺼낸 것."""

    minor_public_id: UUID
    nonce: str


def issue_consent_token(*, minor_public_id: UUID, nonce: str) -> str:
    """동의 링크에 넣는 글자."""
    return signing.dumps(_payload(minor_public_id, nonce), salt=CONSENT_SALT)


def issue_revoke_token(*, minor_public_id: UUID, nonce: str) -> str:
    """철회 링크에 넣는 글자."""
    return signing.dumps(_payload(minor_public_id, nonce), salt=REVOKE_SALT)


def read_consent_token(token: str) -> GuardianLink:
    """동의 링크를 확인한다. 7일이 지났거나 쓸 수 없으면 InvalidGuardianLinkError."""
    return _read(token, salt=CONSENT_SALT, max_age=CONSENT_LINK_LIFETIME)


def read_revoke_token(token: str) -> GuardianLink:
    """철회 링크를 확인한다. 쓸 수 없으면 InvalidGuardianLinkError."""
    return _read(token, salt=REVOKE_SALT, max_age=None)


def _payload(minor_public_id: UUID, nonce: str) -> dict:
    return {'m': str(minor_public_id), 'n': nonce}


def _read(token: str, *, salt: str, max_age: timedelta | None) -> GuardianLink:
    try:
        payload = signing.loads(token, salt=salt, max_age=max_age)
    except signing.BadSignature as exc:
        # 만료(SignatureExpired)도 BadSignature 의 한 종류다
        raise InvalidGuardianLinkError from exc
    if not isinstance(payload, dict) or not isinstance(payload.get('n'), str):
        raise InvalidGuardianLinkError
    try:
        minor_public_id = UUID(payload.get('m'))
    except (TypeError, ValueError) as exc:
        raise InvalidGuardianLinkError from exc
    return GuardianLink(minor_public_id=minor_public_id, nonce=payload['n'])
