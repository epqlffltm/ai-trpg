# story-server/app/turns/schemas.py

"""
말을 보내는 API 가 받는 입력과, SSE 로 흘려보내는 메시지의 모양.

    event: turn     data: {"generation_id": ..., "user_message": {...}, "cast": ["mina", "jun"]}
                                                                맨 처음. 답할 사람의 말과 장면의 인물
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
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.conversations.schemas import MessageOut

# 사람의 말 하나의 길이의 상한(글자). 넘으면 422 다. 입력의 가격 단계(i0)가 약속하는 양을 한 말이 다 쓰지 않게 한다
CONTENT_MAX_CHARS = 4000


class MessageCreate(BaseModel):
    """보내는 말."""

    model_config = ConfigDict(extra='forbid')

    content: Annotated[str, Field(min_length=1, max_length=CONTENT_MAX_CHARS, pattern=r'\S')]


class TurnEvent(BaseModel):
    """turn 메시지. cast 는 이 답을 쓰는 장면의 인물이다."""

    generation_id: uuid.UUID
    user_message: MessageOut
    cast: list[str]


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
