# story-server/app/records/schemas.py

"""
계정의 기록 API 가 내보내는 모양.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.records.illustrations import SceneKind


class EndingRecordOut(BaseModel):
    """본 엔딩 하나. ending_id 는 판의 엔딩의 id 다. 이름과 힌트는 판의 문서에 있다."""

    ending_id: str
    first_seen_at: datetime
    # 처음 본 세션. 그 세션이 지워졌으면 null 이다
    conversation_id: uuid.UUID | None


class EndingRecordList(BaseModel):
    """한 세계관에서 본 엔딩들. 처음 본 차례다."""

    items: list[EndingRecordOut]


class IllustrationOut(BaseModel):
    """
    연 일러스트 하나. 장면은 종류(event, ending)와 판의 id 다. image_id 는 연 때의 그림이다.
    cast 는 그 장면이 부르는 인물들이다. 갤러리는 인물마다 묶고, 비었으면 세계관 칸에 둔다.
    """

    kind: SceneKind
    scene_id: str
    image_id: uuid.UUID
    cast: list[str]
    first_seen_at: datetime
    # 처음 연 세션. 그 세션이 지워졌으면 null 이다
    conversation_id: uuid.UUID | None


class IllustrationList(BaseModel):
    """한 세계관에서 연 일러스트들. 처음 연 차례다."""

    items: list[IllustrationOut]
