# game-server/app/assets/schemas.py

"""
모든 자산이 함께 쓰는 입력과 응답의 모양. 종류별 모양은 이것을 물려받아 자기 칸만 더한다.

입력의 검증은 여기서 한다. 길이 제한은 모델의 상수를 그대로 쓴다. DB 의 CHECK 와 숫자가 어긋나지 않는다.
DB 의 CHECK 는 마지막 방어선이고, 사용자에게 "어느 칸이 왜 틀렸는지" 알려 주는 것은 이쪽이다.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.assets.models import DESCRIPTION_MAX_LENGTH, TITLE_MAX_LENGTH, Rating, Visibility

# 제목은 앞뒤 공백을 떼고, 그러고도 한 글자 이상이어야 한다. 공백만 있는 제목을 막는다
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX_LENGTH)]
Description = Annotated[str, StringConstraints(max_length=DESCRIPTION_MAX_LENGTH)]


class AssetCreate(BaseModel):
    """자산을 만들 때 받는 공통 값. 제목만 필수다."""

    # 모르는 칸이 오면 거부한다. owner_id 나 visibility 를 끼워 보내도 조용히 무시되지 않고 오류가 난다
    model_config = ConfigDict(extra='forbid')

    title: Title
    description: Description = ''
    rating: Rating = Rating.ALL


class AssetUpdate(BaseModel):
    """
    자산을 고칠 때 받는 공통 값. 보낸 칸만 바꾼다.

    None 은 "보내지 않았다"는 뜻이다. 글을 비우려면 빈 문자열을 보낸다.
    """

    model_config = ConfigDict(extra='forbid')

    title: Title | None = None
    description: Description | None = None
    rating: Rating | None = None


class AssetSummary(BaseModel):
    """목록에 싣는 값. 어느 종류든 같다. 종류별 긴 글은 싣지 않는다."""

    id: uuid.UUID
    title: str
    description: str
    rating: Rating
    visibility: Visibility
    created_at: datetime
    updated_at: datetime


class AssetPage(BaseModel):
    """자산 목록의 한 쪽."""

    items: list[AssetSummary]
    # 조건에 맞는 전체 개수. 다음 쪽이 있는지 알 수 있다
    total: int = Field(ge=0)
