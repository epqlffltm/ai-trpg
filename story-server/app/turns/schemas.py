# story-server/app/turns/schemas.py

"""
말을 보내고 행동하는 API 가 받는 입력과, SSE 로 흘려보내는 메시지의 모양.

    event: turn     data: {"generation_id": ..., "user_message": {...}, "cast": ["mina"], "state": {...}}
                                                                맨 처음. 답할 말(행동 말), 장면의 인물, 그 뒤의 상태
    event: segment  data: {"speaker": "mina"}                   새 말 조각. 뒤의 delta 는 이 사람의 것(서술은 null)
    event: delta    data: {"text": "..."}                       지금 조각에 붙는 글
    event: done     data: {"message": {...}}                    저장한 답(status 는 complete 나 partial)
    event: failed   data: {"code": "timeout"}                   답 없이 끝났다. 답은 저장하지 않았다
    : heartbeat                                                 15초 조용하면 끼우는 주석

segment 와 delta 는 화면이 그리면서 이름표를 바꾸는 데 쓴다. 저장한 답(done 의 message.segments)이 기준이다.
장면에 없는 인물의 줄은 흘리지 않고 저장하지도 않는다(app/turns/segments.py).
done 이나 failed 가 마지막이다. 그 전에 끊겨도 서버는 끝까지 돌아 저장한다. 앱은 세션을 다시 읽는다.
"""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.conversations.schemas import MessageOut, StateOut

# 판의 id(장소, 선택지, 인물)의 길이의 상한. asset 서버의 판이 쓰는 id 의 길이와 같다
ID_MAX_CHARS = 40

# 사람의 말 하나의 길이의 상한(글자). 넘으면 422 다. 입력의 가격 단계(i0)가 약속하는 양을 한 말이 다 쓰지 않게 한다
CONTENT_MAX_CHARS = 4000


class MessageCreate(BaseModel):
    """보내는 말."""

    model_config = ConfigDict(extra='forbid')

    content: Annotated[str, Field(min_length=1, max_length=CONTENT_MAX_CHARS, pattern=r'\S')]


class ActionBase(BaseModel):
    """행동의 공통. 모르는 칸은 거부한다."""

    model_config = ConfigDict(extra='forbid')


class MoveAction(ActionBase):
    """지금 장소와 길로 바로 이어진 장소로 옮긴다. 길의 시간만큼 시각이 흐른다."""

    kind: Literal['move']
    place: Annotated[str, Field(min_length=1, max_length=ID_MAX_CHARS)]


class PassTimeAction(ActionBase):
    """다음 시간대로."""

    kind: Literal['pass_time']


class EndDayAction(ActionBase):
    """하루를 마치고 다음 날의 첫 시간대로."""

    kind: Literal['end_day']


class ChooseAction(ActionBase):
    """기다리는 이벤트의 선택지 하나를 고른다."""

    kind: Literal['choose']
    choice: Annotated[str, Field(min_length=1, max_length=ID_MAX_CHARS)]


class ConfessAction(ActionBase):
    """장면에 있는 인물 하나에게 고백한다. 성공과 실패는 엔진이 정한다."""

    kind: Literal['confess']
    cast: Annotated[str, Field(min_length=1, max_length=ID_MAX_CHARS)]


class GiveAction(ActionBase):
    """장면에 있는 인물 하나에게 가진 물건 하나를 건넨다. 호감도가 얼마나 바뀌는지는 엔진이 정한다."""

    kind: Literal['give']
    cast: Annotated[str, Field(min_length=1, max_length=ID_MAX_CHARS)]
    item: Annotated[str, Field(min_length=1, max_length=ID_MAX_CHARS)]


# 행동 하나. kind 로 가른다
ActionCreate = Annotated[
    MoveAction | PassTimeAction | EndDayAction | ChooseAction | ConfessAction | GiveAction,
    Field(discriminator='kind'),
]


class TurnEvent(BaseModel):
    """turn 메시지. cast 는 이 답을 쓰는 장면의 인물, state 는 사람의 말이나 행동 뒤의 상태다."""

    generation_id: uuid.UUID
    user_message: MessageOut
    cast: list[str]
    state: StateOut


class SegmentEvent(BaseModel):
    """segment 메시지. speaker 는 장면의 인물의 id 이고, 서술이면 null 이다."""

    speaker: str | None


class DeltaEvent(BaseModel):
    """delta 메시지."""

    text: str


class DoneEvent(BaseModel):
    """done 메시지."""

    message: MessageOut


class FailedEvent(BaseModel):
    """failed 메시지. code 는 까닭(timeout, status_429, empty, cancelled, server_error …)이다."""

    code: str
