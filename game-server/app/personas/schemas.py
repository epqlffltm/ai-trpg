# game-server/app/personas/schemas.py

"""
보관함 API 가 받는 입력과 내보내는 응답의 모양.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.assets.scenarios.schemas import CharacterDescription, CharacterName
from app.engine.ruleset import RULESET_MAX_ABILITIES, Key
from app.engine.sheet import Score

# 보관하는 능력치의 점수. 능력치의 이름표에서 점수로 간다. 여기서는 모양만 본다.
# 어느 규칙에 맞는지는 보지 않는다. 보관함에는 규칙이 없다. 테이블로 가져갈 때 그 테이블의 규칙으로 본다
KeptAbilities = Annotated[dict[Key, Score], Field(max_length=RULESET_MAX_ABILITIES)]


class PersonaWrite(BaseModel):
    """
    보관함에 캐릭터를 만들거나 고칠 때 받는 값. 고칠 때는 보낸 것으로 통째로 바꾼다.

    능력치는 비워도 된다. 글만 보관한 캐릭터는 테이블에서 숫자를 정한다.
    룰북의 제목은 받지 않는다. 테이블에서 저장할 때 서버가 적는다.
    """

    model_config = ConfigDict(extra='forbid')

    name: CharacterName
    description: CharacterDescription = ''
    abilities: KeptAbilities | None = None


class PersonaOut(BaseModel):
    """보관한 캐릭터 하나. 주인에게만 보인다."""

    id: uuid.UUID
    name: str
    description: str
    # 참고로 적어 둔 능력치의 점수. 없으면 None 이다
    abilities: dict[str, int] | None
    # 능력치를 어느 룰북의 규칙으로 만들었는가. 테이블에서 저장했을 때만 있다
    rulebook_title: str | None
    created_at: datetime
    updated_at: datetime


class PersonaPage(BaseModel):
    """보관함 목록의 한 쪽."""

    items: list[PersonaOut]
    # 전체 개수. 다음 쪽이 있는지 알 수 있다
    total: int = Field(ge=0)
