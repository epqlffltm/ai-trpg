# asset-server/app/worlds/schemas.py

"""
세계관 API 가 받는 입력과 내보내는 응답의 모양(#591).

길이와 개수는 모델의 상수를 쓴다. 캐릭터와 같은 칸(이름, 소개, 태그, 길, 시작 소지품, 호감도의 단계)은
캐릭터의 모양(app/characters/schemas.py)을 그대로 쓴다. 한 칸 안에서 맞는지(시간대의 시각이 차례로 커지는지,
조건의 종류마다 쓰는 칸)는 여기서 보고, 칸끼리 가리키는 것이 맞는지는 게시할 때 본다(app/worlds/publishing.py).
"""

import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.characters.models import (
    AFFECTION_MAX,
    AFFECTION_MAX_CHANGE,
    AFFECTION_MAX_STAGES,
    ITEM_DESCRIPTION_MAX_LENGTH,
    ITEM_NAME_MAX_LENGTH,
    PLACE_DESCRIPTION_MAX_LENGTH,
    PLACE_NAME_MAX_LENGTH,
    AffectionDisplay,
    Visibility,
)
from app.characters.schemas import (
    Intro,
    Key,
    Name,
    Path,
    RemovedItem,
    Stage,
    StartItem,
    Tags,
    reject_repeated,
    reject_repeated_keys,
    stages_from_zero,
    unique_paths,
    unique_start_items,
)
from app.genres import Genre
from app.ratings import Rating
from app.worlds.documents import WorldDocument
from app.worlds.models import (
    CAST_MAX_GIFTS,
    CAST_MAX_SCHEDULE,
    CHOICE_TEXT_MAX_LENGTH,
    CONDITION_MAX_COUNT,
    CONFESSION_COOLDOWN_DEFAULT_DAYS,
    CONFESSION_FAIL_DROP_DEFAULT,
    CONFESSION_MAX_COOLDOWN_DAYS,
    DEADLINE_MAX_DAYS,
    EFFECT_MAX_CHANGE,
    EFFECT_MAX_COUNT,
    ENDING_HINT_MAX_LENGTH,
    ENDING_NAME_MAX_LENGTH,
    EVENT_MAX_CHOICES,
    EVENT_NAME_MAX_LENGTH,
    HOURS_PER_DAY,
    MAX_CONDITIONS,
    MAX_EFFECTS,
    SCENE_MAX_CAST,
    SCENE_TEXT_MAX_LENGTH,
    SLOT_NAME_MAX_LENGTH,
    VERSION_NOTE_MAX_LENGTH,
    WORLD_MAX_CAST,
    WORLD_MAX_ENDINGS,
    WORLD_MAX_EVENTS,
    WORLD_MAX_ITEMS,
    WORLD_MAX_LOREBOOKS,
    WORLD_MAX_PATHS,
    WORLD_MAX_PLACES,
    WORLD_MAX_SLOTS,
    WORLD_MAX_START_ITEMS,
    WORLD_MIN_SLOTS,
    AfterEnding,
    ConditionKind,
    ConfessionFailure,
    EffectKind,
    EndingTrigger,
    MapPresence,
    Match,
    PanelField,
    Reveal,
)


class Slot(BaseModel):
    """
    시간대 하나. start_hour 는 이 시간대가 시작하는 시각(몇 시)이다. 다음 시간대가 시작할 때까지 이 시간대다.
    마지막 시간대는 자정을 넘어 첫 시간대가 시작할 때까지다(story.md 의 "시각").
    """

    model_config = ConfigDict(extra='forbid')

    id: Key
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=SLOT_NAME_MAX_LENGTH)]
    start_hour: Annotated[int, Field(ge=0, lt=HOURS_PER_DAY)]


def ordered_slots(slots: list[Slot]) -> list[Slot]:
    """id 와 이름은 하나씩이고, 시작하는 시각은 차례로 커진다(하루를 차례로 나눈다)."""
    reject_repeated_keys([slot.id for slot in slots])
    reject_repeated([slot.name for slot in slots])
    if any(later.start_hour <= earlier.start_hour for earlier, later in zip(slots, slots[1:], strict=False)):
        raise ValueError('시간대의 시작 시각은 차례로 커집니다.')
    return slots


