# chat-server/app/assets/schemas.py

"""
asset 서버가 내주는 것의 모양(asset-server 의 app/characters/schemas.py 의 CharacterCopy, app/personas/schemas.py 의
PersonaCopy). 받은 것을 이 모양으로 검사한 뒤에만 쓴다. 모양이 틀리면 asset 서버를 쓸 수 없는 것으로 본다.

모르는 칸은 버린다. asset 서버가 칸을 더해도 chat 이 멈추지 않는다. 그래서 판의 사본에 남기려는 칸은 여기에 적어야 한다.
판의 형식(format)은 받은 그대로 적어 둔다. 칸이 바뀌면 asset 서버가 번호를 올리고, 이쪽은 번호로 읽는 법을 고른다.
  - 1: 처음의 칸
  - 2: 지도(장소, 길, 처음 있는 장소)와 물건(물건, 시작 소지품). 형식 1 의 판에서는 비어 있다.
       쓰는 것(현재 장소, 이동, 소지품)은 chat 의 만드는 순서 5(장소와 소지품)다
  - 3: 호감도(보이는 방식, 시작 값, 단계, 오르내리는 규칙). 형식 1, 2 의 판에서는 없다(null)
  - 4: 시작 상황의 시작 시각(hour)과 장소의 시간대 배경(backgrounds). 3 까지의 판은 정오에 시작하고 시간대 배경이 없다
  - 5: 이벤트 씬(그림, 해금 대상인지, 장면의 설명, 나오는 조건, #669). 4 까지의 판은 이벤트 씬이 없다.
       그때 이름은 illustrations(장면의 설명은 scene)였다. 판의 사본에도 그 이름으로 남아 있을 수 있어 바꿔 읽는다
  - 6: 이벤트 씬의 이름(event_scenes, description)과 캐릭터 그림(sprites, 표정과 차림마다).
       5 까지의 판은 캐릭터 그림이 없다
  - 7: 물건의 giftable(상대가 줄 수 있다)과 호감도의 model_step(모델이 답 하나에 바꿀 수 있는 크기, #676).
       6 까지의 판은 줄 수 있는 물건이 없고 model_step 이 AFFECTION_MODEL_STEP_DEFAULT 다
  - 8: 로어북(lorebooks, 캐릭터가 가리킨 로어북의 게시할 때의 마지막 판, #672). 7 까지의 판은 로어북이 없다
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.ratings import Rating

# 시작 시각을 적지 않은 시작 상황(형식 3 까지의 판)은 정오에 시작한다(asset 서버의 START_HOUR_DEFAULT 와 같다)
START_HOUR_DEFAULT = 12
# model_step 을 적지 않은 호감도(형식 6 까지의 판)의 크기(asset 서버의 AFFECTION_MODEL_STEP_DEFAULT 와 같다)
AFFECTION_MODEL_STEP_DEFAULT = 3


class StartDocument(BaseModel):
    """시작 상황 하나. 제목은 목록에, 상황은 모델에 간다. hour 는 시작하는 시각(몇 시, 0~23)이다."""

    model_config = ConfigDict(extra='ignore')

    title: str
    situation: str
    hour: int = START_HOUR_DEFAULT


class PlaceDocument(BaseModel):
    """
    장소 하나. id 는 캐릭터 안에서 고유하다. 그림(image_id)은 그 장소의 기본 배경이다.
    backgrounds 는 시간대(dawn, morning, day, evening, night)마다의 배경이다.
    모르는 시간대도 받아 둔다(쓰이지 않을 뿐이다).
    """

    model_config = ConfigDict(extra='ignore')

    id: str
    name: str
    description: str
    image_id: uuid.UUID | None
    backgrounds: dict[str, uuid.UUID] = {}


class PathDocument(BaseModel):
    """두 장소(a, b) 사이의 길. 양쪽으로 다닌다. minutes 는 걸리는 시간(분)이다."""

    model_config = ConfigDict(extra='ignore')

    a: str
    b: str
    minutes: int


class ItemDocument(BaseModel):
    """
    물건 하나. kind 는 thing 이나 clothing(건네면 상대의 차림에 들어간다)이다. 모르는 종류도 받아 둔다.
    consumable 이면 쓰면 하나 없어진다. giftable 이면 상대가 사용자에게 줄 수 있다(모델이 제안한다, #676).
    """

    model_config = ConfigDict(extra='ignore')

    id: str
    name: str
    description: str
    kind: str
    consumable: bool = False
    giftable: bool = False
    image_id: uuid.UUID | None


class StartItemDocument(BaseModel):
    """사용자가 처음에 가진 물건(item 은 물건의 id)과 그 수."""

    model_config = ConfigDict(extra='ignore')

    item: str
    count: int


class StageDocument(BaseModel):
    """호감도의 단계 하나. at 이상이면 이 단계다."""

    model_config = ConfigDict(extra='ignore')

    name: str
    at: int


class TriggerDocument(BaseModel):
    """
    호감도를 바꾸는 행동. kind 는 give_item, reach_place, use_item 이다.
    모르는 종류도 받아 둔다(맞는 행동이 없을 뿐이다).
    """

    model_config = ConfigDict(extra='ignore')

    kind: str
    target: str


class AffectionRuleDocument(BaseModel):
    """오르내리는 규칙 하나. on 의 행동을 하면 change 만큼. once 면 그 가지에서 처음 한 번만."""

    model_config = ConfigDict(extra='ignore')

    id: str
    on: TriggerDocument
    change: int
    once: bool = False


class AffectionDocument(BaseModel):
    """
    캐릭터의 호감도. display 는 number(숫자와 게이지)나 stage(단계 이름과 게이지, 숫자를 내려보내지 않는다)다.
    model_step 은 모델이 답 하나에 바꿀 수 있는 크기다(0 이면 바꾸지 못한다, #676).
    """

    model_config = ConfigDict(extra='ignore')

    display: str
    start: int
    stages: list[StageDocument]
    rules: list[AffectionRuleDocument] = []
    model_step: int = AFFECTION_MODEL_STEP_DEFAULT


class SceneConditionDocument(BaseModel):
    """
    이벤트 씬이 나오는 조건. kind 는 reach_place(장소의 id), give_item(물건의 id), affection_stage(단계의 이름)다.
    모르는 종류도 받아 둔다(맞는 일이 없을 뿐이다).
    """

    model_config = ConfigDict(extra='ignore')

    kind: str
    target: str


class EventSceneDocument(BaseModel):
    """이벤트 씬 하나. collectible 이면 해금 대상이다. description 은 그 답을 쓸 때 모델이 읽는 장면의 설명이다."""

    model_config = ConfigDict(extra='ignore')

    id: str
    title: str
    image_id: uuid.UUID
    description: str = ''
    collectible: bool = True
    when: SceneConditionDocument


class SpriteDocument(BaseModel):
    """
    캐릭터 그림 하나(배경이 투명한 서 있는 그림). expression 은 표정(빈 글이면 기본),
    outfit 은 이 그림의 차림인 옷(물건의 id, 없으면 처음 차림)이다.
    """

    model_config = ConfigDict(extra='ignore')

    id: str
    image_id: uuid.UUID
    expression: str = ''
    outfit: str | None = None


class LoreEntryDocument(BaseModel):
    """
    로어북의 항목 하나. constant 면 늘 모델에 간다. 아니면 최근 말에 keywords 가운데 하나가 나올 때 간다
    (app/conversation/lorebook.py). kind 는 종류(person, place …)다. 모르는 종류도 받아 둔다.
    """

    model_config = ConfigDict(extra='ignore')

    id: str
    name: str
    kind: str = 'other'
    keywords: list[str] = []
    content: str
    constant: bool = False


class LorebookCopyDocument(BaseModel):
    """캐릭터의 판에 복사된 로어북 하나. id 와 version 은 asset 의 로어북과 그 판의 번호다."""

    model_config = ConfigDict(extra='ignore')

    id: uuid.UUID
    version: int
    name: str
    entries: list[LoreEntryDocument] = []


def legacy_scenes(data: dict) -> dict:
    """형식 5 의 판의 이벤트 씬(illustrations, scene)을 지금의 이름(event_scenes, description)으로 바꾼다."""
    if 'illustrations' not in data or data.get('event_scenes'):
        return data
    renamed = {key: value for key, value in data.items() if key != 'illustrations'}
    renamed['event_scenes'] = [
        {('description' if key == 'scene' else key): value for key, value in scene.items()}
        for scene in data['illustrations']
    ]
    return renamed


class CharacterDocument(BaseModel):
    """판에 굳힌 캐릭터. intro_html 은 asset 서버가 허용 목록으로 거른 소개다."""

    model_config = ConfigDict(extra='ignore')

    format: int
    name: str
    intro_html: str
    greeting: str
    speech_examples: str
    age: str
    gender: str
    tags: list[str]
    starts: list[StartDocument]
    image_id: uuid.UUID | None
    rating: Rating
    places: list[PlaceDocument] = []
    paths: list[PathDocument] = []
    start_place: str | None = None
    items: list[ItemDocument] = []
    start_items: list[StartItemDocument] = []
    affection: AffectionDocument | None = None
    event_scenes: list[EventSceneDocument] = []
    sprites: list[SpriteDocument] = []
    lorebooks: list[LorebookCopyDocument] = []

    @model_validator(mode='before')
    @classmethod
    def read_legacy_scenes(cls, data: object) -> object:
        """형식 5 의 판(과 그것을 복사한 사본)을 읽을 때 이벤트 씬의 옛 이름을 바꾼다."""
        return legacy_scenes(data) if isinstance(data, dict) else data


class CharacterCopy(BaseModel):
    """asset 서버의 마지막 판. id 는 asset 서버의 캐릭터 id 다."""

    model_config = ConfigDict(extra='ignore')

    id: uuid.UUID
    version: int
    rating: Rating
    published_at: datetime
    document: CharacterDocument


class PersonaCopy(BaseModel):
    """asset 서버의 계정 페르소나의 사본. id 는 asset 서버의 페르소나 id 다."""

    model_config = ConfigDict(extra='ignore')

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
