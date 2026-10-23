# chat-server/app/world/clock.py

"""
대화 안의 시각을 셈한다. DB 를 모르는 순수 함수다(#668).

시각은 하나의 정수다. 1일째 0시 0분부터 흐른 분이다. 대화의 시각은 시작 시각(시작 상황의 hour)에
흐른 시간(상태의 minutes)을 더한 것이다(clock_minutes). 며칠째, 몇 시, 몇 분, 시간대는 그 수에서 계산한다.
시간대의 경계는 TRPG 와 같다(trpg-server 의 app/calendar/clock.py, 2026-10-22 유저 결정).
TRPG 와 함께 쓸 때 shared/ 로 뽑는다(chat 의 만드는 순서 5 와 같다).
"""

import enum
from dataclasses import dataclass

MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 24
MINUTES_PER_DAY = HOURS_PER_DAY * MINUTES_PER_HOUR


class TimeOfDay(enum.StrEnum):
    """하루의 어느 때. 배경을 고르고, 모델이 밝기와 분위기를 맞춘다. asset 서버의 TimeOfDay 와 같은 이름이다."""

    DAWN = 'dawn'
    MORNING = 'morning'
    DAY = 'day'
    EVENING = 'evening'
    NIGHT = 'night'


# 때가 시작하는 시. 이른 것부터다. 4시 전은 밤이다(전날 21시부터 이어진다)
TIMES_OF_DAY = (
    (4, TimeOfDay.DAWN),
    (7, TimeOfDay.MORNING),
    (11, TimeOfDay.DAY),
    (17, TimeOfDay.EVENING),
    (21, TimeOfDay.NIGHT),
)

# 사람과 모델에게 보이는 시간대의 이름
TIME_OF_DAY_WORDS = {
    TimeOfDay.DAWN: '새벽',
    TimeOfDay.MORNING: '아침',
    TimeOfDay.DAY: '낮',
    TimeOfDay.EVENING: '저녁',
    TimeOfDay.NIGHT: '밤',
}


@dataclass(frozen=True)
class ClockTime:
    """시각을 사람이 읽는 모양으로 푼 것. day 는 1 부터, hour 는 0~23, minute 는 0~59."""

    day: int
    hour: int
    minute: int
    time_of_day: TimeOfDay


def clock_minutes(start_hour: int, elapsed: int) -> int:
    """시작 시각(1일째 start_hour 시)에서 elapsed 분이 흐른 시각. 1일째 0시부터 흐른 분이다."""
    return start_hour * MINUTES_PER_HOUR + elapsed


def time_of_day(hour: int) -> TimeOfDay:
    """몇 시가 하루의 어느 때인가."""
    found = TimeOfDay.NIGHT
    for starts_at, part in TIMES_OF_DAY:
        if hour >= starts_at:
            found = part
    return found


def read_time(minutes: int) -> ClockTime:
    """1일째 0시부터 흐른 분을 며칠째, 몇 시, 몇 분, 시간대로 푼다."""
    days, in_day = divmod(minutes, MINUTES_PER_DAY)
    hour, minute = divmod(in_day, MINUTES_PER_HOUR)
    return ClockTime(day=days + 1, hour=hour, minute=minute, time_of_day=time_of_day(hour))


def until_next_time_of_day(minutes: int) -> int:
    """다음 시간대가 시작할 때까지 남은 분. 밤이면 다음 새벽(4시)까지다. 늘 1 이상이다."""
    in_day = minutes % MINUTES_PER_DAY
    for starts_at, _ in TIMES_OF_DAY:
        start = starts_at * MINUTES_PER_HOUR
        if start > in_day:
            return start - in_day
    first = TIMES_OF_DAY[0][0] * MINUTES_PER_HOUR
    return MINUTES_PER_DAY - in_day + first


def time_words(time: ClockTime) -> str:
    """'2일째 저녁 18:30'."""
    return f'{time.day}일째 {TIME_OF_DAY_WORDS[time.time_of_day]} {time.hour:02d}:{time.minute:02d}'