Slots = Annotated[
    list[Slot], Field(min_length=WORLD_MIN_SLOTS, max_length=WORLD_MAX_SLOTS), AfterValidator(ordered_slots)
]

# 처음 만들 때의 시간대(story.md 의 "기본값으로 둔 것": 아침, 낮, 저녁, 밤). 시각의 경계는 TRPG 의 시계와 같다
DEFAULT_SLOTS = (
    Slot(id='morning', name='아침', start_hour=7),
    Slot(id='day', name='낮', start_hour=11),
    Slot(id='evening', name='저녁', start_hour=17),
    Slot(id='night', name='밤', start_hour=21),
)


class Show(BaseModel):
    """보이기의 기본. 인물의 공개, 지도에 인물을 보이는지, 인물 창의 항목이다. 인물마다 덮어쓴다."""

    model_config = ConfigDict(extra='forbid')

    reveal: Reveal = Reveal.SHOWN
    map: MapPresence = MapPresence.SHOWN
    panel: list[PanelField] = list(PanelField)

    @model_validator(mode='after')
    def panel_once(self) -> Self:
        """인물 창의 항목은 한 번씩이다."""
        if len(set(self.panel)) != len(self.panel):
            raise ValueError('인물 창의 항목이 두 번 있습니다.')
        return self


class WorldPlace(BaseModel):
    """
    장소 하나. 캐릭터의 장소와 같고, 시간대마다의 배경(backgrounds)의 열쇠가 그 세계관의 시간대 id 다.
    그 시간대의 배경이 없으면 기본 배경(image_id)을 쓴다.
    """

    model_config = ConfigDict(extra='forbid')

    id: Key
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=PLACE_NAME_MAX_LENGTH)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=PLACE_DESCRIPTION_MAX_LENGTH)] = ''
    image_id: uuid.UUID | None = None
    backgrounds: dict[Key, uuid.UUID] = {}


class WorldItem(BaseModel):
    """물건 하나. consumable 이면 쓰면 하나 없어진다. 건네는 것과 호감도는 인물의 선물 규칙이 정한다."""

    model_config = ConfigDict(extra='forbid')

    id: Key
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=ITEM_NAME_MAX_LENGTH)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=ITEM_DESCRIPTION_MAX_LENGTH)] = ''
    consumable: bool = False
    image_id: uuid.UUID | None = None


def unique_places(places: list[WorldPlace]) -> list[WorldPlace]:
    reject_repeated_keys([place.id for place in places])
    return places


def unique_items(items: list[WorldItem]) -> list[WorldItem]:
    reject_repeated_keys([item.id for item in items])
    return items


Places = Annotated[list[WorldPlace], Field(max_length=WORLD_MAX_PLACES), AfterValidator(unique_places)]
Paths = Annotated[list[Path], Field(max_length=WORLD_MAX_PATHS), AfterValidator(unique_paths)]
Items = Annotated[list[WorldItem], Field(max_length=WORLD_MAX_ITEMS), AfterValidator(unique_items)]
StartItems = Annotated[list[StartItem], Field(max_length=WORLD_MAX_START_ITEMS), AfterValidator(unique_start_items)]

# 조건의 종류마다 쓰는 칸(ConditionKind 의 설명과 같다). target, value, count 가운데 이것만 적는다
CONDITION_FIELDS: dict[ConditionKind, frozenset[str]] = {
    ConditionKind.REACH_PLACE: frozenset({'target'}),
    ConditionKind.HOLD_ITEM: frozenset({'target', 'count'}),
    ConditionKind.GAVE_ITEM: frozenset({'target', 'value'}),
    ConditionKind.AFFECTION_AT_LEAST: frozenset({'target', 'value'}),
    ConditionKind.AFFECTION_BELOW: frozenset({'target', 'value'}),
    ConditionKind.DAY_AT_LEAST: frozenset({'count'}),
    ConditionKind.DAY_AT_MOST: frozenset({'count'}),
    ConditionKind.SLOT_IS: frozenset({'target'}),
    ConditionKind.ACCOMPANIED: frozenset({'target'}),
    ConditionKind.EVENT_SEEN: frozenset({'target'}),
    ConditionKind.ENDING_SEEN: frozenset({'target'}),
}
# count 를 쓰지 않는 종류의 count. 세지 않는다
UNCOUNTED = 1

