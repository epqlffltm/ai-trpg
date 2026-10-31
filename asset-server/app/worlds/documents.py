# asset-server/app/worlds/documents.py

"""
세계관의 판에 굳히는 문서의 모양(#591). story 서버가 세션을 시작할 때 이 문서를 가져가 복사한다.

판의 형식(format)에 번호를 둔다. 칸이 늘면 번호를 올리고, 받는 쪽은 번호로 읽는 법을 고른다(캐릭터의 판과 같다).
  - 1: 이름, 소개, 태그, 등급, 대표 그림, 시간대, 시작 시간대, 기한, 엔딩 뒤, 지도(장소, 길, 시작 장소),
       물건과 시작 소지품, 인물(복사한 캐릭터, 기본 장소, 일정, 호감도, 보이기), 로어북(2026-10-24)
  - 2: 이벤트(열리는 조건, 되풀이, 장면 지시, 열릴 때의 효과, 선택지)와 조건의 event_seen 을 더했다(2026-10-24).
       1 의 판은 이벤트가 없는 것으로 읽는다
  - 3: 인물의 고백(confession)과 엔딩(endings)을 더했다(2026-10-24). 2 까지의 판은 고백할 수 있는 인물과 엔딩이 없다
  - 4: 장르(genre, app/genres.py 의 값 하나, 반드시 있다)를 더했다(2026-10-31).
       받는 쪽(story)은 장면 화면의 테마를 이 값으로 고른다.
       3 까지의 판에도 장르를 적었다(마이그레이션 genre required 가 초안의 장르를 판의 문서에 넣었다)

인물의 보이기는 판에서는 정해진 값이다. 초안의 덮어쓰기가 비어 있으면 세계관의 기본을 채워 넣는다.
받는 쪽(story)이 기본과 덮어쓰기를 다시 합치지 않아도 된다.
DB 를 모르는 순수한 함수다. 초안(World)과 거른 소개, 복사한 캐릭터와 로어북에서 문서를 만든다.
"""

import uuid
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from app.characters.documents import LorebookCopyDocument, PathDocument, SpriteDocument, StageDocument
from app.characters.models import AffectionDisplay
from app.genres import Genre
from app.ratings import Rating
from app.worlds.models import (
    AfterEnding,
    ConditionKind,
    ConfessionFailure,
    EffectKind,
    EndingTrigger,
    MapPresence,
    Match,
    PanelField,
    Reveal,
    World,
)

# 판의 형식. 칸을 바꾸면 올린다
DOCUMENT_FORMAT = 4


class SlotDocument(BaseModel):
    """시간대 하나. start_hour 부터 다음 시간대가 시작할 때까지다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    id: str
    name: str
    start_hour: int


class WorldPlaceDocument(BaseModel):
    """장소 하나. backgrounds 의 열쇠는 시간대의 id 다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    id: str
    name: str
    description: str
    image_id: uuid.UUID | None
    backgrounds: dict[str, uuid.UUID] = {}


class WorldItemDocument(BaseModel):
    """물건 하나."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    id: str
    name: str
    description: str
    consumable: bool
    image_id: uuid.UUID | None


class StartItemDocument(BaseModel):
    """사용자가 처음에 가진 물건과 그 수."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    item: str
    count: int


class ConditionDocument(BaseModel):
    """조건 하나. 종류마다 쓰는 칸이 다르다(app/worlds/models.py 의 ConditionKind)."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    kind: ConditionKind
    target: str | None
    value: str | None
    count: int


class ConditionsDocument(BaseModel):
    """조건 목록과 맞추는 법. 목록이 비면 늘 맞는다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    match: Match
    items: list[ConditionDocument]


class ScheduleLineDocument(BaseModel):
    """일정의 줄 하나. 위의 줄부터 맞춰 본다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    slot: str
    place: str
    when: ConditionsDocument


class GiftDocument(BaseModel):
    """선물의 규칙 하나."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    id: str
    item: str
    change: int
    once: bool


class CastAffectionDocument(BaseModel):
    """인물의 호감도."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    display: AffectionDisplay
    start: int
    stages: list[StageDocument]
    gifts: list[GiftDocument]


class CastCharacterDocument(BaseModel):
    """
    인물에 복사한 캐릭터. id 와 version 은 캐릭터와 그 판의 번호다(어디서 왔는지 적어 둔다).
    캐릭터의 판 가운데 story 에 쓰는 칸만이다. intro_html 은 캐릭터를 게시할 때 거른 것이다.
    """

    model_config = ConfigDict(extra='forbid', frozen=True)

    id: uuid.UUID
    version: int
    name: str
    intro_html: str
    speech_examples: str
    age: str
    gender: str
    image_id: uuid.UUID | None
    sprites: list[SpriteDocument]


class ConfessionDocument(BaseModel):
    """인물에게 하는 고백. stage 이상이고 when 이 맞으면 성공이다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    stage: str
    when: ConditionsDocument
    on_fail: ConfessionFailure
    fail_drop: int
    cooldown_days: int


