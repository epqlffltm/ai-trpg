# chat-server/app/world/actions.py

"""
행동 하나를 상태에 적용한다(이동, 쓰기, 건네기, 시간 보내기). DB 를 모르는 순수 함수다.

할 수 있는지 보고(안 되면 ActionRefusedError), 바뀐 상태와 행동 말의 글을 돌려준다. 저장은 부르는 쪽이 한다.
행동의 결과 뒤에 호감도의 규칙을 걸고(app/world/affection.py), 그 뒤의 상태로 이벤트 씬의 조건을 맞춘다
(app/world/scenes.py, #669).
"""

from dataclasses import dataclass, field, replace

from app.assets.schemas import CharacterDocument
from app.world.affection import GIVE_ITEM, REACH_PLACE, USE_ITEM, apply_affection
from app.world.items import apply_give, apply_use, check_held, give_text, use_text
from app.world.moves import apply_move, check_move, move_text
from app.world.scenes import Event, Revealed, mark_shown, reveal
from app.world.schemas import Action, GiveAction, MoveAction, UseAction
from app.world.state import WorldState
from app.world.waiting import apply_wait, wait_text


@dataclass(frozen=True)
class Performed:
    """
    행동한 결과. 바뀐 상태와, 행동 말의 글(사람에게 보이고 모델에도 간다).
    revealed 는 이번 행동으로 나온 이벤트 씬들이다(첫 것이 답에 붙는다).
    """

    state: WorldState
    text: str
    revealed: Revealed = field(default_factory=Revealed)


def event_of(action: Action) -> Event | None:
    """이벤트 씬의 조건이 보는, 이번 행동이 일으킨 일. 이동은 장소에 간 것, 건네기는 물건을 건넨 것이다."""
    if isinstance(action, MoveAction):
        return Event(REACH_PLACE, action.place)
    if isinstance(action, GiveAction):
        return Event(GIVE_ITEM, action.item)
    return None


def with_event_scenes(document: CharacterDocument, performed: Performed, action: Action) -> Performed:
    """행동한 뒤의 상태로 이벤트 씬의 조건을 맞추고, 나온 것을 상태에 적는다."""
    revealed = reveal(document, performed.state, event_of(action))
    return replace(performed, state=mark_shown(performed.state, revealed), revealed=revealed)


def perform_move(document: CharacterDocument, state: WorldState, action: MoveAction) -> Performed:
    """지도에서 이동한다."""
    minutes = check_move(document, state, action.place)
    moved = apply_affection(document, apply_move(state, action.place, minutes), REACH_PLACE, action.place)
    return Performed(moved, move_text(document, action.place, minutes))


def perform_use(document: CharacterDocument, state: WorldState, action: UseAction) -> Performed:
    """물건을 쓴다."""
    item = check_held(document, state, action.item)
    return Performed(apply_affection(document, apply_use(state, item), USE_ITEM, item.id), use_text(item))


def perform_give(document: CharacterDocument, state: WorldState, action: GiveAction) -> Performed:
    """물건을 건넨다. 덧붙이는 한마디는 행동 말이 아니라 그 뒤의 사람의 말이다(부르는 쪽이 붙인다)."""
    item = check_held(document, state, action.item)
    return Performed(apply_affection(document, apply_give(state, item), GIVE_ITEM, item.id), give_text(item))


def perform_wait(state: WorldState, start_hour: int) -> Performed:
    """시간을 보낸다. 다음 시간대가 된다. 호감도의 규칙은 걸지 않는다(시간 보내기의 행동 종류가 없다)."""
    waited = apply_wait(state, start_hour)
    return Performed(waited, wait_text(waited, start_hour))


def perform_kind(document: CharacterDocument, state: WorldState, action: Action, start_hour: int) -> Performed:
    """행동 하나의 결과(이벤트 씬은 맞추기 전). kind 로 가른다."""
    if isinstance(action, MoveAction):
        return perform_move(document, state, action)
    if isinstance(action, UseAction):
        return perform_use(document, state, action)
    if isinstance(action, GiveAction):
        return perform_give(document, state, action)
    return perform_wait(state, start_hour)


def perform(document: CharacterDocument, state: WorldState, action: Action, start_hour: int) -> Performed:
    """행동 하나. start_hour 는 대화의 시작 시각(몇 시)이다. 그 뒤에 이벤트 씬의 조건을 맞춘다."""
    return with_event_scenes(document, perform_kind(document, state, action, start_hour), action)