ConditionValue = Annotated[str, StringConstraints(min_length=1, max_length=40)]


class Condition(BaseModel):
    """
    조건 하나(story.md 의 "조건"). 종류(kind)마다 쓰는 칸이 다르다(CONDITION_FIELDS).
    target 은 장소, 물건, 인물, 시간대, 이벤트의 id 다. value 는 물건의 id(건넸다)나 호감도 단계의 이름이다.
    count 는 물건의 수(가졌다)나 날짜(n일째)다. 쓰지 않는 칸은 적지 않는다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: ConditionKind
    target: Key | None = None
    value: ConditionValue | None = None
    count: Annotated[int, Field(ge=1, le=CONDITION_MAX_COUNT)] = UNCOUNTED

    @model_validator(mode='after')
    def fields_for_the_kind(self) -> Self:
        """그 종류가 쓰는 칸은 채우고, 쓰지 않는 칸은 비운다."""
        wanted = CONDITION_FIELDS[self.kind]
        missing = [name for name in ('target', 'value') if name in wanted and getattr(self, name) is None]
        extra = [name for name in ('target', 'value') if name not in wanted and getattr(self, name) is not None]
        if 'count' not in wanted and self.count != UNCOUNTED:
            extra.append('count')
        if missing or extra:
            raise ValueError(f'{self.kind} 의 칸이 맞지 않습니다(채울 것: {missing}, 비울 것: {extra}).')
        return self


class Conditions(BaseModel):
    """조건 목록과 맞추는 법. 목록이 비면 늘 맞는다."""

    model_config = ConfigDict(extra='forbid')

    match: Match = Match.ALL
    items: Annotated[list[Condition], Field(max_length=MAX_CONDITIONS)] = []


# 효과의 종류마다 amount 를 쓰는가(EffectKind 의 설명과 같다). target 은 모두 쓴다
COUNTED_EFFECTS = frozenset({EffectKind.GIVE_ITEM, EffectKind.TAKE_ITEM})
SIGNED_EFFECTS = frozenset({EffectKind.AFFECTION})


class Effect(BaseModel):
    """
    효과 하나(story.md 의 "효과"). target 은 인물, 물건, 장소의 id 다(종류마다, EffectKind).
    amount 는 호감도를 바꾸는 크기(±, 0 이 아니다)나 주고 가져가는 물건의 수(1 이상)다. 쓰지 않는 종류는 적지 않는다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: EffectKind
    target: Key
    amount: Annotated[int, Field(ge=-EFFECT_MAX_CHANGE, le=EFFECT_MAX_CHANGE)] | None = None

    @model_validator(mode='after')
    def amount_for_the_kind(self) -> Self:
        """호감도는 0 이 아닌 크기, 물건은 1~99 개, 나머지는 amount 를 적지 않는다."""
        if self.kind in SIGNED_EFFECTS and not self.amount:
            raise ValueError('호감도의 효과는 0 이 아닌 크기(amount)를 적습니다.')
        if self.kind in COUNTED_EFFECTS and not (self.amount and 1 <= self.amount <= EFFECT_MAX_COUNT):
            raise ValueError(f'물건의 효과는 1~{EFFECT_MAX_COUNT} 개(amount)를 적습니다.')
        if self.kind not in SIGNED_EFFECTS | COUNTED_EFFECTS and self.amount is not None:
            raise ValueError(f'{self.kind} 에는 amount 를 적지 않습니다.')
        return self


Effects = Annotated[list[Effect], Field(max_length=MAX_EFFECTS)]


class Scene(BaseModel):
    """
    이벤트의 장면 지시. text 는 모델에게 주는 상황 설명이다. cast 는 장면에 불러들이는 인물(4명까지)이다.
    image_id 는 일러스트다. 있으면 그림 창의 배경과 캐릭터를 대신한다. collectible 이면 열릴 때 계정에 남는다(갤러리).
    """

    model_config = ConfigDict(extra='forbid')

    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=SCENE_TEXT_MAX_LENGTH)]
    cast: Annotated[list[Key], Field(max_length=SCENE_MAX_CAST)] = []
    image_id: uuid.UUID | None = None
    collectible: bool = False

    @model_validator(mode='after')
    def cast_once_and_collect_a_picture(self) -> Self:
        """같은 인물을 두 번 부르지 않는다. 일러스트가 없으면 열 것이 없다."""
        reject_repeated_keys(self.cast)
        if self.collectible and self.image_id is None:
            raise ValueError('일러스트(image_id)가 있어야 해금 대상으로 둡니다.')
        return self


