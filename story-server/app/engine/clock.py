# story-server/app/engine/clock.py

"""
세션 안의 시각(docs/architecture/story.md 의 "시각"). 판과 시각만 보는 순수 함수다.

시각은 하나의 정수다. 1일째 0시 0분부터 흐른 분이다(chat 의 app/world/clock.py 와 같은 모양).
며칠째와 시간대는 그 수에서 계산한다. 날짜는 자정에 바뀐다.
시간대는 제작자가 정한 목록이다. 시간대 하나는 그 시작 시각부터 다음 시간대가 시작할 때까지다.
첫 시간대가 시작하기 전(예: 첫 시간대가 7시면 새벽 2시)은 마지막 시간대가 이어지는 것으로 본다.

시각을 흘리는 행동(이동, 시간 보내기, 하루 마치기)은 app/engine/actions.py 에 있다. 여기는 셈만 한다.
"""

from app.engine.world import World

MINUTES_PER_HOUR = 60
MINUTES_PER_DAY = 24 * MINUTES_PER_HOUR
# 처음의 날짜. 1일째부터 센다
FIRST_DAY = 1


def day_of(minutes: int) -> int:
    """그 시각이 며칠째인가. 1 부터."""
    return minutes // MINUTES_PER_DAY + FIRST_DAY


def day_start(day: int) -> int:
    """그날 0시의 시각."""
    return (day - FIRST_DAY) * MINUTES_PER_DAY


def slot_starts(world: World) -> list[tuple[int, str]]:
    """시간대마다 하루 안에서 시작하는 분과 그 id. 이른 것부터다."""
    return [(slot.start_hour * MINUTES_PER_HOUR, slot.id) for slot in world.slots]


def slot_of(world: World, minutes: int) -> str:
    """그 시각의 시간대. 첫 시간대가 시작하기 전은 마지막 시간대다(전날 밤이 이어진다)."""
    in_day = minutes % MINUTES_PER_DAY
    found = world.slots[-1].id
    for start, slot_id in slot_starts(world):
        if in_day >= start:
            found = slot_id
    return found


def start_minutes(world: World) -> int:
    """세션이 시작하는 시각. 1일째 처음의 시간대가 시작하는 때다."""
    slot = world.slot(world.start_slot) or world.slots[0]
    return day_start(FIRST_DAY) + slot.start_hour * MINUTES_PER_HOUR


def next_slot_start(world: World, minutes: int) -> int:
    """지금 뒤에 오는 가장 가까운 시간대의 시작. 오늘 남은 것이 없으면 다음 날의 첫 시간대다."""
    today = day_start(day_of(minutes))
    for start, _ in slot_starts(world):
        if today + start > minutes:
            return today + start
    return today + MINUTES_PER_DAY + slot_starts(world)[0][0]


def first_slot_after_rest(world: World, minutes: int) -> int:
    """
    하루를 마치고 닿는 시각. 다음 날의 첫 시간대다.

    자정을 넘겨 아직 그날의 첫 시간대가 오지 않았으면 그날의 첫 시간대다(잠들지 않은 밤이 이어진다).
    """
    today = day_start(day_of(minutes))
    first = slot_starts(world)[0][0]
    if minutes - today < first:
        return today + first
    return today + MINUTES_PER_DAY + first


def deadline_passed(world: World, minutes: int) -> bool:
    """그 시각에 기한이 지났는가. 기한이 N일이면 N+1일째가 된 때다. 기한이 없으면 지나지 않는다."""
    return world.deadline_days is not None and day_of(minutes) > world.deadline_days
