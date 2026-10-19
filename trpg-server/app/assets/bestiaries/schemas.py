# trpg-server/app/assets/bestiaries/schemas.py

"""
몬스터 도감 API 가 받는 입력과 내보내는 응답의 모양.

도감 자신은 공통 칸(제목, 메모)만 가진다. 그래서 공통 모양(app/assets/schemas.py)을 그대로 쓴다.
여기에는 몬스터의 모양이 있다.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.assets.bestiaries.models import MONSTER_CONTENT_MAX_LENGTH, MONSTER_NAME_MAX_LENGTH, MonsterKind
from app.assets.schemas import AssetCreate, AssetUpdate


class BestiaryCreate(AssetCreate):
    """도감을 만들 때 받는 값. 공통 칸뿐이다. 몬스터는 만든 뒤에 하나씩 더한다."""


class BestiaryUpdate(AssetUpdate):
    """도감을 고칠 때 받는 값. 공통 칸뿐이다."""


# 이름은 앞뒤 공백을 떼고, 그러고도 한 글자 이상이어야 한다
MonsterName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MONSTER_NAME_MAX_LENGTH)]
MonsterContent = Annotated[str, StringConstraints(max_length=MONSTER_CONTENT_MAX_LENGTH)]


class MonsterCreate(BaseModel):
    """몬스터를 만들 때 받는 값. 이름만 필수다. 타입을 적지 않으면 기타다."""

    model_config = ConfigDict(extra='forbid')

    name: MonsterName
    content: MonsterContent = ''
    kind: MonsterKind = MonsterKind.OTHER
    # 네임드 몹인가. 판 전체에서 한 마리만 둔다
    unique: bool = False


class MonsterUpdate(BaseModel):
    """
    몬스터를 고칠 때 받는 값. 보낸 칸만 바꾼다.

    None 은 "보내지 않았다"는 뜻이다. 내용을 비우려면 빈 문자열을 보낸다.
    """

    model_config = ConfigDict(extra='forbid')

    name: MonsterName | None = None
    content: MonsterContent | None = None
    kind: MonsterKind | None = None
    unique: bool | None = None


class MonsterDetail(BaseModel):
    """몬스터 하나의 값."""

    id: uuid.UUID
    name: str
    content: str
    kind: MonsterKind
    unique: bool
    created_at: datetime
    updated_at: datetime