class Choice(BaseModel):
    """선택지 하나. 제작자가 적은 글과, 고르면 엔진이 반영하는 효과들이다. id 는 이벤트 안에서 고유하다."""

    model_config = ConfigDict(extra='forbid')

    id: Key
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=CHOICE_TEXT_MAX_LENGTH)]
    effects: Effects = []


def unique_choices(choices: list[Choice]) -> list[Choice]:
    reject_repeated_keys([choice.id for choice in choices])
    return choices


class Event(BaseModel):
    """
    이벤트 하나(story.md 의 "이벤트"). 행동 뒤에 엔진이 when 을 맞춰 보고, 맞는 것 가운데 적은 차례로 하나만 연다.
    열리면 on_open 의 효과를 반영하고, 이어지는 응답이 scene 을 받아 그 장면을 쓴다.
    choices 가 있으면 화면이 응답 밑에 보이고, 고르면 그 효과를 반영한 뒤 모델이 반응을 쓴다.
    repeat 이 아니면 한 번만 열린다. id 는 세계관 안에서 고유하고, 조건(event_seen)과 story 의 "본 이벤트"가 적는다.
    """

    model_config = ConfigDict(extra='forbid')

    id: Key
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=EVENT_NAME_MAX_LENGTH)]
    when: Conditions = Conditions()
    repeat: bool = False
    scene: Scene
    on_open: Effects = []
    choices: Annotated[list[Choice], Field(max_length=EVENT_MAX_CHOICES), AfterValidator(unique_choices)] = []


def unique_events(events: list[Event]) -> list[Event]:
    reject_repeated_keys([event.id for event in events])
    return events


Events = Annotated[list[Event], Field(max_length=WORLD_MAX_EVENTS), AfterValidator(unique_events)]


class ScheduleLine(BaseModel):
    """
    일정의 줄 하나(story.md 의 "인물과 장면"). 그 시간대에 조건이 맞으면 그 장소에 있다.
    위에 적은 줄부터 맞춰 본다. 맞는 줄이 없으면 기본 장소(home)다.
    """

    model_config = ConfigDict(extra='forbid')

    slot: Key
    place: Key
    when: Conditions = Conditions()


class Gift(BaseModel):
    """
    선물의 규칙 하나. 그 물건을 건네면 호감도를 change 만큼 바꾼다(0~100 안으로 자른다).
    once 면 그 가지에서 처음 한 번만이다. id 는 인물 안에서 고유하고, story 가 "이미 했다"를 적는다.
    """

    model_config = ConfigDict(extra='forbid')

    id: Key
    item: Key
    change: Annotated[int, Field(ge=-AFFECTION_MAX_CHANGE, le=AFFECTION_MAX_CHANGE)]
    once: bool = False

    @model_validator(mode='after')
    def changes_something(self) -> Self:
        """바꾸지 않는 규칙은 없다."""
        if self.change == 0:
            raise ValueError('규칙은 호감도를 바꿉니다(0 이 아닙니다).')
        return self


def unique_gifts(gifts: list[Gift]) -> list[Gift]:
    reject_repeated_keys([gift.id for gift in gifts])
    return gifts


class CastAffection(BaseModel):
    """
    인물의 호감도. 값 하나(0~100)와 단계들이다. chat 의 호감도와 보이는 방식과 단계가 같다.
    바뀌는 길은 선물의 규칙과 이벤트의 효과(두 번째 조각)다. 대화의 내용만으로는 움직이지 않는다(story.md 의 "호감도").
    """

    model_config = ConfigDict(extra='forbid')

    display: AffectionDisplay = AffectionDisplay.NUMBER
    start: Annotated[int, Field(ge=0, le=AFFECTION_MAX)] = 0
    stages: Annotated[
        list[Stage], Field(min_length=1, max_length=AFFECTION_MAX_STAGES), AfterValidator(stages_from_zero)
    ]
    gifts: Annotated[list[Gift], Field(max_length=CAST_MAX_GIFTS), AfterValidator(unique_gifts)] = []


