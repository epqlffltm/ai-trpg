# game-server/app/assets/lorebooks/schemas.py

"""
로어북 API 가 받는 입력과 내보내는 응답의 모양.

로어북 자신은 공통 칸(제목, 소개글, 등급)만 가진다. 그래서 공통 모양(app/assets/schemas.py)을 그대로 쓴다.
여기에는 항목의 모양이 있다.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.assets.models import (
    LORE_ENTRY_CONTENT_MAX_LENGTH,
    LORE_ENTRY_MAX_KEYWORDS,
    LORE_ENTRY_NAME_MAX_LENGTH,
    LORE_KEYWORD_MAX_LENGTH,
)
from app.assets.schemas import AssetCreate, AssetUpdate


class LorebookCreate(AssetCreate):
    """로어북을 만들 때 받는 값. 공통 칸뿐이다. 항목은 만든 뒤에 하나씩 더한다."""


class LorebookUpdate(AssetUpdate):
    """로어북을 고칠 때 받는 값. 공통 칸뿐이다."""


def reject_duplicates(keywords: list[str]) -> list[str]:
    """같은 키워드가 두 번 있으면 거부한다. 대소문자만 다른 것도 같은 것으로 본다."""
    folded = [keyword.casefold() for keyword in keywords]
    if len(set(folded)) != len(folded):
        raise ValueError('같은 키워드가 두 번 있습니다.')
    return keywords


EntryName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=LORE_ENTRY_NAME_MAX_LENGTH)
]
EntryContent = Annotated[str, StringConstraints(max_length=LORE_ENTRY_CONTENT_MAX_LENGTH)]

# 키워드 하나. 앞뒤 공백을 떼고, 그러고도 한 글자 이상이어야 한다
Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=LORE_KEYWORD_MAX_LENGTH)]
Keywords = Annotated[list[Keyword], Field(max_length=LORE_ENTRY_MAX_KEYWORDS), AfterValidator(reject_duplicates)]


class EntryCreate(BaseModel):
    """항목을 만들 때 받는 값. 이름만 필수다."""

    model_config = ConfigDict(extra='forbid')

    name: EntryName
    keywords: Keywords = []
    content: EntryContent = ''


class EntryUpdate(BaseModel):
    """
    항목을 고칠 때 받는 값. 보낸 칸만 바꾼다.

    None 은 "보내지 않았다"는 뜻이다. 키워드를 전부 없애려면 빈 목록을 보낸다.
    """

    model_config = ConfigDict(extra='forbid')

    name: EntryName | None = None
    keywords: Keywords | None = None
    content: EntryContent | None = None


class EntryDetail(BaseModel):
    """항목 하나의 값."""

    id: uuid.UUID
    name: str
    keywords: list[str]
    content: str
    created_at: datetime
    updated_at: datetime
