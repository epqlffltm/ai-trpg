# auth-server/accounts/badges.py

"""
활동 배지(#193)를 주고 읽는다. 목록과 규칙은 badge_rules.py 다.

주는 함수는 일이 생기는 자리의 트랜잭션 안에서 불린다.
출석(attendance.py), 본인인증(identity.py), 초대 보상(invite_rewards.py)이다.
배지를 적는 일이 그 일과 함께 되거나 함께 안 된다. 따로 돌리는 워커가 없다.
이미 가진 배지를 다시 주면 아무 일도 없다. 유일 제약(사용자, 배지)이 막는다.
그 실패가 부르는 쪽의 트랜잭션을 깨지 않게 저장점을 쓴다.
"""

from dataclasses import dataclass
from datetime import datetime

from django.db import IntegrityError, transaction

from accounts import badge_rules as rules
from accounts.models import AttendanceClaim, User, UserBadge


@dataclass(frozen=True)
class BadgeState:
    """배지 하나와 내가 받았는지."""

    badge: rules.Badge
    # 받은 시각. 아직이면 None 이다
    earned_at: datetime | None


def award(user: User, badge_id: str, now: datetime) -> bool:
    """그 배지를 준다. 새로 줬으면 True, 이미 가졌으면 False 다. 모르는 배지면 ValueError."""
    if badge_id not in rules.BADGE_IDS:
        raise ValueError(f'모르는 배지입니다: {badge_id}')
    if UserBadge.objects.filter(user=user, badge=badge_id).exists():
        return False
    try:
        # 같은 배지를 함께 주는 다른 요청이 먼저 적었을 수 있다. 저장점으로 그 실패만 되돌린다
        with transaction.atomic():
            UserBadge.objects.create(user=user, badge=badge_id, earned_at=now)
    except IntegrityError:
        return False
    return True


def award_attendance(user: User, *, opened_chest: bool, chest_outcome: str | None, now: datetime) -> tuple[str, ...]:
    """방금 적은 출석으로 받을 배지를 주고, 새로 준 배지의 이름들을 돌려준다. 출석의 줄을 적은 뒤에 부른다."""
    facts = rules.AttendanceFacts(
        total_days=AttendanceClaim.objects.filter(user=user).count(),
        opened_chest=opened_chest,
        chest_outcome=chest_outcome,
    )
    return tuple(badge for badge in rules.attendance_badges(facts) if award(user, badge, now))


def my_badges(user: User) -> list[BadgeState]:
    """모든 배지를 목록의 차례로, 내가 받았는지와 함께. 목록에 없는 옛 배지의 기록은 넣지 않는다."""
    earned = dict(UserBadge.objects.filter(user=user).values_list('badge', 'earned_at'))
    return [BadgeState(badge=badge, earned_at=earned.get(badge.id)) for badge in rules.BADGES]
