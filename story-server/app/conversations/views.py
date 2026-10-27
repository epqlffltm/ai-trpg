# story-server/app/conversations/views.py

"""
세션에서 화면이 쓰는 세계관의 칸(WorldView)을 만든다. DB 도 모델도 모른다.

판의 문서에는 플레이의 내용(이벤트와 엔딩의 조건, 인물의 일정과 호감도 규칙)과 아직 보이면 안 되는 것
(만나지 않은 실루엣과 숨김 인물, 못 본 엔딩의 이름)이 들어 있다. 그대로 화면에 내려보내지 않고,
이 가지의 상태에 맞춰 지금 보여도 되는 것만 고른다(docs/product/screens.md 의 D2~D6).

  - 만남: 이 가지의 답의 장면에 한 번이라도 들어온 인물이다(met_on). 엔진이 정한 장면의 인물이라 모델이 바꾸지 못한다.
    상태에 따로 적지 않는다. 답마다 그때의 장면의 인물(messages.cast)이 이미 저장되어 있다
  - 인물: 만났으면 보임이다. 만나기 전에는 제작자가 고른 공개를 따른다.
    실루엣은 이름과 그림을 가리고, 숨김은 목록에 없다
  - 인물 창: 제작자가 고른 항목(소개, 나이, 성별, 호감도)만 싣는다. 고백 대기, 건넨 선물, 함께 본 이벤트는
    호감도를 보이는 인물에만 싣는다(판에 그 셋을 따로 고르는 칸이 아직 없다)
  - 이벤트: 이 가지에서 열린 것의 이름, 장면의 인물, 일러스트. 선택지의 글은 고르기를 기다리는 이벤트에만 싣는다
  - 엔딩: 칸은 모두 보인다. 이름과 일러스트는 본 것(계정의 기록이나 이 가지에서 본 것)만이고, 힌트는 늘 보인다
  - 지도: 장소마다 가 본 곳인가와 지금 거기 보이는 인물.
    가 본 곳은 가지의 말에 붙은 상태의 장소와 시작 장소다(visited_on). 인물의 자리는 엔진이 정한다(동행, 일정, 기본).
    가 본 곳에 있고, 만났고, 제작자의 지도 보이기(보임, 숨김, 호감도 단계 이상)를 통과한 인물만 보인다.
    함께 다니는 인물은 넣지 않는다
판의 모양은 asset 서버의 WorldDocument 다. 모르는 칸은 버리고 빈 칸은 기본값으로 읽는다.
"""

import uuid
from collections.abc import Iterable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from app.conversations.schemas import (
    CastAffectionOut,
    CastOut,
    ChoiceOut,
    EndingOut,
    EventOut,
    ItemOut,
    MapPlaceOut,
    PathOut,
    PlaceOut,
    SlotOut,
    SpriteOut,
    StageOut,
    WorldView,
)
from app.engine.conditions import affection_of, stage_floor
from app.engine.scene import place_of_character
from app.engine.state import StoryState
from app.engine.world import World

# 인물의 공개(asset 서버의 Reveal)와 인물 창의 항목(PanelField)
SHOWN = 'shown'
SILHOUETTE = 'silhouette'
HIDDEN = 'hidden'
PANEL_INTRO = 'intro'
PANEL_AGE = 'age'
PANEL_GENDER = 'gender'
PANEL_AFFECTION = 'affection'
# 지도에 인물을 보이는가(asset 서버의 MapPresence)
MAP_SHOWN = 'shown'
MAP_STAGE = 'stage'


class Part(BaseModel):
    """판의 칸을 읽는 모양의 공통. 모르는 칸은 버리고 읽은 뒤에는 바꾸지 않는다."""

    model_config = ConfigDict(extra='ignore', frozen=True)


class ViewSlot(Part):
    id: str
    name: str = ''
    start_hour: int = 0


class ViewPlace(Part):
    id: str
    name: str = ''
    description: str = ''
    image_id: uuid.UUID | None = None
    backgrounds: dict[str, uuid.UUID] = {}


class ViewPath(Part):
    a: str
    b: str
    minutes: int = 0


class ViewItem(Part):
    id: str
    name: str = ''
    description: str = ''
    consumable: bool = False
    image_id: uuid.UUID | None = None


class ViewSprite(Part):
    id: str
    image_id: uuid.UUID
    expression: str = ''


class ViewCharacter(Part):
    name: str = ''
    intro_html: str = ''
    age: str = ''
    gender: str = ''
    image_id: uuid.UUID | None = None
    sprites: tuple[ViewSprite, ...] = ()


class ViewStage(Part):
    name: str
    at: int = 0


class ViewAffection(Part):
    display: str = 'stage'
    stages: tuple[ViewStage, ...] = ()


class ViewCast(Part):
    id: str
    character: ViewCharacter = ViewCharacter()
    reveal: str = SHOWN
    panel: tuple[str, ...] = ()
    map: str = MAP_SHOWN
    map_stage: str | None = None
    affection: ViewAffection = ViewAffection()
    confession: dict | None = None


class ViewScene(Part):
    cast: tuple[str, ...] = ()
    image_id: uuid.UUID | None = None


