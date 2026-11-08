# auth-server/accounts/attendance_rules.py

"""
출석과 보물 상자의 규칙. DB 를 보지 않는다. 적고 읽는 일은 attendance.py 가 한다.

출석은 결제 서버에서 이 서버로 옮겼다(2026-11-08 결정). 규칙은 결제 서버의 출석(#339)과 같다.
  - 본인인증을 한 사용자만 받는다. 한 사람이 계정을 여럿 만들어 받는 것을 본인인증이 막는다(한 사람 = 한 계정)
  - 날짜는 한국 날짜다. 자정(Asia/Seoul)에 바뀐다
  - 주기는 하루 양의 목록(ATTENDANCE_SILVER)의 길이다(기본 7일). 하루라도 빠지면 1일째부터 다시 센다
  - 주기의 마지막 날에 보물 상자를 함께 연다

보물 상자의 확률은 공개한다(GET /attendance/rewards). 무료로만 얻는 상자라 법의 공개 의무(게임산업법)는 없지만
믿고 쓰게 하려고 스스로 공개한다. 표는 설정이 아니라 코드에 둔다. 확률을 바꾸려면 공지를 먼저 하고 PR 로,
표를 고치지 않고 버전을 올린 새 표를 만든다. 연 상자마다 표의 버전을 적어 옛 표로 연 결과도 설명할 수 있다.
결과의 이름은 D&D SRD 5.1 에 있는 것에서 땄다(미믹, 고블린). 고유한 괴물과 상표는 쓰지 않는다.
"""

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# 날짜를 정하는 시간대
KOREA = ZoneInfo('Asia/Seoul')

# 주기의 가장 긴 날 수. 그보다 길면 마지막 날의 상자가 너무 멀다
MAX_CYCLE_LENGTH = 14
# 하루 양으로 받는 가장 큰 실버. 0 을 몇 개 더 붙인 실수를 막는다(결제 서버도 같은 상한으로 받는다)
MAX_DAILY_SILVER = 100_000
# 하루 양의 기본값. 1판(20 실버)을 하루 7판에서 시작해 하루 1판씩 늘린다. 한 주에 1,400 실버다
DEFAULT_SCHEDULE = (140, 160, 180, 200, 220, 240, 260)
# 확률의 단위. 만분율이다. 1000 은 10%, 1 은 0.01% 다. 소수를 쓰지 않아 더한 값을 틀림없이 본다
CHANCE_SCALE = 10_000


class InvalidScheduleError(ValueError):
    """하루 양의 목록이 틀렸다. 서버가 뜰 때 걸러진다."""


class InvalidChestError(ValueError):
    """보물 상자의 확률표가 틀렸다. 서버가 뜰 때 걸러진다."""


@dataclass(frozen=True)
class Outcome:
    """보물 상자에서 나올 수 있는 결과 하나."""

    # 결과의 이름. 기록과 응답에 그대로 나간다. 한번 정하면 바꾸지 않는다
    id: str
    # 화면에 보이는 이름
    name: str
    # 받는 실버. 0 이면 꽝이다
    silver: int
    # 나올 확률(만분율)
    chance: int


@dataclass(frozen=True)
class ChestTable:
    """버전이 붙은 확률표. 결과는 이 순서로 화면에 보인다. 확률을 모두 더하면 CHANCE_SCALE 이다."""

    version: str
    outcomes: tuple[Outcome, ...]


# 첫 확률표(2026-10-18, 결제 서버의 것을 그대로 옮겼다). 평균 617 실버다
CHEST_V1 = ChestTable(
    version='v1',
    outcomes=(
        Outcome('mimic_bite', '미믹 — 물렸다', 0, 1_000),
        Outcome('mimic_teeth', '미믹 — 이빨 사이의 동전', 100, 2_000),
        Outcome('goblin_pouch', '고블린의 주머니', 300, 3_000),
        Outcome('adventurer_pack', '모험가의 배낭', 600, 2_200),
        Outcome('treasure_hoard', '보물 더미', 1_500, 1_500),
        Outcome('dragon_hoard', '용의 보물', 5_000, 300),
    ),
)

# 지금 여는 상자의 표
CURRENT_CHEST = CHEST_V1


def validate_schedule(schedule: tuple[int, ...]) -> None:
    """하루 양의 목록이 맞는지 본다. 1 일에서 MAX_CYCLE_LENGTH 일까지, 날마다 1 에서 MAX_DAILY_SILVER 실버까지다."""
    if not 1 <= len(schedule) <= MAX_CYCLE_LENGTH:
        raise InvalidScheduleError(f'출석의 하루 양은 1 일에서 {MAX_CYCLE_LENGTH} 일까지여야 합니다')
    for day, silver in enumerate(schedule, start=1):
        if not 1 <= silver <= MAX_DAILY_SILVER:
            raise InvalidScheduleError(f'출석의 {day} 일째는 1 에서 {MAX_DAILY_SILVER} 실버 사이여야 합니다')


