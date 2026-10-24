# story-server/app/conversations/models.py

"""
세션의 테이블(docs/architecture/story.md 의 "데이터의 모양"). 스키마는 story 다.

  - worlds: asset 서버에서 가져온 세계관의 판의 사본. 사람마다, 판마다 하나다. 그 사람의 세션들이 함께 쓴다
  - conversations: 세션 하나. 세계관을 새로 시작할 때마다 하나다. 지난 세션은 목록에 남는다

asset 서버의 행을 가리키는 칸(source_id)에는 외래 키를 걸지 않는다. 다른 서버의 DB 다.
사본은 가져온 뒤 바뀌지 않는다. 원본이 다시 게시돼도 그 세션은 처음의 판으로 돈다. 새 판은 새 세션에서 쓴다.
말(messages)과 말에 붙는 상태, 세션의 끝(엔딩, 후일담)은 그것을 쓰는 조각에서 더한다(만드는 순서 2~5).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.ratings import Rating


def one_of(column: str, values: type[enum.StrEnum]) -> str:
    """칸의 값이 그 목록 안에 있다는 CHECK 의 글자."""
    allowed = ', '.join(f"'{value}'" for value in values)
    return f'{column} IN ({allowed})'


class ImportedWorld(Base):
    """
    asset 서버에서 가져온 세계관의 판 하나의 사본. 사람마다, 판마다 하나다.

    같은 판으로 세션을 여러 번 시작해도 사본은 하나다(owner_id, source_id, version 이 고유).
    사람마다 두는 것은 탈퇴할 때 그 사람의 것만 지우기 위해서다(chat 의 캐릭터 사본과 같다).
    판의 문서는 받은 그대로(JSON) 둔다. 세션마다 엔진이 문서 전체를 읽으므로 표로 쪼개지 않는다.
    """

    __tablename__ = 'worlds'
    __table_args__ = (
        UniqueConstraint('owner_id', 'source_id', 'version', name='uq_worlds_owner_source_version'),
        CheckConstraint(one_of('rating', Rating), name='rating_allowed'),
        CheckConstraint('version >= 1', name='version_positive'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # 가져온 사람. 인증 서버의 public_id 다
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    # asset 서버의 세계관 id 와 판의 번호
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)
    # 목록에서 문서를 열지 않고 보이고 거르려고 문서에서 꺼내 둔다
    name: Mapped[str] = mapped_column(Text)
    rating: Mapped[str] = mapped_column(String(10))
    # 판의 문서(app/assets/schemas.py 의 WorldDocument, 받은 칸 전부). 받은 그대로다
    document: Mapped[dict] = mapped_column(JSONB)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Conversation(Base):
    """
    세션 하나. 세계관의 판 하나를 가리킨다. 제목은 세계관의 이름이다.

    지우는 길은 아직 없다(지난 세션은 목록에 남는다). 지우기를 더할 때 chat 처럼 지운 시각의 칸을 함께 더한다.
    """

    __tablename__ = 'conversations'
    __table_args__ = (
        # 내 세션 목록: 최근의 것부터
        Index('ix_conversations_owner_updated', 'owner_id', 'updated_at'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    # 세션이 쓰는 판의 사본. 세션이 남아 있는 동안 사본을 지우지 못한다
    world_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('worlds.id', ondelete='RESTRICT'), index=True)
    title: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