class ViewChoice(Part):
    id: str
    text: str = ''


class ViewEvent(Part):
    id: str
    name: str = ''
    scene: ViewScene = ViewScene()
    choices: tuple[ViewChoice, ...] = ()


class ViewEnding(Part):
    id: str
    name: str = ''
    hint: str = ''
    unlock: bool = True
    scene: ViewScene = ViewScene()


class ViewDocument(Part):
    """화면에 보일 수 있는 판의 칸."""

    name: str = ''
    intro_html: str = ''
    tags: tuple[str, ...] = ()
    image_id: uuid.UUID | None = None
    deadline_days: int | None = None
    after_ending: str = 'end'
    slots: tuple[ViewSlot, ...] = ()
    places: tuple[ViewPlace, ...] = ()
    paths: tuple[ViewPath, ...] = ()
    items: tuple[ViewItem, ...] = ()
    cast: tuple[ViewCast, ...] = ()
    events: tuple[ViewEvent, ...] = ()
    endings: tuple[ViewEnding, ...] = ()


def read_view_document(document: Mapping) -> ViewDocument:
    """판의 문서(사본의 document)를 화면에 보일 수 있는 칸의 모양으로."""
    return ViewDocument.model_validate(document)


def met_on(casts: Iterable[Sequence[str]]) -> frozenset[str]:
    """이 가지의 답들의 장면의 인물을 모은 것(만난 인물). casts 는 답마다의 장면의 인물이다."""
    return frozenset(cast_id for cast in casts for cast_id in cast)


def shown_reveal(reveal: str, met: bool) -> str | None:
    """지금 보이는 법. 만났으면 보임, 아니면 제작자가 고른 공개다. 숨김이고 만나지 않았으면 None(목록에 없다)."""
    if met:
        return SHOWN
    if reveal in (SHOWN, SILHOUETTE):
        return reveal
    return None


def cast_events(document: ViewDocument, state: StoryState, cast_id: str) -> list[str]:
    """이 가지에서 열린 이벤트 가운데 그 인물을 장면에 부른 것들. 판의 차례다."""
    return [event.id for event in document.events if event.id in state.seen and cast_id in event.scene.cast]


def affection_out(member: ViewCast, state: StoryState) -> CastAffectionOut:
    """인물 창의 호감도. 고백 대기는 다시 고백할 시각이 아직 오지 않았을 때만이다."""
    until = state.cooldowns.get(member.id)
    return CastAffectionOut(
        display=member.affection.display,
        stages=[StageOut(name=stage.name, at=stage.at) for stage in member.affection.stages],
        cooling_until=until if until is not None and until > state.minutes else None,
        gifts=sorted(item for cast_id, item in state.gifts if cast_id == member.id),
    )


def panel_text(member: ViewCast, field: str, value: str) -> str | None:
    """인물 창의 글 칸. 제작자가 고른 항목이면 그 글, 아니면 None."""
    return value if field in member.panel else None


def sprite_out(sprite: ViewSprite) -> SpriteOut:
    """인물의 그림 하나."""
    return SpriteOut(id=sprite.id, image_id=sprite.image_id, expression=sprite.expression)


def shown_cast(document: ViewDocument, member: ViewCast, state: StoryState, met: bool) -> CastOut:
    """보이는 인물. 이름, 그림, 고른 인물 창의 항목을 싣는다."""
    shows_affection = PANEL_AFFECTION in member.panel
    character = member.character
    return CastOut(
        id=member.id,
        reveal=SHOWN,
        met=met,
        name=character.name,
        image_id=character.image_id,
        sprites=[sprite_out(sprite) for sprite in character.sprites],
        confessable=member.confession is not None,
        intro_html=panel_text(member, PANEL_INTRO, character.intro_html),
        age=panel_text(member, PANEL_AGE, character.age),
        gender=panel_text(member, PANEL_GENDER, character.gender),
        affection=affection_out(member, state) if shows_affection else None,
        events=cast_events(document, state, member.id) if shows_affection else [],
    )


def silhouette_cast(member: ViewCast) -> CastOut:
    """실루엣인 인물. 이름, 그림, 인물 창의 칸을 가린다."""
    return CastOut(
        id=member.id,
        reveal=SILHOUETTE,
        met=False,
        name=None,
        image_id=None,
        sprites=[],
        confessable=False,
        intro_html=None,
        age=None,
        gender=None,
        affection=None,
        events=[],
    )


def cast_out(document: ViewDocument, member: ViewCast, state: StoryState, met: frozenset[str]) -> CastOut | None:
    """보이는 인물 하나. 숨김이고 만나지 않았으면 None."""
    reveal = shown_reveal(member.reveal, member.id in met)
    if reveal is None:
        return None
    if reveal == SILHOUETTE:
        return silhouette_cast(member)
    return shown_cast(document, member, state, member.id in met)


def event_out(event: ViewEvent, state: StoryState) -> EventOut:
    """열린 이벤트 하나. 선택지의 글은 고르기를 기다리는 이벤트에만 싣는다."""
    waiting = state.choosing == event.id
    return EventOut(
        id=event.id,
        name=event.name,
        cast=list(event.scene.cast),
        image_id=event.scene.image_id,
        choices=[ChoiceOut(id=choice.id, text=choice.text) for choice in event.choices] if waiting else [],
    )


