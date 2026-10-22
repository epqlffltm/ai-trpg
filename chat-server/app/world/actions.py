# chat-server/app/world/actions.py

"""
행동 하나를 상태에 적용한다(이동, 쓰기, 건네기). DB 를 모르는 순수 함수다.

할 수 있는지 보고(안 되면 ActionRefusedError), 바뀐 상태와 행동 말의 글을 돌려준다. 저장은 부르는 쪽이 한다.
"""

from dataclasses import dataclass

from app.assets.schemas import CharacterDocument
from app.world.items import apply_give, apply_use, check_held, give_text, use_text
from app.world.moves import apply_move, check_move, move_text
from app.world.schemas import Action, GiveAction, MoveAction, UseAction
from app.world.state import WorldState


@dataclass(frozen=True)
class Performed:
    """행동한 결과. 바뀐 상태와, 행동 말의 글(사람에게 보이고 모델에도 간다)."""

    state: WorldState
    text: str


def perform_move(document: CharacterDocument, state: WorldState, action: MoveAction) -> Performed:
    """지도에서 이동한다."""
    minutes = check_move(document, state, action.place)
    return Performed(apply_move(state, action.place, minutes), move_text(document, action.place, minutes))


def perform_use(document: CharacterDocument, state: WorldState, action: UseAction) -> Performed:
    """물건을 쓴다."""
    item = check_held(document, state, action.item)
    return Performed(apply_use(state, item), use_text(item))


def perform_give(document: CharacterDocument, state: WorldState, action: GiveAction) -> Performed:
    """물건을 건넨다. 덧붙이는 한마디는 행동 말이 아니라 그 뒤의 사람의 말이다(부르는 쪽이 붙인다)."""
    item = check_held(document, state, action.item)
    return Performed(apply_give(state, item), give_text(item))


def perform(document: CharacterDocument, state: WorldState, action: Action) -> Performed:
    """행동 하나. kind 로 가른다."""
    if isinstance(action, MoveAction):
        return perform_move(document, state, action)
    if isinstance(action, UseAction):
        return perform_use(document, state, action)
    return perform_give(document, state, action)
