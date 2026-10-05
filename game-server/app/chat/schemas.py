# game-server/app/chat/schemas.py

"""
채팅 API 가 받는 입력과 내보내는 응답의 모양.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.chat.models import MESSAGE_MAX_LENGTH

# 채팅의 글. 공백이 아닌 글자가 하나는 있어야 한다. 앞뒤 공백은 떼지 않는다
MessageContent = Annotated[str, StringConstraints(pattern=r'\S', max_length=MESSAGE_MAX_LENGTH)]


class MessageCreate(BaseModel):
    """채팅을 쓸 때 받는 값. 누가 썼는지는 토큰에서 읽는다. 입력으로 받지 않는다."""

    model_config = ConfigDict(extra='forbid')

    content: MessageContent


class MessageOut(BaseModel):
    """앉은 사람이 채팅 한 줄을 볼 때의 값."""

    # 테이블 안에서의 순서. 다음에 읽을 때 "이 번호 뒤"를 달라고 한다
    sequence: int
    user_id: uuid.UUID
    # 쓸 때의 캐릭터 이름. 캐릭터를 정하기 전에 쓴 글이면 None 이다.
    # 쓴 사람이 아직 앉아 있으면, 화면은 user_id 로 자리를 찾아 지금의 이름을 보여 준다
    character_name: str | None
    content: str
    created_at: datetime


class MessagePage(BaseModel):
    """채팅 목록의 한 쪽."""

    items: list[MessageOut]
    # 이 테이블에 적힌 마지막 채팅의 번호. items 의 마지막 번호가 이보다 작으면 더 읽을 것이 있다
    last_sequence: int = Field(ge=0)
