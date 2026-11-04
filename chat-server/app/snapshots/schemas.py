# chat-server/app/snapshots/schemas.py

"""
장면 그림 API 의 응답의 모양(#983). 그림은 asset 서버의 주소(GET /api/v1/asset/images/{image_id})로 받는다(주인만).
"""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from app.billing.prices import Tier


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


class SnapshotPriceOut(BaseModel):
    """
    장면 그림 한 장의 값. available 이 거짓이면 지금은 그릴 수 없다(단추를 숨긴다).
    credits 는 결제 서버가 정한 값(글자, "160")이다. 결제 서버 없이 도는 서버면 credits 와 tier 가 null 이다.
    tier 가 premium 이면 골드(유료 크레딧)로만 낸다. promo 면 행사가다.
    """

    available: bool
    credits: str | None = None
    tier: Tier | None = None
    promo: bool = False
