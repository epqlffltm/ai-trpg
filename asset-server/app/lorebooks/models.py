# asset-server/app/lorebooks/models.py

"""
로어북의 초안과 판(lorebooks, lorebook_versions, #672).

로어북은 설정을 항목 단위로 쪼개 담은 사전이다. 캐릭터와 따로 된 자산이라 여러 캐릭터가 함께 가리킨다
(나중에 story 와 TRPG 도. docs/architecture/asset-server.md).
캐릭터를 게시할 때 가리킨 로어북의 마지막 판을 캐릭터의 판에 복사한다.
그래서 chat 은 캐릭터의 판 하나만 가져온다.

항목은 로어북에 딸린 목록이라 초안의 문서(entries)로 둔다(캐릭터의 장소와 물건과 같다).
항목의 모양과 종류는 TRPG 의 로어북 항목과 맞춘다. 나중에 TRPG 의 로어북을 옮길 때 그대로 담긴다.
지금은 만든 사람만 쓴다(공개 범위와 등급이 없다). 남과 나누는 것은 story 와 TRPG 를 옮길 때 더한다.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 로어북의 이름과 설명의 길이
LOREBOOK_NAME_MAX_LENGTH = 50
LOREBOOK_DESCRIPTION_MAX_LENGTH = 1000
# 로어북 하나의 항목 수. 캐릭터의 판에 복사되므로 묶어 둔다
LOREBOOK_MAX_ENTRIES = 200
# 항목의 이름, 내용, 키워드의 수와 길이. TRPG 의 로어북 항목과 같다(trpg-server 의 app/assets/models.py)
LORE_ENTRY_NAME_MAX_LENGTH = 100
LORE_ENTRY_CONTENT_MAX_LENGTH = 500
LORE_ENTRY_MAX_KEYWORDS = 5
LORE_KEYWORD_MAX_LENGTH = 30
# 판의 메모의 길이
LOREBOOK_VERSION_NOTE_MAX_LENGTH = 500


class LoreKind(enum.StrEnum):
    """
    로어북 항목의 종류. TRPG 의 LoreKind 와 같은 값이다. chat 은 지금 종류로 다르게 다루지 않는다(보이기만 한다).
    인물, 장소, 물건, 세력, 종족, 전설(사실인지 애매한 이야기), 사건, 기타.
    """

    PERSON = 'person'
    PLACE = 'place'
    ITEM = 'item'
    FACTION = 'faction'
    SPECIES = 'species'
    LEGEND = 'legend'
    EVENT = 'event'
    OTHER = 'other'


class Lorebook(Base):
    """
    로어북의 초안. 만든 사람만 보고 고친다.
    latest_version 과 published_at 은 마지막으로 게시한 판의 번호와 시각이다. 게시한 적이 없으면 비어 있다.
    """

    __tablename__ = 'lorebooks'
    __table_args__ = (CheckConstraint('(latest_version IS NULL) = (published_at IS NULL)', name='published_paired'),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # 만든 사람. 인증 서버의 public_id 다. "내 로어북들"을 찾는 일이 많아 색인을 건다
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    name: Mapped[str] = mapped_column(String(LOREBOOK_NAME_MAX_LENGTH))
    # 만든 사람이 보는 설명. 모델에는 가지 않는다
    description: Mapped[str] = mapped_column(Text, default='', server_default='')
    # 항목들 [{"id", "name", "kind", "keywords", "content", "constant"}]. 모양은 schemas.LoreEntry 가 정한다
    entries: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default='[]')

    latest_version: Mapped[int | None] = mapped_column(Integer, default=None)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LorebookVersion(Base):
    """로어북의 판 하나. 게시할 때의 초안을 굳힌 문서(document)다. 바뀌지 않는다. 로어북을 지우면 함께 지워진다."""

    __tablename__ = 'lorebook_versions'
    __table_args__ = (
        UniqueConstraint('lorebook_id', 'number', name='uq_lorebook_versions_number'),
        CheckConstraint('number >= 1', name='number_positive'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    lorebook_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('lorebooks.id', ondelete='CASCADE'), index=True)
    number: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(LOREBOOK_VERSION_NOTE_MAX_LENGTH), default='', server_default='')
    # 굳힌 문서. 모양은 app/lorebooks/documents.py 의 LorebookDocument 다
    document: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
