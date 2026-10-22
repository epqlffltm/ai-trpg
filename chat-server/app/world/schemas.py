# chat-server/app/world/schemas.py

"""
장소와 소지품의 응답과 입력의 모양.
장소와 물건의 이름, 그림은 대화의 판(character.document)에 있다. 여기는 id 만 싣는다.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.world.models import KEY_MAX_LENGTH
from app.world.state import WorldState

# 장소와 물건의 id. asset 서버의 판과 같은 모양이다
Key = Annotated[str, StringConstraints(min_length=1, max_length=KEY_MAX_LENGTH, pattern=r'^[A-Za-z0-9_-]+$')]


class HoldingOut(BaseModel):
    """가진 물건 하나와 그 수."""

    item: str
    count: int


class StateOut(BaseModel):
    """
    지금 보고 있는 가지의 끝의 상태. place 는 지금 있는 장소(지도가 없으면 null),
    minutes 는 대화를 시작한 뒤 흐른 시간(분), visited 는 가 본 장소들이다(화면이 안개를 그린다).
    """

    place: str | None
    minutes: int
    inventory: list[HoldingOut]
    visited: list[str]


class MoveAction(BaseModel):
    """지도에서 장소를 골라 간다. 지금 있는 곳과 길로 바로 이어진 곳만 된다."""

    model_config = ConfigDict(extra='forbid')

    kind: Literal['move']
    place: Key


def state_out(state: WorldState) -> StateOut:
    """상태를 응답의 모양으로."""
    return StateOut(
        place=state.place,
        minutes=state.minutes,
        inventory=[HoldingOut(item=holding.item, count=holding.count) for holding in state.inventory],
        visited=list(state.visited),
    )
