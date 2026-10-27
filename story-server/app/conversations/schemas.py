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


class NamedOut(BaseModel):
    """id 와 이름이 있는 것(시간대)."""

    id: str
    name: str


class SlotOut(NamedOut):
    """시간대 하나. start_hour 부터 다음 시간대가 시작할 때까지다."""

    start_hour: int


class PlaceOut(NamedOut):
    """장소 하나. backgrounds 는 시간대의 id 마다의 배경 그림이다."""

    description: str
    image_id: uuid.UUID | None
    backgrounds: dict[str, uuid.UUID]


class PathOut(BaseModel):
    """두 장소를 잇는 길과 걸리는 분."""

    a: str
    b: str
    minutes: int


class ItemOut(NamedOut):
    """물건 하나."""

    description: str
    consumable: bool
    image_id: uuid.UUID | None


class SpriteOut(BaseModel):
    """인물의 그림 하나. expression 은 표정(빈 글이면 기본)이다."""

    id: str
    image_id: uuid.UUID
    expression: str


class StageOut(BaseModel):
    """호감도의 단계 하나. at 이상이면 이 단계다."""

    name: str
    at: int


class CastAffectionOut(BaseModel):
    """
    인물 창의 호감도. display 는 보이는 법(숫자, 단계 …), stages 는 단계들이다.
    cooling_until 은 다시 고백할 수 있는 시각(1일째 0시부터의 분)이고, 대기가 아니면 null 이다.
    gifts 는 이 가지에서 이 인물에게 건넨 물건(물건의 id)이다.
    """

    display: str
    stages: list[StageOut]
    cooling_until: int | None
    gifts: list[str]


class CastOut(BaseModel):
    """
    보이는 인물 하나. reveal 은 지금 보이는 법이다(만나면 shown).
    silhouette 이면 이름, 그림, 인물 창의 칸이 모두 null 이거나 비어 있다. 숨김인 인물은 만나기 전에는 목록에 없다.
    intro_html, age, gender, affection 은 제작자가 인물 창에 고른 항목만 실린다(아니면 null).
    events 는 이 가지에서 이 인물이 나온 이벤트(이벤트의 id)다. 호감도를 보이는 인물만 실린다.
    """

    id: str
    reveal: str
    met: bool
    name: str | None
    image_id: uuid.UUID | None
    sprites: list[SpriteOut]
    confessable: bool
    intro_html: str | None
    age: str | None
    gender: str | None
    affection: CastAffectionOut | None
    events: list[str]


class ChoiceOut(BaseModel):
    """선택지 하나."""

    id: str
    text: str


class EventOut(NamedOut):
    """
    이 가지에서 열린 이벤트 하나. cast 는 장면이 부른 인물, image_id 는 장면의 일러스트다.
    choices 는 고르기를 기다리는 이벤트에만 실린다(아니면 빈 목록). 열리는 조건과 효과는 싣지 않는다.
    """

    cast: list[str]
    image_id: uuid.UUID | None
    choices: list[ChoiceOut]


class EndingOut(BaseModel):
    """
    엔딩의 칸 하나. 본 엔딩(계정의 기록이나 이 가지에서 본 것)만 이름과 일러스트가 실린다(아니면 null).
    hint 는 제작자가 적은 힌트다. unlock 이 거짓이면 계정에 남지 않는 엔딩이다(엔딩 수에 넣지 않는다).
    """

    id: str
    seen: bool
    name: str | None
    image_id: uuid.UUID | None
    hint: str
    unlock: bool


class MapPlaceOut(BaseModel):
    """
    지도의 장소 하나(D3). visited 는 이 가지에서 가 본 곳인가다.
    cast 는 지금 거기 있는 것이 보이는 인물들이다: 가 본 곳이고, 만난 적이 있고, 제작자의 지도 보이기를 통과한 인물.
    함께 다니는 인물은 넣지 않는다(상태의 companions 로 내 자리 옆에 보인다).
    """

    id: str
    visited: bool
    cast: list[str]


class WorldView(BaseModel):
    """
    세션에서 화면이 쓰는 세계관의 칸. 판의 문서에서 지금 보여도 되는 것만 골라 이 가지의 상태에 맞춘다.
    이벤트와 엔딩의 조건, 일정, 호감도의 규칙, 만나지 않은 인물은 싣지 않는다.
    """

    name: str
    intro_html: str
    tags: list[str]
    image_id: uuid.UUID | None
    deadline_days: int | None
    after_ending: str
    slots: list[SlotOut]
    places: list[PlaceOut]
    paths: list[PathOut]
    items: list[ItemOut]
    cast: list[CastOut]
    events: list[EventOut]
    endings: list[EndingOut]
    # 지도의 장소마다 가 본 곳인가와 지금 거기 보이는 인물(판의 장소 차례)
    map: list[MapPlaceOut]


