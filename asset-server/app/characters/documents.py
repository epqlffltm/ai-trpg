# asset-server/app/characters/documents.py

"""
캐릭터의 판에 굳히는 문서의 모양(#567). chat 이 대화를 시작할 때 이 문서를 가져가 복사한다.

판의 형식(format)에 번호를 둔다. 칸이 늘면 번호를 올리고, 받는 쪽은 번호로 읽는 법을 고른다.
TRPG 의 판 형식과 같은 방식이다.
  - 1: 처음의 칸(이름, 소개, 인사말, 말투, 나이, 성별, 태그, 시작 상황, 대표 그림, 등급)
  - 2: 지도(장소, 길, 처음 있는 장소)와 물건(물건, 시작 소지품)을 더했다(2026-10-22).
       1 의 판은 이 칸들이 비어 있는 것으로 읽는다
  - 3: 호감도(보이는 방식, 시작 값, 단계, 오르내리는 규칙)를 더했다(2026-10-22). 1, 2 의 판은 호감도가 없다(null)
  - 4: 시작 상황의 시작 시각(hour)과 장소의 시간대 배경(backgrounds)을 더했다(2026-10-22, #668).
       3 까지의 판은 정오에 시작하고 시간대 배경이 없는 것으로 읽는다
  - 5: 이벤트 씬(그림, 해금 대상인지, 장면의 설명, 나오는 조건)을 더했다(2026-10-23, #669).
       4 까지의 판은 이벤트 씬이 없다.
       그때는 칸의 이름이 illustrations, 장면의 설명이 scene 이었다. 5 의 판은 그 이름을 바꿔 읽는다(legacy_scenes)
  - 6: 이벤트 씬의 이름을 바로잡고(event_scenes, description), 캐릭터 그림(sprites)을 더했다(2026-10-23).
       5 까지의 판은 캐릭터 그림이 없다
  - 7: 물건의 giftable(상대가 줄 수 있다)과 호감도의 model_step(모델이 답 하나에 바꿀 수 있는 크기)을 더했다
       (2026-10-23, #676).
  - 8: 로어북(lorebooks)을 더했다(2026-10-23, #672). 캐릭터가 가리킨 로어북마다 게시할 때의 마지막 판(id, 판 번호,
       이름, 항목들)을 복사한다. 7 까지의 판은 로어북이 없다
       6 까지의 판은 줄 수 있는 물건이 없고 model_step 이 AFFECTION_MODEL_STEP_DEFAULT 다
DB 를 모르는 순수한 함수다. 초안(Character)과 거른 소개에서 문서를 만든다.
"""

import uuid
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, model_validator

from app.characters.models import (
    AFFECTION_MODEL_STEP_DEFAULT,
    START_HOUR_DEFAULT,
    AffectionDisplay,
    Character,
    ItemKind,
    SceneWhen,
    TimeOfDay,
    TriggerKind,
)
from app.lorebooks.documents import LoreEntryDocument
from app.ratings import Rating

# 판의 형식. 칸을 바꾸면 올린다
DOCUMENT_FORMAT = 8


class StartDocument(BaseModel):
    """시작 상황 하나. hour 는 시작하는 시각(몇 시)이다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    title: str
    situation: str
    hour: int = START_HOUR_DEFAULT


class PlaceDocument(BaseModel):
    """장소 하나. 그림은 그 장소의 기본 배경이고, backgrounds 는 시간대마다의 배경이다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    id: str
    name: str
    description: str
    image_id: uuid.UUID | None
    backgrounds: dict[TimeOfDay, uuid.UUID] = {}


class PathDocument(BaseModel):
    """두 장소(a, b) 사이의 길. 양쪽으로 다닌다. minutes 는 걸리는 시간(분)이다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    a: str
    b: str
    minutes: int


class ItemDocument(BaseModel):
    """물건 하나."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    id: str
    name: str
    description: str
    kind: ItemKind
    consumable: bool = False
    giftable: bool = False
    image_id: uuid.UUID | None


