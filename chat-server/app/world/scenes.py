# chat-server/app/world/scenes.py

"""
이벤트 씬이 나오는 조건을 맞춘다(#669). DB 를 모르는 순수 함수다.

제작자가 이벤트 씬마다 조건 하나를 적는다(asset 의 판 형식 5). 사용자가 행동한 뒤 엔진이 맞춘다.
  - reach_place: 그 장소에 갔다(이번 행동이 그 장소로의 이동이다)
  - give_item: 그 물건을 처음 건넸다(이번 행동이 그 물건을 건넨 것이다)
  - affection_stage: 호감도가 그 단계 이상이다(이번 행동 뒤의 값으로 본다)
한 가지에서 한 번만 나온다. 나온 것은 상태의 shown 에 적는다(가지를 바꾸면 그 가지의 것이다).
한 행동에 여럿이 맞으면 판의 차례로 첫 것이 그 행동의 답에 붙고, 나머지도 나온 것으로 적고 연 것으로 센다
(사건이 지나가면 다시 오지 않으니 놓치지 않게 한다).
조건이 맞는 것은 행동뿐이다. 말만 주고받아서는 상태가 바뀌지 않으므로 새로 맞는 것이 없다.
"""

from dataclasses import dataclass, replace

from app.assets.schemas import CharacterDocument, EventSceneDocument
from app.world.affection import stage_index
from app.world.state import WorldState

# 조건의 종류(asset 서버의 IllustrationWhen)
REACH_PLACE = 'reach_place'
GIVE_ITEM = 'give_item'
AFFECTION_STAGE = 'affection_stage'
# 이번 행동이 일으킨 일로 맞추는 종류
EVENT_KINDS = frozenset({REACH_PLACE, GIVE_ITEM})


@dataclass(frozen=True)
class Event:
    """이번 행동이 일으킨 일. kind 는 reach_place 나 give_item, target 은 그 장소나 물건의 id 다."""

    kind: str
    target: str


@dataclass(frozen=True)
class Revealed:
    """이번 행동으로 나온 이벤트 씬들(판의 차례). 첫 것이 답에 붙는다."""

    event_scenes: tuple[EventSceneDocument, ...] = ()

    @property
    def shown(self) -> EventSceneDocument | None:
        """답에 붙는 이벤트 씬. 없으면 None."""
        return self.event_scenes[0] if self.event_scenes else None

    @property
    def collected(self) -> tuple[str, ...]:
        """계정에 연 것으로 적을 것들의 id. 해금 대상만이다."""
        return tuple(event_scene.id for event_scene in self.event_scenes if event_scene.collectible)


def stage_reached(document: CharacterDocument, state: WorldState, name: str) -> bool:
    """호감도가 name 단계 이상인가. 호감도가 없거나 모르는 단계면 거짓이다."""
    if document.affection is None or state.affection is None:
        return False
    names = [stage.name for stage in document.affection.stages]
    if name not in names:
        return False
    return stage_index(document.affection, state.affection) >= names.index(name)


def condition_met(
    document: CharacterDocument, state: WorldState, event: Event | None, event_scene: EventSceneDocument
) -> bool:
    """그 이벤트 씬의 조건이 이번 행동(event)과 그 뒤의 상태(state)로 맞는가. 모르는 종류는 맞지 않는다."""
    when = event_scene.when
    if when.kind == AFFECTION_STAGE:
        return stage_reached(document, state, when.target)
    if when.kind not in EVENT_KINDS or event is None:
        return False
    return (event.kind, event.target) == (when.kind, when.target)


def reveal(document: CharacterDocument, state: WorldState, event: Event | None) -> Revealed:
    """이번 행동으로 새로 나오는 이벤트 씬들. 이 가지에서 이미 나온 것은 뺀다."""
    found = tuple(
        event_scene
        for event_scene in document.event_scenes
        if event_scene.id not in state.shown and condition_met(document, state, event, event_scene)
    )
    return Revealed(found)


def mark_shown(state: WorldState, revealed: Revealed) -> WorldState:
    """나온 이벤트 씬들을 상태의 shown 에 적는다(나온 차례)."""
    if not revealed.event_scenes:
        return state
    return replace(state, shown=(*state.shown, *(event_scene.id for event_scene in revealed.event_scenes)))


def find_scene(document: CharacterDocument, scene_id: str | None) -> EventSceneDocument | None:
    """판의 이벤트 씬 하나. 없으면 None."""
    if scene_id is None:
        return None
    return next((item for item in document.event_scenes if item.id == scene_id), None)