class ProgressOut(BaseModel):
    """
    세션의 지금 가지의 끝까지 온 곳. 목록(D1 의 내 세션)이 날짜와 진행, 끝, 후일담을 그린다.
    day 는 며칠째, slot 은 시간대의 id, deadline_days 는 판의 기한(없으면 null)이다. 남은 날은 deadline_days - day 다.
    ending 은 이 가지에서 본 엔딩의 id 와 이름(못 봤으면 null)이다.
    epilogue 는 엔딩을 봤고 세계관이 후일담을 골라 이야기가 이어지는 것이다(엔딩을 봤는데 거짓이면 끝난 세션이다).
    """

    day: int
    slot: str
    deadline_days: int | None
    ending: str | None
    ending_name: str | None
    epilogue: bool


class ConversationSummary(BaseModel):
    """목록의 한 줄. progress 는 지금 가지의 끝까지 온 곳이다."""

    id: uuid.UUID
    title: str
    world: WorldSummary
    model: ConversationModelOut | None
    progress: ProgressOut
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
    # 행동 말에서 그 행동 뒤에 열린 이벤트와 본 엔딩(판의 id). 없으면 null 이다
    event_id: str | None = None
    ending_id: str | None = None
    # 사람이 답의 글을 고쳤는가
    edited: bool = False
    created_at: datetime


# 고치는 조각 하나의 글. 한 줄이다(조각은 줄 하나다, app/turns/segments.py). 비어 있지 않다
EditedText = Annotated[str, Field(min_length=1, max_length=4000, pattern=r'^[^\r\n]*\S[^\r\n]*$')]
# 한 번에 고치는 조각의 수의 상한. 답 하나의 길이(STORY_OUTPUT_LIMIT)로는 이보다 많은 줄이 나오지 않는다
SEGMENTS_MAX = 200


class MessageEdit(BaseModel):
    """
    답을 고친 글. 조각마다 고친 글을 차례대로 적는다. 조각의 수는 그 답의 것과 같아야 한다.
    말하는 사람은 보내지 않는다. 저장된 그대로다(장면 밖의 인물이 끼어들 길이 없다).
    """

    model_config = ConfigDict(extra='forbid')

    segments: Annotated[list[EditedText], Field(min_length=1, max_length=SEGMENTS_MAX)]


class PathMessageOut(MessageOut):
    """
    지금 가지의 말 하나와 그 대안들. alternatives 는 같은 부모 아래의 말들의 id 다(먼저 생긴 것부터, 이 말도 든다).

    화면이 "< 2/3 >" 를 그리고, 다른 대안을 고르면 PUT /conversations/{id}/branch 로 그 가지를 본다(chat 과 같다).
    """

    alternatives: list[uuid.UUID]


class BranchChoice(BaseModel):
    """볼 가지. 대안 가운데 하나의 id 다. 그 말 아래에서 가장 나중에 생긴 말이 가지의 끝이 된다."""

    model_config = ConfigDict(extra='forbid')

    message_id: uuid.UUID


class StateOut(BaseModel):
    """
    가지의 끝의 상태(엔진의 상태). 화면이 시계, 지도, 소지품, 인물 창, 선택지, 엔딩을 그린다.

    minutes 는 1일째 0시부터 흐른 분이고, day 와 slot(시간대의 id)은 그 수에서 계산한 것이다.
    affection 은 인물마다의 호감도(0~100)다. 인물 창에 호감도를 보이는 인물만 실린다
    (view 의 cast 에 affection 이 있는 인물).
    숫자로 보일지 단계로 보일지는 view 의 affection.display 를 따라 화면이 정한다.
    choosing 은 선택지를 기다리는 이벤트, ending 은 이 가지에서 본 엔딩이다. cast 는 지금 장소의 장면의 인물이다.
    """

    minutes: int
    day: int
    slot: str
    place: str
    items: dict[str, int]
    affection: dict[str, int]
    companions: list[str]
    choosing: str | None
    ending: str | None
    cast: list[str]


class ConversationDetail(BaseModel):
    """
    세션 하나. messages 는 지금 보고 있는 가지의 말들이다(첫 말부터, 말마다 대안들). state 는 그 끝의 상태다.
    """

    id: uuid.UUID
    title: str
    world: WorldSummary
    model: ConversationModelOut | None
    messages: list[PathMessageOut]
    # 지금 가지의 끝의 상태. 말이 없으면 판으로 만든 처음의 상태다
    state: StateOut
    # 화면이 쓰는 세계관의 칸. 이 가지의 상태에 맞춰 보여도 되는 것만이다(app/conversations/views.py)
    view: WorldView
    created_at: datetime
    updated_at: datetime
