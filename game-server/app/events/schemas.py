# game-server/app/events/schemas.py

"""
이벤트 API 가 내보내는 응답의 모양. 받는 입력은 없다. 이벤트는 읽기만 한다.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.events.models import EventType


class EventOut(BaseModel):
    """앉은 사람이 이벤트 하나를 볼 때의 값."""

    # 테이블 안에서의 순서. 다음에 읽을 때 "이 번호 뒤"를 달라고 한다
    sequence: int
    type: EventType
    # 이 일을 한 사람. 사람이 한 일이 아니면 None 이다
    actor_id: uuid.UUID | None
    # 종류마다 다른 내용. 내보내기로 정한 칸만 들어 있다(app/events/router.py 의 VISIBLE)
    payload: dict
    # 이 이벤트를 일으킨 이벤트의 번호
    caused_by_sequence: int | None
    # 요청 하나가 낳은 이벤트들의 묶음
    action_group_id: uuid.UUID
    created_at: datetime


class EventPage(BaseModel):
    """이벤트 목록의 한 쪽."""

    items: list[EventOut]
    # 이 테이블에 적힌 마지막 이벤트의 번호. items 의 마지막 번호가 이보다 작으면 더 읽을 것이 있다
    last_sequence: int = Field(ge=0)
