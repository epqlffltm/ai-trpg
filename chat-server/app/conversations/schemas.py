# chat-server/app/conversations/schemas.py

"""
대화 API 가 받는 입력과 내보내는 응답의 모양.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.assets.schemas import CharacterDocument
from app.ratings import Rating

# 고를 수 있는 시작 상황의 번호의 상한. asset 서버가 캐릭터마다 다섯까지 둔다. 넉넉히 받고 판에 없으면 422 다
START_INDEX_MAX = 20


class ConversationCreate(BaseModel):
    """
    대화를 시작할 때 받는 값. 캐릭터와 시작 상황만 고르고 들어간다(2026-10-20).

    persona_id 는 셋 중 하나다.
      - 보내지 않으면: 지난번 대화의 페르소나를 쓴다. 지난번에 없었거나 그 페르소나가 지워졌으면 페르소나 없이 시작한다
      - null 을 보내면: 페르소나 없이 시작한다
      - id 를 보내면: 그 페르소나다. 없거나 남의 것이면 404 다
    """

    # 모르는 칸이 오면 거부한다. owner_id 를 끼워 보내도 조용히 무시되지 않고 오류가 난다
    model_config = ConfigDict(extra='forbid')

    # asset 서버의 캐릭터 id. 마지막 판을 가져온다
    character_id: uuid.UUID
    # 판의 시작 상황 가운데 몇 번째인가(0 부터)
    start: Annotated[int, Field(ge=0, le=START_INDEX_MAX)] = 0
    persona_id: uuid.UUID | None = None

    def persona_chosen(self) -> bool:
        """persona_id 를 보냈는가(null 을 보낸 것도 고른 것이다)."""
        return 'persona_id' in self.model_fields_set


class CharacterSummary(BaseModel):
    """목록에 싣는 캐릭터. id 는 asset 서버의 캐릭터 id 다."""

    id: uuid.UUID
    version: int
    name: str
    image_id: uuid.UUID | None
    rating: Rating


class CharacterOut(BaseModel):
    """대화 하나에 싣는 캐릭터. 가져온 판의 문서까지다."""

    id: uuid.UUID
    version: int
    rating: Rating
    document: CharacterDocument


class PersonaOut(BaseModel):
    """대화에 가져온 페르소나의 사본. id 는 asset 서버의 페르소나 id 다."""

    id: uuid.UUID
    revision: int
    name: str
    description: str
    image_id: uuid.UUID | None
    age: str
    gender: str
    form_of_address: str
    speech_examples: str
    personality: str


class StartOut(BaseModel):
    """고른 시작 상황."""

    title: str
    situation: str


class MessageOut(BaseModel):
    """말 하나."""

    id: uuid.UUID
    parent_id: uuid.UUID | None
    role: str
    content: str
    status: str
    created_at: datetime


class ConversationSummary(BaseModel):
    """목록의 한 줄."""

    id: uuid.UUID
    title: str
    character: CharacterSummary
    created_at: datetime
    updated_at: datetime


class ConversationPage(BaseModel):
    """목록의 한 쪽과 전체 개수. 게임 서버의 GET /tables 와 같은 모양이다(#593)."""

    items: list[ConversationSummary]
    total: int


class ConversationDetail(BaseModel):
    """
    대화 하나. messages 는 지금 보고 있는 가지의 말들이다. 첫 말부터 차례로.

    대안(다시 생성, 고친 말)은 그 단계에서 따로 읽는 길을 둔다.
    """

    id: uuid.UUID
    title: str
    start: StartOut
    character: CharacterOut
    persona: PersonaOut | None
    messages: list[MessageOut]
    created_at: datetime
    updated_at: datetime
