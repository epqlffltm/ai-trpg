# chat-server/app/world/schemas.py

"""
장소와 소지품의 응답과 입력의 모양.
장소와 물건의 이름, 그림은 대화의 판(character.document)에 있다. 여기는 id 만 싣는다.
"""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.assets.schemas import CharacterDocument
from app.world.affection import stage_index
from app.world.backgrounds import background_of
from app.world.clock import TimeOfDay, clock_minutes, read_time
from app.world.models import KEY_MAX_LENGTH
from app.world.sprites import sprite_image
from app.world.state import WorldState

# 숫자와 게이지로 보이는 호감도(asset 서버의 AffectionDisplay.NUMBER)
NUMBER_DISPLAY = 'number'
# 건넬 때 덧붙이는 한마디의 길이의 상한(글자). 사람의 말과 같다(app/turns/schemas.py 의 CONTENT_MAX_CHARS)
WORDS_MAX_CHARS = 4000
# 장소와 물건의 id. asset 서버의 판과 같은 모양이다
Key = Annotated[str, StringConstraints(min_length=1, max_length=KEY_MAX_LENGTH, pattern=r'^[A-Za-z0-9_-]+$')]


class HoldingOut(BaseModel):
    """가진 물건 하나와 그 수."""

    item: str
    count: int


class AffectionOut(BaseModel):
    """
    사용자에 대한 상대의 호감도. 보이는 방식(display)은 제작자가 정한다.
    number 면 value(0~100)가 실리고, stage 면 value 는 null 이다(숫자를 내려보내지 않는다. 화면의 코드로 숨기지 않는다).
    stage 는 지금 단계의 이름, stage_index 는 그 자리(0 부터), stages 는 단계의 수다(게이지를 그린다).
    """

    display: str
    value: int | None
    stage: str
    stage_index: int
    stages: int


class ClockOut(BaseModel):
    """대화 안의 지금 시각. day 는 1 부터(며칠째), hour 는 0~23, minute 는 0~59, time_of_day 는 시간대다."""

    day: int
    hour: int
    minute: int
    time_of_day: TimeOfDay


class StateOut(BaseModel):
    """
    지금 보고 있는 가지의 끝의 상태. place 는 지금 있는 장소(지도가 없으면 null),
    minutes 는 대화를 시작한 뒤 흐른 시간(분), visited 는 가 본 장소들이다(화면이 안개를 그린다).
    outfit 은 상대가 입은 옷들이다.
    """

    place: str | None
    minutes: int
    # 지금 시각(시작 시각 + 흐른 시간)과 시간대
    clock: ClockOut
    # 지금 장소와 시간대의 배경 그림. 시간대의 것이 없으면 장소의 기본 배경, 장소나 그림이 없으면 null
    background: uuid.UUID | None
    # 지금 띄울 캐릭터 그림(배경 위에 겹친다). 상대의 차림에 맞춘 기본 표정의 그림이다. 그림이 없으면 null
    sprite: uuid.UUID | None
    inventory: list[HoldingOut]
    visited: list[str]
    # 상대가 입은 옷들(사용자가 건넨 옷)의 물건 id
    outfit: list[str]
    # 호감도. 판에 호감도가 없으면 null
    affection: AffectionOut | None


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


class WaitAction(BaseModel):
    """시간을 보낸다. 다음 시간대가 시작하는 시각까지 흐른다(밤이면 다음 날 새벽). 지도가 없어도 된다."""

    model_config = ConfigDict(extra='forbid')

    kind: Literal['wait']


# 행동 하나. kind 로 가른다
Action = Annotated[MoveAction | UseAction | GiveAction | WaitAction, Field(discriminator='kind')]


def affection_out(document: CharacterDocument, state: WorldState) -> AffectionOut | None:
    """호감도를 응답의 모양으로. 단계 이름으로 보이는 캐릭터면 숫자를 싣지 않는다."""
    if document.affection is None or state.affection is None:
        return None
    index = stage_index(document.affection, state.affection)
    return AffectionOut(
        display=document.affection.display,
        value=state.affection if document.affection.display == NUMBER_DISPLAY else None,
        stage=document.affection.stages[index].name,
        stage_index=index,
        stages=len(document.affection.stages),
    )


def clock_out(state: WorldState, start_hour: int) -> ClockOut:
    """지금 시각을 응답의 모양으로."""
    time = read_time(clock_minutes(start_hour, state.minutes))
    return ClockOut(day=time.day, hour=time.hour, minute=time.minute, time_of_day=time.time_of_day)


def state_out(state: WorldState, document: CharacterDocument, start_hour: int) -> StateOut:
    """상태를 응답의 모양으로. start_hour 는 대화의 시작 시각(몇 시)이다."""
    clock = clock_out(state, start_hour)
    return StateOut(
        place=state.place,
        minutes=state.minutes,
        clock=clock,
        background=background_of(document, state.place, clock.time_of_day),
        sprite=sprite_image(document, state),
        inventory=[HoldingOut(item=holding.item, count=holding.count) for holding in state.inventory],
        visited=list(state.visited),
        outfit=list(state.outfit),
        affection=affection_out(document, state),
    )
