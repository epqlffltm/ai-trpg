# chat-server/app/world/state.py

"""
대화의 상태(장소, 흐른 시간, 소지품, 가 본 곳, 상대의 차림, 호감도, 나온 이벤트 씬). DB 를 모르는 순수한 값과 함수다.

상태는 바뀐 말에만 적는다(message_states). 나머지 말은 부모의 상태를 따른다.
그래서 지금의 상태는 가지의 끝에서 거슬러 올라가 처음 만나는 상태다(state_at).
하나도 없으면 캐릭터의 판에 적힌 시작 상태다(initial_state). 판을 복사해 두었으니 언제 읽어도 같다.
대화는 트리라서, 다시 생성하거나 앞 가지로 돌아가면 그 가지의 상태가 된다. 되돌리기가 가지를 바꾸는 것으로 끝난다.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from app.assets.schemas import CharacterDocument


@dataclass(frozen=True)
class Holding:
    """가진 물건 하나(item 은 판의 물건 id)와 그 수."""

    item: str
    count: int


@dataclass(frozen=True)
class WorldState:
    """
    한 시점의 상태. place 는 지금 있는 장소의 id(지도가 없는 캐릭터면 None),
    minutes 는 대화를 시작한 뒤 흐른 시간(분), visited 는 가 본 장소들(처음 간 차례)이다.
    outfit 은 상대가 입은 옷들(사용자가 건넨 옷, 건넨 차례)의 물건 id 다.
    affection 은 호감도(0~100, 판에 호감도가 없으면 None), fired 는 이 가지에서 걸린 "처음 한 번만" 규칙의 id 다.
    shown 은 이 가지에서 나온 이벤트 씬의 id 다(나온 차례, #669).
    received 는 이 가지에서 상대에게 받은 물건의 id 다(받은 차례, #676). 같은 물건은 한 가지에서 한 번만 받는다.
    """

    place: str | None
    minutes: int
    inventory: tuple[Holding, ...]
    visited: tuple[str, ...]
    outfit: tuple[str, ...] = ()
    affection: int | None = None
    fired: tuple[str, ...] = ()
    shown: tuple[str, ...] = ()
    received: tuple[str, ...] = ()


def initial_state(document: CharacterDocument) -> WorldState:
    """판에 적힌 시작 상태. 처음 있는 장소, 시작 소지품, 호감도의 시작 값이다. 처음 있는 장소는 가 본 곳이다."""
    place = document.start_place
    holdings = tuple(Holding(start.item, start.count) for start in document.start_items)
    affection = document.affection.start if document.affection is not None else None
    return WorldState(
        place=place, minutes=0, inventory=holdings, visited=(place,) if place else (), affection=affection
    )


def filled(document: CharacterDocument, state: WorldState) -> WorldState:
    """
    판에 호감도가 있는데 상태에 없으면(호감도를 더하기 전에 적힌 상태다) 시작 값으로 채운다.
    판을 대화마다 복사해 두었으니 "판에 호감도가 있다"는 바뀌지 않는다.
    """
    if document.affection is not None and state.affection is None:
        return replace(state, affection=document.affection.start)
    return state


def state_at(path_ids: Sequence[uuid.UUID], states: Mapping[uuid.UUID, WorldState], initial: WorldState) -> WorldState:
    """path_ids(첫 말부터 끝까지)의 끝에서 거슬러 올라가 처음 만나는 상태. 없으면 initial."""
    for message_id in reversed(path_ids):
        if message_id in states:
            return states[message_id]
    return initial
