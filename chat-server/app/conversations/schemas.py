# chat-server/app/conversations/schemas.py

"""
대화 API 가 받는 입력과 내보내는 응답의 모양.
"""

import uuid
from datetime import date, datetime
from typing import Annotated

from ai_core.catalog_contract import Grade
from pydantic import BaseModel, ConfigDict, Field

from app.assets.schemas import CharacterDocument
from app.ratings import Rating

# 고를 수 있는 시작 상황의 번호의 상한. asset 서버가 캐릭터마다 다섯까지 둔다. 넉넉히 받고 판에 없으면 422 다
START_INDEX_MAX = 20
# 캐릭터의 말을 고친 글의 길이의 상한(글자). 이어 쓴 답은 길어질 수 있어 사람의 말(4000)보다 넉넉하다
EDIT_MAX_CHARS = 20000

# 모델의 이름표. 표의 칸(String(48))보다 길면 들어올 수 없다
ModelSlug = Annotated[str, Field(min_length=1, max_length=48)]


class ConversationCreate(BaseModel):
    """
    대화를 시작할 때 받는 값. 캐릭터와 시작 상황만 고르고 들어간다(2026-10-20). 페르소나와 모델은 지난번 것을 쓴다.

    persona_id 는 셋 중 하나다.
      - 보내지 않으면: 지난번 대화의 페르소나를 쓴다. 지난번에 없었거나 그 페르소나가 지워졌으면 페르소나 없이 시작한다
      - null 을 보내면: 페르소나 없이 시작한다
      - id 를 보내면: 그 페르소나다. 없거나 남의 것이면 404 다

    model 도 셋 중 하나다.
      - 보내지 않으면: 지난번 대화의 모델을 쓴다. 지난번에 없었거나 이 대화에 고를 수 없으면 모델 없이 시작한다
      - null 을 보내면: 모델 없이 시작한다. 말을 보내기 전에 고른다
      - 이름표를 보내면: 그 모델이다. 이 대화에 고를 수 없으면 422 model_unavailable 이다
    """

    # 모르는 칸이 오면 거부한다. owner_id 를 끼워 보내도 조용히 무시되지 않고 오류가 난다
    model_config = ConfigDict(extra='forbid')

    # asset 서버의 캐릭터 id. 마지막 판을 가져온다
    character_id: uuid.UUID
    # 판의 시작 상황 가운데 몇 번째인가(0 부터)
    start: Annotated[int, Field(ge=0, le=START_INDEX_MAX)] = 0
    persona_id: uuid.UUID | None = None
    # 모델 목록의 이름표(GET /api/v1/chat/models)
    model: ModelSlug | None = None

    def persona_chosen(self) -> bool:
        """persona_id 를 보냈는가(null 을 보낸 것도 고른 것이다)."""
        return 'persona_id' in self.model_fields_set

    def model_chosen(self) -> bool:
        """model 을 보냈는가(null 을 보낸 것도 고른 것이다)."""
        return 'model' in self.model_fields_set


class ModelChoice(BaseModel):
    """대화의 모델을 바꿀 때 받는 값."""

    model_config = ConfigDict(extra='forbid')

    model: ModelSlug


class ConversationModelOut(BaseModel):
    """
    대화에 싣는 모델. usable 이 거짓이면 이 대화에 더는 고를 수 없는 모델이다
    (꺼졌다, 은퇴했다, 성인 등급의 대화에 쓸 수 없게 됐다).

    화면이 "모델을 다시 골라 주세요"를 보인다. 서버는 몰래 다른 모델로 바꾸지 않는다.
    """

    slug: str
    display_name: str
    vendor: str
    grade: Grade
    retires_on: date | None
    usable: bool


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
    # 다음 답 추천의 선택지(0~3개). 캐릭터의 답에만 있다. 누르면 입력칸을 채운다. 보내는 것은 사람이다
    suggestions: list[str] = []
    # 사람이 고친 캐릭터의 말이다(상대의 말 고치기)
    edited: bool = False


class MessageEdit(BaseModel):
    """캐릭터의 말을 고친 글."""

    model_config = ConfigDict(extra='forbid')

    content: Annotated[str, Field(min_length=1, max_length=EDIT_MAX_CHARS, pattern=r'\S')]


class PathMessageOut(MessageOut):
    """
    지금 가지의 말 하나와 그 대안들. alternatives 는 같은 부모 아래의 말들의 id 다(먼저 생긴 것부터, 이 말도 든다).

    화면이 "< 2/3 >" 를 그리고, 다른 대안을 고르면 PUT /conversations/{id}/branch 로 그 가지를 본다.
    """

    alternatives: list[uuid.UUID]


class BranchChoice(BaseModel):
    """볼 가지. 대안 가운데 하나의 id 다. 그 말 아래에서 가장 나중에 생긴 말이 가지의 끝이 된다."""

    model_config = ConfigDict(extra='forbid')

    message_id: uuid.UUID


class ConversationSummary(BaseModel):
    """목록의 한 줄."""

    id: uuid.UUID
    title: str
    character: CharacterSummary
    model: ConversationModelOut | None
    created_at: datetime
    updated_at: datetime


class ConversationPage(BaseModel):
    """목록의 한 쪽과 전체 개수. 게임 서버의 GET /tables 와 같은 모양이다(#593)."""

    items: list[ConversationSummary]
    total: int


class ConversationDetail(BaseModel):
    """
    대화 하나. messages 는 지금 보고 있는 가지의 말들이다. 첫 말부터 차례로. 말마다 그 대안들의 id 가 실린다.

    generating 이 참이면 답을 쓰는 중이다. 화면이 보내기를 막고, 끝난 뒤 다시 읽는다.
    """

    id: uuid.UUID
    title: str
    start: StartOut
    character: CharacterOut
    persona: PersonaOut | None
    model: ConversationModelOut | None
    messages: list[PathMessageOut]
    generating: bool
    created_at: datetime
    updated_at: datetime
