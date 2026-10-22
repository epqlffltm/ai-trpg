# trpg-server/app/calendar/schemas.py

"""
테이블의 시계 API 가 받고 내보내는 모양.
"""

from pydantic import BaseModel

from app.calendar.clock import TimeOfDay


class ClockTimeOut(BaseModel):
    """게임 안의 한 시각. 며칠째(1 부터), 몇 시, 몇 분, 하루의 어느 때."""

    day: int
    hour: int
    minute: int
    time_of_day: TimeOfDay


class ClockOut(ClockTimeOut):
    """
    테이블의 지금 시각과 다음 라운드에 흐를 시간.

    next_step_minutes 는 실제로 흐를 시간이다. step_changed 가 참이면 엔진이 판의 기본보다 늘렸다
    (이번 라운드에 길을 갔거나 쉬었거나 모두 기다렸다). 라운드가 닫힌 뒤 다음 라운드가 열릴 때까지만 참일 수 있다.
    """

    next_step_minutes: int
    default_step_minutes: int
    step_changed: bool
