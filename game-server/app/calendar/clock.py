# game-server/app/calendar/clock.py

"""
게임 안의 시각을 셈한다. DB 도 판도 모르는 순수한 함수만 둔다.

시각은 하나의 정수다. 1일째 0시 0분부터 흐른 분(minutes)이다.
며칠째, 몇 시, 몇 분, 하루의 어느 때(새벽, 아침, 낮, 저녁, 밤)는 그 수에서 계산한다.
따로 적지 않으므로 서로 어긋날 일이 없다. 달과 해, 요일은 없다(달력 1단계).
"""

import enum
from dataclasses import dataclass

MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 24
MINUTES_PER_DAY = HOURS_PER_DAY * MINUTES_PER_HOUR


class TimeOfDay(enum.StrEnum):
    """하루의 어느 때. 서술이 밝기와 분위기를 맞추는 데 쓴다."""

    DAWN = 'dawn'
    MORNING = 'morning'
    DAY = 'day'
    EVENING = 'evening'
    NIGHT = 'night'


# 때가 시작하는 시. 앞에서부터 본다. 4시 전은 밤이다(전날 21시부터 이어진다)
TIMES_OF_DAY = (
    (21, TimeOfDay.NIGHT),
    (17, TimeOfDay.EVENING),
    (11, TimeOfDay.DAY),
    (7, TimeOfDay.MORNING),
    (4, TimeOfDay.DAWN),
)


@dataclass(frozen=True)
class ClockTime:
    """시각을 사람이 읽는 모양으로 푼 것. day 는 1 부터, hour 는 0~23, minute 는 0~59."""

    day: int
    hour: int
    minute: int
    time_of_day: TimeOfDay


def start_minutes(start_day: int, start_hour: int) -> int:
    """판의 시작 시각(며칠째, 몇 시)을 1일째 0시부터 흐른 분으로 바꾼다."""
    return ((start_day - 1) * HOURS_PER_DAY + start_hour) * MINUTES_PER_HOUR


def time_of_day(hour: int) -> TimeOfDay:
    """몇 시가 하루의 어느 때인가."""
    for starts_at, part in TIMES_OF_DAY:
        if hour >= starts_at:
            return part
    return TimeOfDay.NIGHT


def read_time(minutes: int) -> ClockTime:
    """1일째 0시부터 흐른 분을 며칠째, 몇 시, 몇 분, 하루의 어느 때로 푼다."""
    days, in_day = divmod(minutes, MINUTES_PER_DAY)
    hour, minute = divmod(in_day, MINUTES_PER_HOUR)
    return ClockTime(day=days + 1, hour=hour, minute=minute, time_of_day=time_of_day(hour))


def as_document(minutes: int) -> dict:
    """1일째 0시부터 흐른 분을 이벤트와 응답에 적을 모양으로. 며칠째, 몇 시, 몇 분, 하루의 어느 때."""
    time = read_time(minutes)
    return {'day': time.day, 'hour': time.hour, 'minute': time.minute, 'time_of_day': time.time_of_day}
