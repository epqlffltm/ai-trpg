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
DB 를 모르는 순수한 함수다. 초안(Character)과 거른 소개에서 문서를 만든다.
"""

import uuid

from pydantic import BaseModel, ConfigDict

from app.characters.models import START_HOUR_DEFAULT, AffectionDisplay, Character, ItemKind, TimeOfDay, TriggerKind
from app.ratings import Rating

# 판의 형식. 칸을 바꾸면 올린다
DOCUMENT_FORMAT = 4


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


def build_document(character: Character, cleaned_intro: str) -> CharacterDocument:
    """초안과 거른 소개로 판의 문서를 만든다."""
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
    )
