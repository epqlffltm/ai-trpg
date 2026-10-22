# auth-server/accounts/return_blocks.py

"""
정지된 채 탈퇴한 사람의 재가입을 막는다(#634).

  1. 남기기(record_return_blocks): 탈퇴를 마칠 때 정지 중이면, 그 사람의 본인인증의 사람 열쇠와 이메일의 값을 남긴다.
     둘 다 서버의 비밀키로 서명한 값이다. 계정과 잇지 않는다
  2. 막기: 새 계정이 본인인증하면(identity.py) 사유의 규칙대로 인증을 거절하거나 새 계정도 정지한다.
     가입 1단계(services.start_signup)에서 그 이메일이면 코드 대신 안내 메일을 보낸다
  3. 지우기(delete_expired_blocks): 기간이 지난 값을 지운다. 운영자는 관리 화면에서 지워 풀 수 있다

무엇을 막고 얼마 동안 둘지는 정지의 사유의 종류가 정한다(POLICIES, #634 의 사유 표).
본인인증은 가입할 때 하지 않으므로, 새 이메일로 가입해 인증하지 않고 쓰는 것은 막지 못한다.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from django.db import transaction
from django.utils.crypto import salted_hmac

from accounts.models import IdentityVerification, ReturnBlock, ReturnBlockKind, Suspension, SuspensionReason, User

# 이메일의 값을 만들 때 SECRET_KEY 에 섞는 값. 사람 열쇠(identity.PERSON_KEY_SALT)와 겹치지 않게 한다
EMAIL_KEY_SALT = 'accounts.return_blocks.email'


class IdentityRule(StrEnum):
    """정지된 채 탈퇴한 사람이 새 계정에서 본인인증하면."""

    # 인증만 거절한다. 결제, 환영 크레딧, 성인용 내용을 쓰지 못한다
    REFUSE = 'refuse'
    # 새 계정도 정지한다. 정지가 새 계정으로 이어진다
    SUSPEND = 'suspend'


@dataclass(frozen=True)
class ReturnPolicy:
    """사유의 종류 하나의 규칙. 같은 이메일로 가입하는 것은 모든 사유에서 막는다."""

    identity: IdentityRule
    keep_for: timedelta


# 사유의 표(#634, 2026-10-22 의 초안). 기간은 처리방침에 적고 변호사 검토에 넣는다
POLICIES: dict[str, ReturnPolicy] = {
    SuspensionReason.SPAM: ReturnPolicy(IdentityRule.REFUSE, timedelta(days=183)),
    SuspensionReason.ABUSE: ReturnPolicy(IdentityRule.SUSPEND, timedelta(days=365)),
    SuspensionReason.FRAUD: ReturnPolicy(IdentityRule.SUSPEND, timedelta(days=3 * 365)),
    SuspensionReason.ILLEGAL: ReturnPolicy(IdentityRule.SUSPEND, timedelta(days=5 * 365)),
    SuspensionReason.OTHER: ReturnPolicy(IdentityRule.REFUSE, timedelta(days=365)),
}


def email_key(email: str) -> str:
    """이메일의 값. 앞뒤 공백을 떼고 소문자로 맞춰 서버의 비밀키로 서명한다(HMAC-SHA256, 16진수 64자)."""
    return salted_hmac(EMAIL_KEY_SALT, email.strip().lower(), algorithm='sha256').hexdigest()


def policy_for(reason: str) -> ReturnPolicy:
    """사유의 종류의 규칙."""
    return POLICIES[reason]


def record_return_blocks(user: User, email: str, now: datetime) -> int:
    """
    그 계정이 정지 중이면 본인인증과 이메일의 값을 남기고, 남긴 수를 돌려준다. 정지 중이 아니면 0 이다.

    탈퇴를 마치는 트랜잭션 안에서, 계정을 비우고 기록을 지우기 전에 부른다(withdrawal.complete_withdrawal).
    본인인증을 하지 않은 계정은 이메일의 값만 남긴다.
    """
    suspension = Suspension.objects.filter(user=user, restored_at__isnull=True).first()
    if suspension is None:
        return 0
    expires_at = now + policy_for(suspension.reason).keep_for
    keys = [(ReturnBlockKind.EMAIL, email_key(email))]
    verification = IdentityVerification.objects.filter(user=user).first()
    if verification is not None:
        keys.append((ReturnBlockKind.IDENTITY, verification.person_key))
    for kind, key in keys:
        _keep_block(kind, key, suspension.reason, expires_at)
    return len(keys)


def _keep_block(kind: str, key: str, reason: str, expires_at: datetime) -> None:
    """
    그 값을 남긴다. 이미 있으면 더 늦게 지울 쪽의 사유와 기간으로 둔다.

    같은 사람이 다시 정지된 채 탈퇴한 경우다. 앞의 것보다 짧게 만들지 않는다.
    """
    with transaction.atomic():
        block = ReturnBlock.objects.select_for_update().filter(kind=kind, key=key).first()
        if block is None:
            ReturnBlock.objects.create(kind=kind, key=key, reason=reason, expires_at=expires_at)
            return
        if expires_at > block.expires_at:
            block.reason = reason
            block.expires_at = expires_at
            block.save(update_fields=['reason', 'expires_at'])


def active_block(kind: str, key: str, now: datetime) -> ReturnBlock | None:
    """그 값의 막기가 아직 살아 있으면 그 줄, 아니면 None. 기간이 지났는데 아직 지우지 않은 줄은 막지 않는다."""
    return ReturnBlock.objects.filter(kind=kind, key=key, expires_at__gt=now).first()


def delete_expired_blocks(now: datetime) -> int:
    """기간이 지난 값을 지우고, 지운 수를 돌려준다."""
    deleted, _ = ReturnBlock.objects.filter(expires_at__lte=now).delete()
    return deleted
