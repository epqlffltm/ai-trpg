# chat-server/app/world/schemas.py

"""
장소와 소지품의 응답과 입력의 모양.
장소와 물건의 이름, 그림은 대화의 판(character.document)에 있다. 여기는 id 만 싣는다.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.world.models import KEY_MAX_LENGTH
from app.world.state import WorldState

# 건넬 때 덧붙이는 한마디의 길이의 상한(글자). 사람의 말과 같다(app/turns/schemas.py 의 CONTENT_MAX_CHARS)
WORDS_MAX_CHARS = 4000
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
    outfit 은 상대가 입은 옷들이다.
    """

    place: str | None
    minutes: int
    inventory: list[HoldingOut]
    visited: list[str]
    # 상대가 입은 옷들(사용자가 건넨 옷)의 물건 id
    outfit: list[str]


class MoveAction(BaseModel):
    """지도에서 장소를 골라 간다. 지금 있는 곳과 길로 바로 이어진 곳만 된다."""

    model_config = ConfigDict(extra='forbid')

    kind: Literal['move']
    place: Key


class UseAction(BaseModel):
    """소지품의 물건을 쓴다. 쓰면 없어지는 물건이면 하나 준다."""

    model_config = ConfigDict(extra='forbid')

    kind: Literal['use']
    item: Key


class GiveAction(BaseModel):
    """
    소지품의 물건을 상대에게 건넨다. 하나 줄고, 옷이면 상대가 입는다.
    words 는 덧붙이는 한마디다(없으면 행동만). 행동과 말을 한 턴에 붙이고 반응을 한 번 받는다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal['give']
    item: Key
    words: Annotated[str, StringConstraints(min_length=1, max_length=WORDS_MAX_CHARS, pattern=r'\S')] | None = None


# 행동 하나. kind 로 가른다
Action = Annotated[MoveAction | UseAction | GiveAction, Field(discriminator='kind')]


def state_out(state: WorldState) -> StateOut:
    """상태를 응답의 모양으로."""
    return StateOut(
        place=state.place,
        minutes=state.minutes,
        inventory=[HoldingOut(item=holding.item, count=holding.count) for holding in state.inventory],
        visited=list(state.visited),
        outfit=list(state.outfit),
    )