class Confession(BaseModel):
    """
    인물에게 하는 고백(story.md 의 "고백과 엔딩"). 호감도가 stage(단계의 이름) 이상이고 when 이 맞으면 성공이다.
    실패하면 on_fail 대로 한다. 계속(continue)이면 호감도를 fail_drop 만큼 내리고 cooldown_days 동안 다시 못 한다.
    끝(end)이면 그 인물에게 고백 실패로 시작되는 엔딩을 판정한다. 비어 있으면(null) 고백할 수 없는 인물이다.
    """

    model_config = ConfigDict(extra='forbid')

    stage: ConditionValue
    when: Conditions = Conditions()
    on_fail: ConfessionFailure = ConfessionFailure.CONTINUE
    fail_drop: Annotated[int, Field(ge=0, le=AFFECTION_MAX)] = CONFESSION_FAIL_DROP_DEFAULT
    cooldown_days: Annotated[int, Field(ge=1, le=CONFESSION_MAX_COOLDOWN_DAYS)] = CONFESSION_COOLDOWN_DEFAULT_DAYS


class CastMember(BaseModel):
    """
    인물 하나. character_id 는 만든 사람의 캐릭터다. 게시할 때 그 마지막 판의 story 에 쓰는 칸을 복사한다.
    id 는 세계관 안에서 고유하고 조건과 일정이 가리킨다. 판이 바뀌어도 같은 인물은 같은 id 로 둔다.

    home 은 기본 장소다. 비우면 어디에도 없다(이벤트로만 나온다). schedule 은 기본 장소를 덮어쓰는 일정이다.
    reveal, map, panel 은 보이기의 덮어쓰기다. 비우면 세계관의 기본을 쓴다.
    map_stage 는 지도에 보이는 호감도의 단계다. 이 인물의 지도가 stage 일 때 쓴다.
    confession 은 고백이다(판의 형식 3). 비우면 고백할 수 없다.
    """

    model_config = ConfigDict(extra='forbid')

    id: Key
    character_id: uuid.UUID
    home: Key | None = None
    schedule: Annotated[list[ScheduleLine], Field(max_length=CAST_MAX_SCHEDULE)] = []
    affection: CastAffection
    reveal: Reveal | None = None
    map: MapPresence | None = None
    map_stage: ConditionValue | None = None
    panel: list[PanelField] | None = None
    confession: Confession | None = None


def unique_cast(cast: list[CastMember]) -> list[CastMember]:
    """id 는 하나씩이고, 같은 캐릭터를 두 번 넣지 않는다."""
    reject_repeated_keys([member.id for member in cast])
    characters = [member.character_id for member in cast]
    if len(set(characters)) != len(characters):
        raise ValueError('같은 캐릭터가 두 번 있습니다.')
    return cast


Cast = Annotated[list[CastMember], Field(max_length=WORLD_MAX_CAST), AfterValidator(unique_cast)]


