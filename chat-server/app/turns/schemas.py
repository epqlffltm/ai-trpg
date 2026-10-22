# chat-server/app/turns/schemas.py

"""
말을 보내는 API 가 받는 입력과, SSE 로 흘려보내는 메시지의 모양.

    event: turn    data: {"generation_id": ..., "user_message": {...}, "continues": null}
                                                                         맨 처음. 답할 사람의 말
    event: delta   data: {"text": "..."}                                 모델이 새로 쓴 글의 조각
    event: done    data: {"message": {...}}                              저장한 답(status 는 complete 나 partial)
    event: failed  data: {"code": "timeout"}                             글자 없이 실패했다. 답은 저장하지 않았다
    : heartbeat                                                          15초 조용하면 끼우는 주석

이어서 출력이면 continues 가 이어 쓰는 끊긴 답의 id 다. delta 는 그 말 끝에 붙일 글이고,
done 의 말은 그 말 전체(같은 id, 이어 붙인 본문)다. 이어 쓴 글이 없이 실패하면 그 말은 그대로다.

done 이나 failed 가 마지막이다. 그 전에 끊겨도 서버는 끝까지 돌아 저장한다. 앱은 대화를 다시 읽는다.
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
    """turn 메시지."""

    generation_id: uuid.UUID
    user_message: MessageOut
    # 이어서 출력이면 이어 쓰는 끊긴 답의 id. 아니면 null
    continues: uuid.UUID | None = None


class DeltaEvent(BaseModel):
    """delta 메시지."""

    text: str


class DoneEvent(BaseModel):
    """done 메시지."""

    message: MessageOut


class FailedEvent(BaseModel):
    """failed 메시지. code 는 까닭(timeout, status_429, empty, stopped, cancelled, server_error …)이다."""

    code: str
