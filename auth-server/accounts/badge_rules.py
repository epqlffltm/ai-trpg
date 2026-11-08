# auth-server/accounts/badge_rules.py

"""
활동 배지(#193)의 목록과 규칙. DB 를 보지 않는다. 주고 읽는 일은 badges.py 가 한다.

배지는 인증 서버가 갖는다(2026-11-08 결정). 처음 묶음은 이 서버의 기록만으로 셀 수 있는
일반 도전과제다(출석, 본인인증, 초대).
TRPG·story·chat 의 판에서 생기는 일(첫 판 끝내기 같은 것)은 그 서버들이 사건을 알려 주는 길이 생긴 뒤에 더한다.
올라간 시나리오마다 따로 두는 업적은 이것과 다른 것이다. 여기에 섞지 않는다.

  - 배지마다 하나다. 단계(브론즈, 실버, 골드)를 두지 않는다
  - 보상(실버)은 없다. 배지만 준다
  - 본인만 본다. 다른 사람에게 보이는 것은 나중에 정한다

배지의 이름(id)은 기록에 그대로 남는다. 한번 정하면 바꾸지 않는다.
배지를 빼면 목록에서만 뺀다. 받은 기록은 지우지 않는다. 목록에 없는 기록은 응답에 나가지 않는다.
"""

from dataclasses import dataclass

from accounts import attendance_rules

# 배지의 이름. 기록과 응답에 그대로 나간다
FIRST_ATTENDANCE = 'first_attendance'
ATTENDANCE_CYCLE = 'attendance_cycle'
ATTENDANCE_30_DAYS = 'attendance_30_days'
DRAGON_HOARD = 'dragon_hoard'
IDENTITY_VERIFIED = 'identity_verified'
FIRST_INVITE = 'first_invite'

# 출석한 날을 모두 세어 이만큼이면 주는 배지의 날 수
ATTENDANCE_DAYS_GOAL = 30
# 보물 상자에서 나오면 배지를 주는 결과
DRAGON_HOARD_OUTCOME = 'dragon_hoard'


@dataclass(frozen=True)
class Badge:
    """배지 하나."""

    # 배지의 이름. 기록과 응답에 그대로 나간다
    id: str
    # 화면에 보이는 이름
    name: str
    # 어떻게 받는지. 받기 전에도 보인다
    description: str


# 화면에 보이는 차례다
BADGES: tuple[Badge, ...] = (
    Badge(FIRST_ATTENDANCE, '첫 출석', '처음으로 출석 보상을 받았다'),
    Badge(ATTENDANCE_CYCLE, '한 주기 완주', '하루도 빠지지 않고 출석해 주기의 마지막 날 보물 상자를 열었다'),
    Badge(ATTENDANCE_30_DAYS, '출석 30일', f'출석한 날이 모두 {ATTENDANCE_DAYS_GOAL}일이 되었다(이어지지 않아도 된다)'),
    Badge(DRAGON_HOARD, '용의 보물', '보물 상자에서 용의 보물을 찾았다'),
    Badge(IDENTITY_VERIFIED, '본인인증', '휴대폰 본인인증을 마쳤다'),
    Badge(FIRST_INVITE, '첫 초대', '초대한 친구가 본인인증을 마쳐 처음으로 초대 보상을 받았다'),
)

BADGE_IDS = frozenset(badge.id for badge in BADGES)


@dataclass(frozen=True)
class AttendanceFacts:
    """방금 받은 출석에서 배지를 가르는 데 쓰는 것."""

    # 이번이 출석한 날의 몇 번째인지(이번 것을 포함한다)
    total_days: int
    # 이번에 보물 상자를 열었는지
    opened_chest: bool
    # 연 상자의 결과. 열지 않았으면 None 이다
    chest_outcome: str | None


def attendance_badges(facts: AttendanceFacts) -> tuple[str, ...]:
    """방금 받은 출석으로 받을 수 있는 배지들. 이미 가진 것도 들어 있다(주는 쪽이 한 번만 준다)."""
    earned = []
    if facts.total_days >= 1:
        earned.append(FIRST_ATTENDANCE)
    if facts.opened_chest:
        earned.append(ATTENDANCE_CYCLE)
    if facts.total_days >= ATTENDANCE_DAYS_GOAL:
        earned.append(ATTENDANCE_30_DAYS)
    if facts.chest_outcome == DRAGON_HOARD_OUTCOME:
        earned.append(DRAGON_HOARD)
    return tuple(earned)


def validate_badges(badges: tuple[Badge, ...]) -> None:
    """목록이 맞는지 본다. 이름이 비지 않고 겹치지 않는다. 용의 보물의 결과가 지금의 상자 표에 있다."""
    ids = [badge.id for badge in badges]
    if any(not badge.id or not badge.name for badge in badges) or len(set(ids)) != len(ids):
        raise ValueError('배지의 이름이 비었거나 겹칩니다')
    outcomes = {outcome.id for outcome in attendance_rules.CURRENT_CHEST.outcomes}
    if DRAGON_HOARD_OUTCOME not in outcomes:
        raise ValueError(f'보물 상자의 표에 {DRAGON_HOARD_OUTCOME} 가 없습니다')