class StartItemDocument(BaseModel):
    """사용자가 처음에 가진 물건(item 은 물건의 id)과 그 수."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    item: str
    count: int


class StageDocument(BaseModel):
    """호감도의 단계 하나. at 이상이면 이 단계다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    name: str
    at: int


class TriggerDocument(BaseModel):
    """호감도를 바꾸는 행동(종류, 대상)."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    kind: TriggerKind
    target: str


class AffectionRuleDocument(BaseModel):
    """오르내리는 규칙 하나. once 면 그 가지에서 처음 한 번만."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    id: str
    on: TriggerDocument
    change: int
    once: bool


class AffectionDocument(BaseModel):
    """캐릭터의 호감도."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    display: AffectionDisplay
    start: int
    stages: list[StageDocument]
    rules: list[AffectionRuleDocument]
    model_step: int = AFFECTION_MODEL_STEP_DEFAULT


class SceneConditionDocument(BaseModel):
    """이벤트 씬이 나오는 조건(종류, 대상)."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    kind: SceneWhen
    target: str


class EventSceneDocument(BaseModel):
    """이벤트 씬 하나. collectible 이면 해금 대상이다. description 은 그 답을 쓸 때 모델이 읽는 장면의 설명이다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    id: str
    title: str
    image_id: uuid.UUID
    description: str
    collectible: bool
    when: SceneConditionDocument


class SpriteDocument(BaseModel):
    """캐릭터 그림 하나. expression 은 표정(빈 글이면 기본), outfit 은 차림인 옷(물건의 id, 없으면 처음 차림)이다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    id: str
    image_id: uuid.UUID
    expression: str
    outfit: str | None


class LorebookCopyDocument(BaseModel):
    """
    캐릭터의 판에 복사한 로어북 하나(#672). id 와 version 은 로어북과 그 판의 번호다(어디서 왔는지 적어 둔다).
    """

    model_config = ConfigDict(extra='forbid', frozen=True)

    id: uuid.UUID
    version: int
    name: str
    entries: list[LoreEntryDocument]


def lorebook_copy(lorebook_id: uuid.UUID, number: int, document: dict) -> LorebookCopyDocument:
    """로어북의 판(굳힌 문서)을 캐릭터의 판에 넣을 모양으로. 로어북의 판 형식은 빼고 이름과 항목만 담는다."""
    return LorebookCopyDocument(id=lorebook_id, version=number, name=document['name'], entries=document['entries'])


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
    """
    판에 굳힌 캐릭터. intro_html 은 허용 목록으로 거른 소개다.
    지도와 물건의 칸은 형식 2 에서 더했다. 형식 1 의 판을 읽을 수 있게 비어 있는 것이 기본이다.
    """

    model_config = ConfigDict(extra='forbid', frozen=True)

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
        """형식 5 의 판을 읽을 때 이벤트 씬의 옛 이름을 바꾼다."""
        return legacy_scenes(data) if isinstance(data, dict) else data


def build_document(
    character: Character, cleaned_intro: str, lorebooks: Sequence[LorebookCopyDocument] = ()
) -> CharacterDocument:
    """초안과 거른 소개, 복사할 로어북들로 판의 문서를 만든다."""
    return CharacterDocument(
        format=DOCUMENT_FORMAT,
        name=character.name,
        intro_html=cleaned_intro,
        greeting=character.greeting,
        speech_examples=character.speech_examples,
        age=character.age,
        gender=character.gender,
        tags=list(character.tags),
        starts=[StartDocument(**start) for start in character.starts],
        image_id=character.image_id,
        rating=Rating(character.rating),
        places=[PlaceDocument(**place) for place in character.places],
        paths=[PathDocument(**path) for path in character.paths],
        start_place=character.start_place,
        items=[ItemDocument(**item) for item in character.items],
        start_items=[StartItemDocument(**start) for start in character.start_items],
        affection=AffectionDocument.model_validate(character.affection) if character.affection else None,
        event_scenes=[EventSceneDocument.model_validate(scene) for scene in character.event_scenes],
        sprites=[SpriteDocument.model_validate(sprite) for sprite in character.sprites],
        lorebooks=list(lorebooks),
    )
