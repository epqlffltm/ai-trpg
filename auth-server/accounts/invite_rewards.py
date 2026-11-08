# auth-server/accounts/invite_rewards.py

"""
초대 보상을 정한다(#990). 초대받은 사람이 휴대폰 본인인증을 마칠 때, 본인인증과 같은 트랜잭션에서 부른다(identity.py).

보상을 주는 것은 결제 서버다. 여기서는 "두 사람에게 준다"를 적기만 하고(InviteGrant 두 줄),
워커가 맡긴다(invite_grants.py).
본인인증 때 정하는 까닭: 휴대폰 본인인증의 사람 열쇠는 사람마다 하나다. 메일만 바꿔 계정을 늘려도 보상은 늘지 않는다.

주지 않는 경우(조용히 넘어간다. 본인인증은 그대로 된다):
  - 가입할 때 초대 코드를 적지 않았다
  - 이 사람은 전에 초대받은 사람으로 보상을 받았다(계정을 지우고 다시 가입한 경우)
  - 초대한 계정이 없거나 막혔다
  - 초대한 계정이 아직 본인인증을 하지 않았다. 사람을 모르면 상한을 셀 수 없다
  - 초대한 사람과 초대받은 사람이 같은 사람이다
  - 초대한 사람이 상한(INVITE_REWARD_LIMIT)만큼 이미 받았다. 상한이 0 이면 아무도 받지 않는다

상한을 세고 적는 사이에 다른 초대받은 사람의 보상이 끼어들지 않게 초대한 계정의 줄을 잠근다.
초대한 계정은 언제나 초대받은 계정보다 먼저 있으므로 두 계정을 서로 반대 차례로 잠그는 일은 없다.
"""

from django.conf import settings
from django.utils import timezone

from accounts.badge_rules import FIRST_INVITE
from accounts.badges import award
from accounts.models import (
    IdentityVerification,
    Invitation,
    InviteGrant,
    InviteGrantRole,
    InviteReward,
    User,
)


def request_invite_reward(*, invitee: User, invitee_key: str) -> InviteReward | None:
    """
    이 계정이 초대받아 가입했고 규칙에 맞으면 보상을 적고 돌려준다. 주지 않으면 None 이다.

    부르는 쪽의 트랜잭션 안에서 돈다. invitee_key 는 방금 인증한 사람의 열쇠다.
    """
    invitation = Invitation.objects.filter(invitee=invitee).first()
    if invitation is None or InviteReward.objects.filter(invitee_key=invitee_key).exists():
        return None
    inviter = _lock_active_inviter(invitation)
    if inviter is None:
        return None
    inviter_key = _person_key_of(inviter)
    if inviter_key is None or inviter_key == invitee_key or _limit_reached(inviter_key):
        return None
    return _record(invitee, inviter, invitee_key=invitee_key, inviter_key=inviter_key)


def rewarded_count(user: User) -> int:
    """이 계정의 사람이 초대한 사람으로서 받은 보상의 수. 본인인증을 하지 않았으면 0 이다."""
    key = _person_key_of(user)
    return 0 if key is None else InviteReward.objects.filter(inviter_key=key).count()


def _lock_active_inviter(invitation: Invitation) -> User | None:
    """초대한 계정의 줄을 잠그고 가져온다. 없거나 막혔으면 None 이다."""
    return User.objects.select_for_update().filter(public_id=invitation.inviter_public_id, is_active=True).first()


def _person_key_of(user: User) -> str | None:
    """계정의 사람 열쇠. 본인인증을 하지 않았으면 None 이다."""
    return IdentityVerification.objects.filter(user=user).values_list('person_key', flat=True).first()


def _limit_reached(inviter_key: str) -> bool:
    """초대한 사람이 받을 수 있는 만큼 이미 받았는가."""
    return InviteReward.objects.filter(inviter_key=inviter_key).count() >= settings.INVITE_REWARD_LIMIT


def _record(invitee: User, inviter: User, *, invitee_key: str, inviter_key: str) -> InviteReward:
    """보상과 결제 서버에 맡길 일 두 줄을 적는다."""
    reward = InviteReward.objects.create(
        invitee_key=invitee_key,
        inviter_key=inviter_key,
        invitee_public_id=invitee.public_id,
        inviter_public_id=inviter.public_id,
    )
    now = timezone.now()
    InviteGrant.objects.bulk_create(
        [
            InviteGrant(
                reward=reward, role=InviteGrantRole.INVITER, user_public_id=inviter.public_id, next_attempt_at=now
            ),
            InviteGrant(
                reward=reward, role=InviteGrantRole.INVITEE, user_public_id=invitee.public_id, next_attempt_at=now
            ),
        ]
    )
    # 초대한 사람의 활동 배지(#193). 초대한 계정에 준다
    award(inviter, FIRST_INVITE, now)
    return reward
