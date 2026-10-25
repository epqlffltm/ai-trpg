# story-server/app/conversations/schemas.py

"""
세션 API 가 받는 입력과 내보내는 응답의 모양.
"""

import uuid
from datetime import date, datetime
from typing import Annotated

from ai_core.catalog_contract import Grade
from pydantic import BaseModel, ConfigDict, Field

from app.ratings import Rating

# 모델의 이름표. 표의 칸(String(48))보다 길면 들어올 수 없다
ModelSlug = Annotated[str, Field(min_length=1, max_length=48)]


class ConversationCreate(BaseModel):
    """
    세션을 시작할 때 받는 값. 세계관을 고른다. 그 세계관의 마지막 판을 가져와 고정한다.

    model 은 셋 중 하나다(chat 과 같다).
      - 보내지 않으면: 지난번 세션의 모델을 쓴다. 지난번에 없었거나 이 세션에 고를 수 없으면 모델 없이 시작한다
      - null 을 보내면: 모델 없이 시작한다. 말을 보내기 전에 고른다
      - 이름표를 보내면: 그 모델이다. 이 세션에 고를 수 없으면 422 model_unavailable 이다
    """

    # 모르는 칸이 오면 거부한다. owner_id 를 끼워 보내도 조용히 무시되지 않고 오류가 난다
    model_config = ConfigDict(extra='forbid')

    # asset 서버의 세계관 id
    world_id: uuid.UUID
    # 모델 목록의 이름표(GET /api/v1/story/models)
    model: ModelSlug | None = None

    def model_chosen(self) -> bool:
        """model 을 보냈는가(null 을 보낸 것도 고른 것이다)."""
        return 'model' in self.model_fields_set


class ModelChoice(BaseModel):
    """세션의 모델을 바꿀 때 받는 값."""

    model_config = ConfigDict(extra='forbid')

    model: ModelSlug


class ConversationModelOut(BaseModel):
    """
    세션에 싣는 모델. usable 이 거짓이면 이 세션에 더는 고를 수 없는 모델이다
    (꺼졌다, 은퇴했다, 성인 등급의 세션에 쓸 수 없게 됐다). 화면이 다시 고르게 한다. 서버는 몰래 바꾸지 않는다.
    """

    slug: str
    display_name: str
    vendor: str
    grade: Grade
    retires_on: date | None
    usable: bool


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
    model: ConversationModelOut | None
    created_at: datetime
    updated_at: datetime


class ConversationPage(BaseModel):
    """목록의 한 쪽과 전체 개수. chat 의 GET /conversations 와 같은 모양이다(#593)."""

    items: list[ConversationSummary]
    total: int


class SegmentOut(BaseModel):
    """말 조각 하나. speaker 는 장면의 인물의 id(판의 cast 의 id)이고, 서술이면 null 이다."""

    speaker: str | None
    text: str


class MessageOut(BaseModel):
    """
    말 하나. role 은 user(사람의 말), assistant(모델의 답), action(사람의 행동)이다.
    모델의 답은 segments(말 조각)를 그린다. content 는 그 조각을 표식이 붙은 줄로 쓴 것이다.
    cast 는 그 답을 쓸 때의 장면의 인물이다. status 가 partial 이면 끊긴 답이다.
    """

    id: uuid.UUID
    parent_id: uuid.UUID | None
    role: str
    content: str
    status: str
    segments: list[SegmentOut]
    cast: list[str]
    created_at: datetime


class ConversationDetail(BaseModel):
    """세션 하나. messages 는 지금 보고 있는 가지의 말들이다(첫 말부터). 상태는 행동을 더하는 조각에서 싣는다."""

    id: uuid.UUID
    title: str
    world: WorldOut
    model: ConversationModelOut | None
    messages: list[MessageOut]
    created_at: datetime
    updated_at: datetime