class CastDocument(BaseModel):
    """인물 하나. 보이기(reveal, map, panel)는 기본을 채운 정해진 값이다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    id: str
    character: CastCharacterDocument
    home: str | None
    schedule: list[ScheduleLineDocument]
    affection: CastAffectionDocument
    reveal: Reveal
    map: MapPresence
    map_stage: str | None
    panel: list[PanelField]
    confession: ConfessionDocument | None = None


class EffectDocument(BaseModel):
    """효과 하나. amount 는 호감도의 크기나 물건의 수다(쓰지 않는 종류는 null)."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    kind: EffectKind
    target: str
    amount: int | None


class SceneDocument(BaseModel):
    """이벤트의 장면 지시."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    text: str
    cast: list[str]
    image_id: uuid.UUID | None
    collectible: bool


class ChoiceDocument(BaseModel):
    """선택지 하나."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    id: str
    text: str
    effects: list[EffectDocument]


class EventDocument(BaseModel):
    """이벤트 하나. 판의 차례가 여는 차례다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    id: str
    name: str
    when: ConditionsDocument
    repeat: bool
    scene: SceneDocument
    on_open: list[EffectDocument]
    choices: list[ChoiceDocument]


class TriggerDocument(BaseModel):
    """엔딩의 시작. 기한은 target 이 없다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    kind: EndingTrigger
    target: str | None


class EndingDocument(BaseModel):
    """엔딩 하나. 판의 차례가 맞춰 보는 차례다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    id: str
    name: str
    trigger: TriggerDocument
    when: ConditionsDocument
    scene: SceneDocument
    unlock: bool
    hint: str


class WorldDocument(BaseModel):
    """판에 굳힌 세계관. intro_html 은 허용 목록으로 거른 소개다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    format: int
    name: str
    intro_html: str
    tags: list[str]
    rating: Rating
    image_id: uuid.UUID | None
    slots: list[SlotDocument]
    start_slot: str
    deadline_days: int | None
    after_ending: AfterEnding
    places: list[WorldPlaceDocument]
    paths: list[PathDocument]
    start_place: str
    items: list[WorldItemDocument]
    start_items: list[StartItemDocument]
    cast: list[CastDocument]
    lorebooks: list[LorebookCopyDocument]
    events: list[EventDocument] = []
    endings: list[EndingDocument] = []
    genre: Genre


def character_copy(character_id: uuid.UUID, number: int, document: Mapping) -> CastCharacterDocument:
    """캐릭터의 판(굳힌 문서)에서 story 에 쓰는 칸만 골라 인물에 넣을 모양으로."""
    return CastCharacterDocument(
        id=character_id,
        version=number,
        name=document['name'],
        intro_html=document['intro_html'],
        speech_examples=document['speech_examples'],
        age=document['age'],
        gender=document['gender'],
        image_id=document['image_id'],
        sprites=document.get('sprites', []),
    )


def cast_document(member: Mapping, character: CastCharacterDocument, show: Mapping) -> CastDocument:
    """초안의 인물 하나와 복사한 캐릭터를 판의 모양으로. 비어 있는 보이기는 세계관의 기본(show)으로 채운다."""
    return CastDocument(
        id=member['id'],
        character=character,
        home=member.get('home'),
        schedule=member.get('schedule', []),
        affection=member['affection'],
        reveal=member.get('reveal') or show['reveal'],
        map=member.get('map') or show['map'],
        map_stage=member.get('map_stage'),
        panel=member['panel'] if member.get('panel') is not None else show['panel'],
        confession=member.get('confession'),
    )


def build_document(
    world: World,
    cleaned_intro: str,
    characters: Mapping[uuid.UUID, CastCharacterDocument],
    lorebooks: Sequence[LorebookCopyDocument] = (),
) -> WorldDocument:
    """
    초안과 거른 소개, 인물마다 복사한 캐릭터(캐릭터의 id 로 찾는다), 복사할 로어북들로 판의 문서를 만든다.
    게시를 막는 것이 없을 때만 부른다(시작 장소와 시간대가 있고, 인물의 캐릭터가 모두 복사되었다).
    """
    show = effective_show(world.show)
    return WorldDocument(
        format=DOCUMENT_FORMAT,
        name=world.name,
        intro_html=cleaned_intro,
        tags=list(world.tags),
        rating=Rating(world.rating),
        image_id=world.image_id,
        slots=world.slots,
        start_slot=world.start_slot,
        deadline_days=world.deadline_days,
        after_ending=AfterEnding(world.after_ending),
        places=world.places,
        paths=world.paths,
        start_place=world.start_place,
        items=world.items,
        start_items=world.start_items,
        cast=[cast_document(member, characters[uuid.UUID(member['character_id'])], show) for member in world.cast],
        lorebooks=list(lorebooks),
        events=world.events,
        endings=world.endings,
        genre=Genre(world.genre),
    )


def effective_show(show: Mapping) -> dict:
    """보이기의 기본. 초안에 적지 않은 칸은 처음의 값(보임, 보임, 모든 항목)이다."""
    return {
        'reveal': show.get('reveal', Reveal.SHOWN),
        'map': show.get('map', MapPresence.SHOWN),
        'panel': show.get('panel', list(PanelField)),
    }
