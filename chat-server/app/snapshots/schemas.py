# chat-server/app/snapshots/schemas.py

"""
장면 그림 API 의 응답의 모양(#983). 그림은 asset 서버의 주소(GET /api/v1/asset/images/{image_id})로 받는다(주인만).
"""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class SnapshotStatus(StrEnum):
    """화면에 보이는 상태. drawing 이면 그리는 중이다(다시 읽는다)."""

    DRAWING = 'drawing'
    READY = 'ready'
    FAILED = 'failed'


class SnapshotOut(BaseModel):
    """장면 그림 한 장. 실패했으면 code 에 까닭이 있다(refused, credit_short …)."""

    id: uuid.UUID
    message_id: uuid.UUID | None
    status: SnapshotStatus
    image_id: uuid.UUID | None
    code: str | None
    created_at: datetime