def reject_repeated_lorebooks(ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """같은 로어북을 두 번 가리키면 거부한다."""
    if len(set(ids)) != len(ids):
        raise ValueError('같은 로어북이 두 번 있습니다.')
    return ids


Lorebooks = Annotated[list[uuid.UUID], Field(max_length=WORLD_MAX_LOREBOOKS), AfterValidator(reject_repeated_lorebooks)]
DeadlineDays = Annotated[int, Field(ge=1, le=DEADLINE_MAX_DAYS)]

# 엔딩의 시작마다 target 이 무엇인가. 인물(고백), 이벤트, 없음(기한)
TRIGGER_TARGETS = frozenset({EndingTrigger.CONFESS_SUCCESS, EndingTrigger.CONFESS_FAIL, EndingTrigger.EVENT})


class Trigger(BaseModel):
    """엔딩의 시작. 고백 성공과 실패는 인물, 이벤트는 이벤트의 id 를 target 에 적는다. 기한은 target 이 없다."""

    model_config = ConfigDict(extra='forbid')

    kind: EndingTrigger
    target: Key | None = None

    @model_validator(mode='after')
    def target_for_the_kind(self) -> Self:
        """기한 말고는 target 을 적고, 기한은 적지 않는다."""
        if (self.kind in TRIGGER_TARGETS) != (self.target is not None):
            raise ValueError(f'{self.kind} 의 target 이 맞지 않습니다.')
        return self


class Ending(BaseModel):
    """
    엔딩 하나(story.md 의 "고백과 엔딩"). trigger 가 일어나면 그 시작의 엔딩을 적은 차례로 맞춰 보고 when 이 맞는
    첫 엔딩을 고른다. scene 은 엔딩의 장면이다(모델이 쓴다). unlock 이면 계정의 엔딩 기록과 갤러리에 남는다.
    hint 는 못 본 사람에게 보이는 한 줄이다. 못 본 엔딩의 이름은 story 가 내려보내지 않는다.
    """

    model_config = ConfigDict(extra='forbid')

    id: Key
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=ENDING_NAME_MAX_LENGTH)]
    trigger: Trigger
    when: Conditions = Conditions()
    scene: Scene
    unlock: bool = True
    hint: Annotated[str, StringConstraints(strip_whitespace=True, max_length=ENDING_HINT_MAX_LENGTH)] = ''


def unique_endings(endings: list[Ending]) -> list[Ending]:
    reject_repeated_keys([ending.id for ending in endings])
    return endings


Endings = Annotated[list[Ending], Field(max_length=WORLD_MAX_ENDINGS), AfterValidator(unique_endings)]

# DB 에 dict(의 목록)로 적는 칸
DOCUMENT_LISTS = ('slots', 'places', 'paths', 'items', 'start_items', 'cast', 'events', 'endings')
# 고칠 때 null 로 비울 수 있는 칸. 그림, 시작 장소와 시간대, 기한은 "없음"이 null 이다
NULLABLE_FIELDS = frozenset({'image_id', 'start_place', 'start_slot', 'deadline_days'})


def attached_images(
    image_id: uuid.UUID | None, places: list[WorldPlace], items: list[WorldItem], scenes: list[Scene]
) -> list[uuid.UUID]:
    """붙인 그림들. 대표 그림, 장소의 배경(기본, 시간대마다), 물건의 그림, 이벤트와 엔딩의 일러스트. 없는 것은 뺀다."""
    found = [image_id] if image_id is not None else []
    found += [entry.image_id for entry in [*places, *items] if entry.image_id is not None]
    found += [scene.image_id for scene in scenes if scene.image_id is not None]
    return found + [background for place in places for background in place.backgrounds.values()]


def scenes_of(events: list[Event], endings: list[Ending]) -> list[Scene]:
    """이벤트와 엔딩의 장면들."""
    return [event.scene for event in events] + [ending.scene for ending in endings]


def cast_characters(cast: list[CastMember]) -> list[uuid.UUID]:
    """인물들이 가리키는 캐릭터들. 자기 캐릭터인지 볼 것들이다."""
    return [member.character_id for member in cast]


def as_rows(model: BaseModel, names: set[str]) -> dict:
    """보낸 칸을 DB 에 적을 모양으로. 목록은 dict 의 목록, 보이기는 dict 다(그림과 캐릭터의 id 는 글이다)."""
    values = {name: getattr(model, name) for name in names}
    for name in DOCUMENT_LISTS:
        if values.get(name) is not None:
            values[name] = [entry.model_dump(mode='json') for entry in values[name]]
    if values.get('show') is not None:
        values['show'] = values['show'].model_dump(mode='json')
    return values


