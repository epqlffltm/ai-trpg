# game-server/app/rounds/schemas.py

"""
라운드 API 가 받는 입력과 내보내는 응답의 모양.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.rounds.models import DECLARATION_MAX_LENGTH

# 선언의 글. 공백이 아닌 글자가 하나는 있어야 한다. 앞뒤 공백은 떼지 않는다
DeclarationContent = Annotated[str, StringConstraints(pattern=r'\S', max_length=DECLARATION_MAX_LENGTH)]


class DeclarationUpdate(BaseModel):
    """선언을 낼 때 받는 값. 다시 내면 앞의 것을 통째로 바꾼다."""

    model_config = ConfigDict(extra='forbid')

    content: DeclarationContent


class DeclarationOut(BaseModel):
    """선언 하나."""

    user_id: uuid.UUID
    character_name: str
    # 선언의 글. 라운드가 열려 있는 동안에는 자기 것만 보인다. 남의 것은 None 이다.
    # 라운드가 닫히면 모두의 것이 보인다
    content: str | None


class RoundOut(BaseModel):
    """앉은 사람이 라운드를 볼 때의 값."""

    number: int
    # 이 라운드를 여는 장면. GM 의 서술이다
    scene: str
    is_open: bool
    declarations: list[DeclarationOut]
    # 아직 선언을 내지 않은 사람들. 닫힌 라운드에서는 비어 있다
    waiting_for: list[uuid.UUID]
    created_at: datetime
    closed_at: datetime | None


class RoundPage(BaseModel):
    """라운드 목록의 한 쪽."""

    items: list[RoundOut]
    # 전체 개수. 다음 쪽이 있는지 알 수 있다
    total: int = Field(ge=0)
