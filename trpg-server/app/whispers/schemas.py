# trpg-server/app/whispers/schemas.py

"""
쪽지 API 가 받는 입력과 내보내는 응답의 모양.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.whispers.models import WHISPER_MAX_LENGTH

# 쪽지의 글. 공백이 아닌 글자가 하나는 있어야 한다. 앞뒤 공백은 떼지 않는다(채팅과 같다)
WhisperContent = Annotated[str, StringConstraints(pattern=r'\S', max_length=WHISPER_MAX_LENGTH)]


class WhisperCreate(BaseModel):
    """쪽지를 보낼 때 받는 값. 보낸 사람은 토큰에서 읽는다. 입력으로 받지 않는다."""

    model_config = ConfigDict(extra='forbid')

    # 받는 사람. 같은 테이블에 앉아 있어야 한다. 자기 자신은 안 된다
    recipient_id: uuid.UUID
    content: WhisperContent
    # GM(AI)에게도 보여 줄까. 보여 주면 그 라운드의 서술에 숨은 정보로 들어간다.
    # 서술은 모두에게 나가므로 모델이 내용을 흘릴 수 있다. 화면이 보낼 때 알린다
    gm_visible: bool = False


class WhisperOut(BaseModel):
    """
    자기 쪽지함의 쪽지 한 장.

    보낸 것과 받은 것이 한 줄로 섞여 온다. sender_id 가 자기면 보낸 것이다.
    """

    # 자기 쪽지함 안에서의 순서. 다음에 읽을 때 "이 번호 뒤"를 달라고 한다
    sequence: int
    sender_id: uuid.UUID
    recipient_id: uuid.UUID
    # 보낼 때의 캐릭터 이름. 캐릭터를 정하기 전이면 None 이다
    sender_character_name: str | None
    recipient_character_name: str | None
    content: str
    # GM 에게도 보였는가. 받은 사람도 안다
    gm_visible: bool
    # 어느 라운드의 서술에 들어가는가(gm_visible 일 때 뜻이 있다)
    round: int
    created_at: datetime


class WhisperPage(BaseModel):
    """쪽지함의 한 쪽."""

    items: list[WhisperOut]
    # 자기 쪽지함의 마지막 번호. items 의 마지막 번호가 이보다 작으면 더 읽을 것이 있다
    last_sequence: int = Field(ge=0)