class WorldCreate(BaseModel):
    """세계관을 만들 때 받는 값. 이름과 장르가 필수다. 시간대는 아침, 낮, 저녁, 밤에서 시작한다. 처음에는 비공개다."""

    model_config = ConfigDict(extra='forbid')

    name: Name
    intro_html: Intro = ''
    tags: Tags = []
    # 장르. 반드시 하나를 고른다(app/genres.py)
    genre: Genre
    image_id: uuid.UUID | None = None
    rating: Rating = Rating.ALL
    slots: Slots = list(DEFAULT_SLOTS)
    start_slot: Key | None = None
    deadline_days: DeadlineDays | None = None
    after_ending: AfterEnding = AfterEnding.END
    show: Show = Show()
    places: Places = []
    paths: Paths = []
    start_place: Key | None = None
    items: Items = []
    start_items: StartItems = []
    cast: Cast = []
    events: Events = []
    endings: Endings = []
    lorebooks: Lorebooks = []

    def image_ids(self) -> list[uuid.UUID]:
        """붙인 그림들. 자기 그림인지 볼 것들이다."""
        return attached_images(self.image_id, self.places, self.items, scenes_of(self.events, self.endings))

    def character_ids(self) -> list[uuid.UUID]:
        """인물들이 가리키는 캐릭터들."""
        return cast_characters(self.cast)

    def values(self) -> dict:
        """DB 에 적을 칸과 값. 시작 시간대를 적지 않았으면 첫 시간대다."""
        values = as_rows(self, set(type(self).model_fields))
        values['start_slot'] = self.start_slot or self.slots[0].id
        return values


class WorldUpdate(BaseModel):
    """
    세계관을 고칠 때 받는 값. 보낸 칸만 바꾼다. 초안만 바뀐다. 게시한 판은 그대로다.

    null 은 그림, 시작 장소와 시간대, 기한만 받는다. 공개 범위(visibility)도 여기서 바꾼다(공개는 운영자만, 1~2단계).
    """

    model_config = ConfigDict(extra='forbid')

    name: Name | None = None
    intro_html: Intro | None = None
    tags: Tags | None = None
    genre: Genre | None = None
    image_id: uuid.UUID | None = None
    rating: Rating | None = None
    visibility: Visibility | None = None
    slots: Slots | None = None
    start_slot: Key | None = None
    deadline_days: DeadlineDays | None = None
    after_ending: AfterEnding | None = None
    show: Show | None = None
    places: Places | None = None
    paths: Paths | None = None
    start_place: Key | None = None
    items: Items | None = None
    start_items: StartItems | None = None
    cast: Cast | None = None
    events: Events | None = None
    endings: Endings | None = None
    lorebooks: Lorebooks | None = None

    @model_validator(mode='after')
    def null_only_where_allowed(self) -> Self:
        """null 로 비울 수 있는 칸 말고는 null 을 거부한다. "비우기"인지 "보내지 않음"인지 헷갈린다."""
        nulls = [name for name in self.model_fields_set - NULLABLE_FIELDS if getattr(self, name) is None]
        if nulls:
            raise ValueError(f'null 로 비울 수 없는 칸입니다: {", ".join(sorted(nulls))}')
        return self

    def changes(self) -> dict:
        """보낸 칸과 그 값을 DB 에 적을 모양으로."""
        return as_rows(self, set(self.model_fields_set))

    def image_ids(self) -> list[uuid.UUID]:
        """보낸 칸에 붙인 그림들. 자기 그림인지 볼 것들이다."""
        scenes = scenes_of(self.events or [], self.endings or [])
        return attached_images(self.image_id, self.places or [], self.items or [], scenes)

    def character_ids(self) -> list[uuid.UUID]:
        """보낸 인물들이 가리키는 캐릭터들."""
        return cast_characters(self.cast or [])


class WorldDetail(BaseModel):
    """세계관의 초안 하나. 만든 사람만 본다. latest_version 은 마지막으로 게시한 판의 번호다(없으면 null)."""

    id: uuid.UUID
    name: str
    intro_html: str
    tags: list[str]
    genre: Genre
    image_id: uuid.UUID | None
    rating: Rating
    visibility: Visibility
    slots: list[Slot]
    start_slot: str | None
    deadline_days: int | None
    after_ending: AfterEnding
    show: Show
    places: list[WorldPlace]
    paths: list[Path]
    start_place: str | None
    items: list[WorldItem]
    start_items: list[StartItem]
    # 인물들. 지운 캐릭터를 가리키는 인물이 남아 있을 수 있다(다시 게시할 때 막힌다)
    cast: list[CastMember]
    events: list[Event]
    endings: list[Ending]
    lorebooks: list[uuid.UUID]
    latest_version: int | None
    published_at: datetime | None
    # 운영자가 숨긴 시각. 숨긴 동안은 공개여도 남에게 보이지 않는다(캐릭터와 같다)
    hidden_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WorldSummary(BaseModel):
    """내 세계관 목록의 한 줄."""

    id: uuid.UUID
    name: str
    rating: Rating
    visibility: Visibility
    latest_version: int | None
    hidden_at: datetime | None = None
    updated_at: datetime