def parse_schedule(text: str) -> tuple[int, ...]:
    """설정의 글자("140,160,180")를 하루 양의 목록으로 읽는다. 비었으면 기본값이다. 틀렸으면 InvalidScheduleError."""
    if not text.strip():
        return DEFAULT_SCHEDULE
    try:
        schedule = tuple(int(part) for part in text.split(','))
    except ValueError as exc:
        raise InvalidScheduleError('출석의 하루 양은 쉼표로 나눈 정수여야 합니다') from exc
    validate_schedule(schedule)
    return schedule


def validate_chest(table: ChestTable) -> None:
    """
    표가 맞는지 본다.

    버전과 결과가 있고, 이름이 겹치지 않고, 확률은 1 이상으로 더하면 CHANCE_SCALE, 실버는 0 이상이다.
    """
    if not table.version or not table.outcomes:
        raise InvalidChestError('보물 상자의 확률표에 버전과 결과가 있어야 합니다')
    ids = [outcome.id for outcome in table.outcomes]
    if any(not one for one in ids) or len(set(ids)) != len(ids):
        raise InvalidChestError('보물 상자의 결과의 이름이 비었거나 겹칩니다')
    if any(outcome.chance < 1 or outcome.silver < 0 for outcome in table.outcomes):
        raise InvalidChestError('보물 상자의 확률은 1 이상, 실버는 0 이상이어야 합니다')
    total = sum(outcome.chance for outcome in table.outcomes)
    if total != CHANCE_SCALE:
        raise InvalidChestError(f'보물 상자의 확률을 더하면 {CHANCE_SCALE} 이어야 하는데 {total} 입니다')


def pick(table: ChestTable, n: int) -> Outcome:
    """0 이상 CHANCE_SCALE 미만의 수 n 에 해당하는 결과. 앞의 결과부터 확률만큼 구간을 차지한다."""
    for outcome in table.outcomes:
        if n < outcome.chance:
            return outcome
        n -= outcome.chance
    # 표가 틀렸거나 n 이 범위 밖이다. 마지막 것이 아니라 가장 앞의 것(꽝 쪽)을 준다
    return table.outcomes[0]


def expected_silver(table: ChestTable) -> int:
    """상자 하나에서 받는 실버의 평균(내림). 화면에 함께 보인다."""
    return sum(outcome.silver * outcome.chance for outcome in table.outcomes) // CHANCE_SCALE


def percent_of(chance: int) -> str:
    """만분율을 백분율의 글자로 쓴다. 1000 은 "10%", 250 은 "2.5%", 1 은 "0.01%" 다. 끝의 0 은 쓰지 않는다."""
    whole, rest = divmod(chance, 100)
    if rest == 0:
        return f'{whole}%'
    if rest % 10 == 0:
        return f'{whole}.{rest // 10}%'
    return f'{whole}.{rest:02d}%'


# 상자의 수를 고르는 것. 0 이상 CHANCE_SCALE 미만이다. 테스트가 정해진 수를 넣는다
Roll = Callable[[], int]


def crypto_roll() -> int:
    """운영체제의 난수로 상자의 수를 고른다. 다음 결과를 앞의 결과로 미루어 맞힐 수 없다."""
    return secrets.randbelow(CHANCE_SCALE)


def korean_date(now: datetime) -> date:
    """그 시각의 한국 날짜."""
    return now.astimezone(KOREA).date()


@dataclass(frozen=True)
class LastClaim:
    """그 사용자가 가장 최근에 출석한 날과 그날이 주기의 며칠째였는지."""

    day: date
    cycle_day: int


def cycle_day_on(last: LastClaim | None, today: date, length: int) -> int:
    """
    today 에 출석하면 주기의 며칠째인지 센다.

    어제 출석했고 주기가 아직 안 끝났으면 어제의 다음 날, 그 밖(처음, 하루라도 빠짐, 어제가 마지막 날)은 1일째다.
    오늘 이미 출석했는지는 보지 않는다. 주기를 줄였으면(설정) 어제가 새 주기의 길이를 넘어도 1일째다.
    """
    if last is not None and last.day == today - timedelta(days=1) and last.cycle_day < length:
        return last.cycle_day + 1
    return 1


def opens_chest(schedule: tuple[int, ...], cycle_day: int) -> bool:
    """주기의 cycle_day 일째에 보물 상자를 여는가. 마지막 날에 연다."""
    return cycle_day == len(schedule)


def silver_on(schedule: tuple[int, ...], cycle_day: int) -> int:
    """주기의 cycle_day 일째에 받는 실버. cycle_day 는 1 부터 주기의 길이까지다."""
    return schedule[cycle_day - 1]