def ending_out(ending: ViewEnding, seen: bool) -> EndingOut:
    """엔딩의 칸 하나. 이름과 일러스트는 본 엔딩만이다."""
    return EndingOut(
        id=ending.id,
        seen=seen,
        name=ending.name if seen else None,
        image_id=ending.scene.image_id if seen else None,
        hint=ending.hint,
        unlock=ending.unlock,
    )


def slot_out(slot: ViewSlot) -> SlotOut:
    """시간대 하나."""
    return SlotOut(id=slot.id, name=slot.name, start_hour=slot.start_hour)


def place_out(place: ViewPlace) -> PlaceOut:
    """장소 하나."""
    return PlaceOut(
        id=place.id,
        name=place.name,
        description=place.description,
        image_id=place.image_id,
        backgrounds=dict(place.backgrounds),
    )


def path_out(path: ViewPath) -> PathOut:
    """길 하나."""
    return PathOut(a=path.a, b=path.b, minutes=path.minutes)


def item_out(item: ViewItem) -> ItemOut:
    """물건 하나."""
    return ItemOut(
        id=item.id, name=item.name, description=item.description, consumable=item.consumable, image_id=item.image_id
    )


def visible_cast(document: ViewDocument, state: StoryState, met: frozenset[str]) -> list[CastOut]:
    """보이는 인물들. 판에 적힌 차례다."""
    members = (cast_out(document, member, state, met) for member in document.cast)
    return [member for member in members if member is not None]


def seen_endings(state: StoryState, recorded: frozenset[str]) -> frozenset[str]:
    """본 엔딩들. 계정에 남은 것과, 이 가지에서 본 것(계정에 남지 않는 엔딩이어도)이다."""
    return recorded | ({state.ending} if state.ending is not None else frozenset())


def visited_on(start_place: str, places: Iterable[str | None]) -> frozenset[str]:
    """가 본 장소들. 시작 장소와, 가지의 말에 붙은 상태들의 장소(places, 상태가 없는 말은 None)다."""
    return frozenset({start_place, *(place for place in places if place is not None)})


def shown_on_map(world: World, member: ViewCast, state: StoryState) -> bool:
    """제작자의 지도 보이기. 보임은 보이고, 단계는 호감도가 그 단계 이상일 때 보이고, 숨김은 보이지 않는다."""
    if member.map == MAP_SHOWN:
        return True
    if member.map != MAP_STAGE:
        return False
    floor = stage_floor(world, member.id, member.map_stage)
    return floor is not None and affection_of(state, world, member.id) >= floor


def where_on_map(world: World, member: ViewCast, state: StoryState) -> str | None:
    """인물이 지금 있는 장소(엔진이 정한다). 함께 다니거나 어디에도 없거나 판에 없는 인물이면 None."""
    engine_member = world.member(member.id)
    if engine_member is None or member.id in state.companions:
        return None
    return place_of_character(engine_member, state, world).place


def map_out(
    world: World, document: ViewDocument, state: StoryState, met: frozenset[str], visited: frozenset[str]
) -> list[MapPlaceOut]:
    """지도의 장소마다 가 본 곳인가와 지금 거기 보이는 인물. 장소는 판의 차례, 인물도 판의 차례다."""
    seen_here: dict[str, list[str]] = {}
    for member in document.cast:
        place = where_on_map(world, member, state)
        if place in visited and member.id in met and shown_on_map(world, member, state):
            seen_here.setdefault(place, []).append(member.id)
    return [
        MapPlaceOut(id=place.id, visited=place.id in visited, cast=seen_here.get(place.id, []))
        for place in document.places
    ]


def world_view(
    world: World,
    document: Mapping,
    state: StoryState,
    met: frozenset[str],
    recorded: frozenset[str],
    visited: frozenset[str],
) -> WorldView:
    """
    이 가지의 상태(state)와 만난 인물(met), 계정에 남은 엔딩(recorded), 가 본 장소(visited)에 맞춘 세계관의 칸.
    world 는 엔진이 읽은 판이다(인물의 자리를 정한다). 이 가지에서 본 엔딩(state.ending)은 계정에 남지 않아도 본 것이다.
    지금 있는 장소는 가 본 곳이다.
    """
    read = read_view_document(document)
    seen = seen_endings(state, recorded)
    return WorldView(
        name=read.name,
        intro_html=read.intro_html,
        tags=list(read.tags),
        image_id=read.image_id,
        deadline_days=read.deadline_days,
        after_ending=read.after_ending,
        slots=[slot_out(slot) for slot in read.slots],
        places=[place_out(place) for place in read.places],
        paths=[path_out(path) for path in read.paths],
        items=[item_out(item) for item in read.items],
        cast=visible_cast(read, state, met),
        events=[event_out(event, state) for event in read.events if event.id in state.seen],
        endings=[ending_out(ending, ending.id in seen) for ending in read.endings],
        map=map_out(world, read, state, met, visited | {state.place}),
    )