class WorldPage(BaseModel):
    """목록의 한 쪽과 전체 개수."""

    items: list[WorldSummary]
    total: int


class WorldVersionCreate(BaseModel):
    """게시할 때 받는 값. 이번 판에서 무엇이 바뀌었는지 적는다(비워도 된다)."""

    model_config = ConfigDict(extra='forbid')

    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=VERSION_NOTE_MAX_LENGTH)] = ''


class WorldVersionSummary(BaseModel):
    """판의 목록에 싣는 값. 굳힌 문서는 싣지 않는다."""

    id: uuid.UUID
    number: int
    note: str
    created_at: datetime


class WorldVersionDetail(WorldVersionSummary):
    """판 하나. 굳힌 문서까지 싣는다."""

    document: WorldDocument


class WorldPublishResult(WorldVersionDetail):
    """
    게시한 결과. 새 판과, 소개에서 걸러 낸 것들(removed), 알리는 것들(warnings)이다.

    걸러 낸 것과 알리는 것이 있어도 게시는 된다. 화면이 제작자에게 보인다.
    """

    removed: list[RemovedItem]
    warnings: list[str]


class WorldPublishCheck(BaseModel):
    """
    지금 게시하면 막히는 이유, 알리는 것, 걸러질 것. 판을 만들지 않는다.

    problems 는 게시가 409 로 돌려주는 것과 같은 이름이다. 비어 있으면 게시할 수 있다(ready).
    warnings 는 막지 않는다(닿지 않는 장소 등, 2026-10-24 유저 결정).
    """

    ready: bool
    problems: list[str]
    warnings: list[str]
    removed: list[RemovedItem]


class WorldCopy(BaseModel):
    """
    story 서버에 내주는 판. 세션을 시작할 때 가져가 고정한다.
    가져간 쪽은 번호를 적어 두고, 지금의 번호(WorldVersionNumber)가 크면 "새 판이 있다"를 알린다.
    """

    id: uuid.UUID
    version: int
    rating: Rating
    published_at: datetime
    document: WorldDocument


class WorldVersionNumber(BaseModel):
    """세계관의 지금 판 번호. 화면을 열 때 한 번 묻는다. 문서는 싣지 않는다."""

    id: uuid.UUID
    version: int


class PublicWorldSummary(BaseModel):
    """공개 목록의 한 줄. 마지막 판의 값이다. deadline_days 는 기한(날 수)이고 없으면 null 이다."""

    id: uuid.UUID
    version: int
    name: str
    tags: list[str]
    genre: Genre
    rating: Rating
    image_id: uuid.UUID | None
    deadline_days: int | None
    published_at: datetime


class PublicWorldPage(BaseModel):
    """공개 목록의 한 쪽과 전체 개수."""

    items: list[PublicWorldSummary]
    total: int


class PublicCastMember(BaseModel):
    """
    소개에 보이는 인물 하나. reveal 이 silhouette 이면 이름과 그림을 싣지 않는다(null).
    숨김(hidden)인 인물은 목록에 없다.
    """

    id: str
    reveal: Reveal
    name: str | None
    image_id: uuid.UUID | None


class PublicWorldDetail(BaseModel):
    """
    공개 세계관의 소개(D1). 마지막 판에서 보여도 되는 것만 골라 싣는다.
    이벤트, 조건, 엔딩의 이름과 조건, 인물의 일정과 호감도 규칙은 싣지 않는다(플레이의 내용이다).
    intro_html 은 게시할 때 거른 소개다. ending_count 는 계정에 남는 엔딩(unlock)의 수다.
    """

    id: uuid.UUID
    version: int
    published_at: datetime
    name: str
    intro_html: str
    tags: list[str]
    # 장르. 소개 화면의 테마를 정한다
    genre: Genre
    rating: Rating
    image_id: uuid.UUID | None
    deadline_days: int | None
    after_ending: AfterEnding
    cast: list[PublicCastMember]
    ending_count: int
