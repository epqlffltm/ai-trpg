# asset-server/app/lorebooks/schemas.py

"""
로어북의 입력과 응답의 모양(#672).

항목의 id 는 로어북 안에서 고유하다(캐릭터의 장소와 물건의 id 와 같은 모양). 키워드는 항목 안에서 겹치지 않는다.
상시(constant) 항목은 늘 모델에 가고, 나머지는 키워드가 최근 대화에 나올 때 간다.
키워드가 없는 상시가 아닌 항목도 받는다
(뜻으로 찾는 검색을 더하면 쓰인다).
"""

import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.characters.schemas import Key, reject_repeated, reject_repeated_keys
from app.lorebooks.documents import LorebookDocument
from app.lorebooks.models import (
    LORE_ENTRY_CONTENT_MAX_LENGTH,
    LORE_ENTRY_MAX_KEYWORDS,
    LORE_ENTRY_NAME_MAX_LENGTH,
    LORE_KEYWORD_MAX_LENGTH,
    LOREBOOK_DESCRIPTION_MAX_LENGTH,
    LOREBOOK_MAX_ENTRIES,
    LOREBOOK_NAME_MAX_LENGTH,
    LOREBOOK_VERSION_NOTE_MAX_LENGTH,
    LoreKind,
)

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=LOREBOOK_NAME_MAX_LENGTH)]
Description = Annotated[str, StringConstraints(max_length=LOREBOOK_DESCRIPTION_MAX_LENGTH)]
Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=LORE_KEYWORD_MAX_LENGTH)]
Keywords = Annotated[list[Keyword], Field(max_length=LORE_ENTRY_MAX_KEYWORDS), AfterValidator(reject_repeated)]


class LoreEntry(BaseModel):
    """항목 하나. 이름과 내용은 모델에 간다. constant 면 늘 간다."""

    model_config = ConfigDict(extra='forbid')

    id: Key
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=LORE_ENTRY_NAME_MAX_LENGTH)]
    kind: LoreKind = LoreKind.OTHER
    keywords: Keywords = []
    content: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=LORE_ENTRY_CONTENT_MAX_LENGTH)
    ]
    constant: bool = False


def unique_entries(entries: list[LoreEntry]) -> list[LoreEntry]:
    """같은 id 의 항목이 둘이면 거부한다."""
    reject_repeated_keys([entry.id for entry in entries])
    return entries


Entries = Annotated[list[LoreEntry], Field(max_length=LOREBOOK_MAX_ENTRIES), AfterValidator(unique_entries)]


class LorebookCreate(BaseModel):
    """로어북을 만들 때 받는 값. 이름만 필수다."""

    model_config = ConfigDict(extra='forbid')

    name: Name
    description: Description = ''
    entries: Entries = []

    def values(self) -> dict:
        """DB 에 적을 칸과 값. 항목은 dict 의 목록이다."""
        return {**self.model_dump(), 'entries': [entry.model_dump(mode='json') for entry in self.entries]}


class LorebookUpdate(BaseModel):
    """로어북을 고칠 때 받는 값. 보낸 칸만 바꾼다. 게시한 판은 그대로다. null 은 받지 않는다."""

    model_config = ConfigDict(extra='forbid')

    name: Name | None = None
    description: Description | None = None
    entries: Entries | None = None

    @model_validator(mode='after')
    def no_nulls(self) -> Self:
        """null 을 거부한다. "비우기"인지 "보내지 않음"인지 헷갈린다(비우려면 빈 글이나 빈 목록을 보낸다)."""
        nulls = [name for name in self.model_fields_set if getattr(self, name) is None]
        if nulls:
            raise ValueError(f'null 로 비울 수 없는 칸입니다: {", ".join(sorted(nulls))}')
        return self

    def changes(self) -> dict:
        """보낸 칸과 그 값. 항목은 DB 에 적을 모양(dict 의 목록)으로 바꾼다."""
        changes = {name: getattr(self, name) for name in self.model_fields_set}
        if 'entries' in changes:
            changes['entries'] = [entry.model_dump(mode='json') for entry in self.entries]
        return changes


class LorebookDetail(BaseModel):
    """로어북의 초안 하나. 만든 사람만 본다. latest_version 은 마지막으로 게시한 판의 번호다(없으면 null)."""

    id: uuid.UUID
    name: str
    description: str
    entries: list[LoreEntry]
    latest_version: int | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LorebookSummary(BaseModel):
    """내 로어북 목록의 한 줄. entry_count 는 초안의 항목 수다."""

    id: uuid.UUID
    name: str
    entry_count: int
    latest_version: int | None
    updated_at: datetime


class LorebookPage(BaseModel):
    """목록의 한 쪽과 전체 개수."""

    items: list[LorebookSummary]
    total: int


class LorebookVersionCreate(BaseModel):
    """게시할 때 받는 값. 이번 판에서 무엇이 바뀌었는지 적는다(비워도 된다)."""

    model_config = ConfigDict(extra='forbid')

    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=LOREBOOK_VERSION_NOTE_MAX_LENGTH)] = ''


class LorebookVersionSummary(BaseModel):
    """판의 목록에 싣는 값. 굳힌 문서는 싣지 않는다."""

    id: uuid.UUID
    number: int
    note: str
    created_at: datetime


class LorebookVersionDetail(LorebookVersionSummary):
    """판 하나. 굳힌 문서까지 싣는다."""

    document: LorebookDocument
