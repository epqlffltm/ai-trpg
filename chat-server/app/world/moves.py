# chat-server/app/world/moves.py

"""
지도에서 이동하는 규칙. DB 를 모르는 순수 함수다(check_move, apply_move).

사용자가 지도에서 장소를 고르면 서버가 갈 수 있는지 보고, 되면 상태를 바꾼다. 모델은 바뀐 상태를 받아 반응만 쓴다.
  - 지도가 있어야 한다(지금 있는 장소가 있다)
  - 아는 장소여야 하고, 지금 있는 곳이 아니어야 하고, 길로 바로 이어져야 한다. 길은 양쪽으로 다닌다
  - 가면 길의 시간만큼 흐르고, 처음 간 곳이면 가 본 곳에 더한다
숨은 길과 찾기는 TRPG 의 규칙이라 없다. 가 본 곳만 보이는 안개는 화면이 visited 로 그린다.
"""

import enum
from dataclasses import replace

from app.assets.schemas import CharacterDocument, PlaceDocument
from app.world.state import WorldState


class MoveRefusal(enum.StrEnum):
    """갈 수 없는 까닭. 응답의 code 다."""

    # 지도가 없는 캐릭터다(지금 있는 장소가 없다)
    NO_MAP = 'no_map'
    # 판에 없는 장소다
    PLACE_NOT_FOUND = 'place_not_found'
    # 이미 그곳에 있다
    ALREADY_THERE = 'already_there'
    # 지금 있는 곳과 길로 이어지지 않았다
    NOT_CONNECTED = 'not_connected'


class MoveRefusedError(Exception):
    """갈 수 없다(422). reason 이 까닭이다."""

    def __init__(self, reason: MoveRefusal) -> None:
        super().__init__(reason)
        self.reason = reason


def find_place(document: CharacterDocument, place_id: str) -> PlaceDocument | None:
    """판의 장소 하나. 없으면 None."""
    return next((place for place in document.places if place.id == place_id), None)


def path_minutes(document: CharacterDocument, start: str, end: str) -> int | None:
    """두 장소를 바로 잇는 길의 시간(분). 길이 없으면 None. 길은 양쪽으로 다닌다."""
    for path in document.paths:
        if {path.a, path.b} == {start, end}:
            return path.minutes
    return None


def check_move(document: CharacterDocument, state: WorldState, target: str) -> int:
    """target 으로 갈 수 있으면 걸리는 시간(분). 없으면 MoveRefusedError."""
    if state.place is None:
        raise MoveRefusedError(MoveRefusal.NO_MAP)
    if find_place(document, target) is None:
        raise MoveRefusedError(MoveRefusal.PLACE_NOT_FOUND)
    if target == state.place:
        raise MoveRefusedError(MoveRefusal.ALREADY_THERE)
    minutes = path_minutes(document, state.place, target)
    if minutes is None:
        raise MoveRefusedError(MoveRefusal.NOT_CONNECTED)
    return minutes


def apply_move(state: WorldState, target: str, minutes: int) -> WorldState:
    """target 으로 간 뒤의 상태. 시간이 흐르고, 처음 간 곳이면 가 본 곳에 더한다. 검사는 check_move 가 한다."""
    visited = state.visited if target in state.visited else (*state.visited, target)
    return replace(state, place=target, minutes=state.minutes + minutes, visited=visited)


def move_text(document: CharacterDocument, target: str, minutes: int) -> str:
    """이동한 행동 말의 글. 사람에게도 보이고 모델에도 간다."""
    place = find_place(document, target)
    name = place.name if place is not None else target
    return f'{name}에 갔다. {minutes}분이 걸렸다.' if minutes else f'{name}에 갔다.'
