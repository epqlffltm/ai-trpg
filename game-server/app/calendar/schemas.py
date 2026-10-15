# game-server/app/calendar/schemas.py

"""
테이블의 시계 API 가 받고 내보내는 모양.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.assets.models import ROUND_MAX_MINUTES
from app.calendar.clock import TimeOfDay


class StepChange(BaseModel):
    """
    방장이 다음 라운드가 열릴 때 흐를 시간을 정할 때 받는 값.

    minutes 는 꼭 보낸다. null 이면 판의 기본으로 되돌린다. 빈 본문이 몰래 되돌리지 않게 한다.
    0 이면 다음 라운드는 같은 때에 열린다(한 장면을 이어 간다). 한 번에 일주일까지 흘린다(판의 기본과 같은 한도).
    """

    model_config = ConfigDict(extra='forbid')

    minutes: Annotated[int, Field(ge=0, le=ROUND_MAX_MINUTES)] | None


class ClockTimeOut(BaseModel):
    """게임 안의 한 시각. 며칠째(1 부터), 몇 시, 몇 분, 하루의 어느 때."""

    day: int
    hour: int
    minute: int
    time_of_day: TimeOfDay


class ClockOut(ClockTimeOut):
    """
    테이블의 지금 시각과 다음 라운드에 흐를 시간.

    next_step_minutes 는 실제로 흐를 시간이다(방장이 정한 값, 없으면 판의 기본). step_changed 가 참이면 방장이 정했다.
    """

    next_step_minutes: int
    default_step_minutes: int
    step_changed: bool
