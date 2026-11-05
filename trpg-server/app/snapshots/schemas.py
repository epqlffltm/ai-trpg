# trpg-server/app/snapshots/schemas.py

"""
장면 그림 API 의 응답의 모양(#983). 그림의 바이트는 이 서버가 대신 내준다
(GET /api/v1/game/tables/{table_id}/snapshots/{id}/image, 테이블에 앉은 사람만).
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
    """
    테이블의 장면 그림 한 장. round_number 는 그린 라운드다. by_me 면 내가 그렸다(내가 냈다).
    실패했으면 code 에 까닭이 있다(refused, credit_short …). 다 그렸으면(ready) 그림의 주소로 받는다.
    """

    id: uuid.UUID
    round_number: int
    status: SnapshotStatus
    by_me: bool
    code: str | None
    created_at: datetime


class SnapshotPriceOut(BaseModel):
    """
    장면 그림 한 장의 값. available 이 거짓이면 지금은 그릴 수 없다(단추를 숨긴다).
    credits 는 결제 서버가 정한 값(글자, "160")이다. 결제 서버 없이 도는 서버면 credits 와 tier 가 null 이다.
    tier 가 premium 이면 골드(유료 크레딧)로만 낸다. promo 면 행사가다. chat·story 서버와 같은 모양이다.
    """

    available: bool
    credits: str | None = None
    tier: Tier | None = None
    promo: bool = False


class KeptSnapshotOut(BaseModel):
    """
    내가 다 그린 테이블의 장면 그림 한 장(갤러리). table_title 은 그 테이블의 제목이다.
    테이블을 지웠으면 table_id 와 table_title 이 null 이다. 그림은 asset 서버의 주소로 받는다(그린 사람만).
    """

    id: uuid.UUID
    image_id: uuid.UUID
    table_id: uuid.UUID | None
    table_title: str | None
    round_number: int
    created_at: datetime


class KeptSnapshotPage(BaseModel):
    """목록의 한 쪽과 전체 개수."""

    items: list[KeptSnapshotOut]
    total: int
