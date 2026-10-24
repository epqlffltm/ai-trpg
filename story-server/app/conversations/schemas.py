# story-server/app/conversations/schemas.py

"""
세션 API 가 받는 입력과 내보내는 응답의 모양.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.ratings import Rating


class ConversationCreate(BaseModel):
    """세션을 시작할 때 받는 값. 세계관만 고른다. 그 세계관의 마지막 판을 가져와 고정한다."""

    # 모르는 칸이 오면 거부한다. owner_id 를 끼워 보내도 조용히 무시되지 않고 오류가 난다
    model_config = ConfigDict(extra='forbid')

    # asset 서버의 세계관 id
    world_id: uuid.UUID


class WorldSummary(BaseModel):
    """목록에 싣는 세계관. id 는 asset 서버의 세계관 id 이고 version 은 이 세션이 쓰는 판의 번호다."""

    id: uuid.UUID
    version: int
    name: str
    image_id: uuid.UUID | None
    rating: Rating


class WorldOut(WorldSummary):
    """
    세션 하나에 싣는 세계관. 가져온 판의 문서까지다(받은 칸 전부).

    문서의 칸은 asset 서버의 판의 형식을 따른다(asset-server/README.md 의 "세계관").
    """

    document: dict


class ConversationSummary(BaseModel):
    """목록의 한 줄."""

    id: uuid.UUID
    title: str
    world: WorldSummary
    created_at: datetime
    updated_at: datetime


class ConversationPage(BaseModel):
    """목록의 한 쪽과 전체 개수. chat 의 GET /conversations 와 같은 모양이다(#593)."""

    items: list[ConversationSummary]
    total: int


class ConversationDetail(BaseModel):
    """세션 하나. 말과 상태는 그것을 쓰는 조각에서 더한다(만드는 순서 2~5)."""

    id: uuid.UUID
    title: str
    world: WorldOut
    created_at: datetime
    updated_at: datetime
