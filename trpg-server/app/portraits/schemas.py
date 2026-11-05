# trpg-server/app/portraits/schemas.py

"""캐릭터 그림 API 의 응답 모양."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PortraitOut(BaseModel):
    """올린 그림 하나. 바이트는 GET /portraits/{id}/image 로 받는다."""

    id: uuid.UUID
    created_at: datetime


class PortraitPage(BaseModel):
    """올린 그림들의 한 쪽. 최근 것부터다."""

    items: list[PortraitOut]
    total: int = Field(ge=0)
