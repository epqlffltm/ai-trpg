# game-server/app/assets/schemas.py

"""
세계관 API 가 받는 입력과 내보내는 응답의 모양.

입력의 검증은 여기서 한다. 길이 제한은 모델의 상수를 그대로 쓴다. DB 의 CHECK 와 숫자가 어긋나지 않는다.
DB 의 CHECK 는 마지막 방어선이고, 사용자에게 "어느 칸이 왜 틀렸는지" 알려 주는 것은 이쪽이다.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.assets.models import (
    DESCRIPTION_MAX_LENGTH,
    TITLE_MAX_LENGTH,
    WORLD_GM_NOTES_MAX_LENGTH,
    WORLD_SETTING_MAX_LENGTH,
    Rating,
    Visibility,
)

# 제목은 앞뒤 공백을 떼고, 그러고도 한 글자 이상이어야 한다. 공백만 있는 제목을 막는다
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX_LENGTH)]
Description = Annotated[str, StringConstraints(max_length=DESCRIPTION_MAX_LENGTH)]
Setting = Annotated[str, StringConstraints(max_length=WORLD_SETTING_MAX_LENGTH)]
GmNotes = Annotated[str, StringConstraints(max_length=WORLD_GM_NOTES_MAX_LENGTH)]


class WorldCreate(BaseModel):
    """세계관을 만들 때 받는 값. 제목만 필수다."""

    # 모르는 칸이 오면 거부한다. owner_id 나 visibility 를 끼워 보내도 조용히 무시되지 않고 오류가 난다
    model_config = ConfigDict(extra='forbid')

    title: Title
    description: Description = ''
    rating: Rating = Rating.ALL
    setting: Setting = ''
    gm_notes: GmNotes = ''


class WorldUpdate(BaseModel):
    """
    세계관을 고칠 때 받는 값. 보낸 칸만 바꾼다.

    None 은 "보내지 않았다"는 뜻이다. 글을 비우려면 빈 문자열을 보낸다.
    """

    model_config = ConfigDict(extra='forbid')

    title: Title | None = None
    description: Description | None = None
    rating: Rating | None = None
    setting: Setting | None = None
    gm_notes: GmNotes | None = None


class WorldSummary(BaseModel):
    """목록에 싣는 값. 긴 글(setting, gm_notes)은 싣지 않는다."""

    id: uuid.UUID
    title: str
    description: str
    rating: Rating
    visibility: Visibility
    created_at: datetime
    updated_at: datetime


class WorldDetail(WorldSummary):
    """
    만든 사람이 자기 세계관을 볼 때의 값. gm_notes 까지 싣는다.

    만든 사람이 아닌 사람에게 보여 주는 기능을 만들 때는 gm_notes 가 없는 응답을 따로 만든다.
    이 모양을 그대로 쓰면 비밀이 새어 나간다.
    """

    setting: str
    gm_notes: str


class WorldPage(BaseModel):
    """세계관 목록의 한 쪽."""

    items: list[WorldSummary]
    # 조건에 맞는 전체 개수. 다음 쪽이 있는지 알 수 있다
    total: int = Field(ge=0)
