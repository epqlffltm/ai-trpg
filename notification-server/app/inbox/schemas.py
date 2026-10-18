# notification-server/app/inbox/schemas.py

"""
알림함 API(사용자가 자기 알림을 읽는 쪽)의 요청과 응답의 모양.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.notifications.models import Notification

# 한 번에 읽는 알림의 수. 기본과 상한
PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 100


class NotificationView(BaseModel):
    """알림함에 보이는 알림 하나. 넣은 서버가 붙인 열쇠(source_key)와 받는 사람은 싣지 않는다(내 것이다)."""

    id: int
    source: str
    kind: str
    payload: dict[str, Any]
    created_at: datetime
    read_at: datetime | None


class NotificationPage(BaseModel):
    """
    알림함의 한 쪽. 최근 것부터다.

    next_before 가 있으면 그 값을 before 로 다시 부르면 다음 쪽이다. 없으면 끝이다.
    """

    items: list[NotificationView]
    next_before: int | None


class UnreadCount(BaseModel):
    """읽지 않은 알림의 수."""

    unread: int


class ReadAllRequest(BaseModel):
    """
    모두 읽음. up_to 번호까지(그 번호 포함) 읽지 않은 알림을 읽음으로 한다.

    화면이 마지막으로 받은 알림의 번호를 보낸다. "지금까지 전부"로 하면, 목록을 받은 뒤에 막 들어와
    화면에 보이지도 않은 알림까지 읽음이 된다.
    """

    model_config = ConfigDict(extra='forbid')

    up_to: int = Field(ge=1)


class ReadAllResult(BaseModel):
    """모두 읽음의 결과. 이번에 읽음이 된 알림의 수다."""

    read: int


def view_of(notification: Notification) -> NotificationView:
    """테이블의 줄을 알림함에 보일 모양으로 바꾼다."""
    return NotificationView(
        id=notification.id,
        source=notification.source,
        kind=notification.kind,
        payload=notification.payload,
        created_at=notification.created_at,
        read_at=notification.read_at,
    )
