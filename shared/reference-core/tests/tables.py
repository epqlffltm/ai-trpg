# shared/reference-core/tests/tables.py

"""
테스트의 참고 자료 표 둘. 서버의 표(app/references/models.py)와 칸의 이름과 제약이 같다.

공용 코드는 표를 꾸러미(ReferenceTables)로 받는다. 서버의 표 대신 이것을 넘겨 쿼리를 본다.
"""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from reference_core.tables import ReferenceTables


class Base(DeclarativeBase):
    """테스트의 표만 담는 바탕."""


class Entry(Base):
    __tablename__ = 'reference_entries'
    __table_args__ = (UniqueConstraint('source', 'key'),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(20))
    key: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String(30)), default=list)
    content: Mapped[str] = mapped_column(Text, default='')
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    name_ko: Mapped[str] = mapped_column(String(100), default='')
    content_ko: Mapped[str] = mapped_column(Text, default='')


class Embedding(Base):
    __tablename__ = 'reference_embeddings'
    __table_args__ = (UniqueConstraint('model', 'reference_id'),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    reference_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('reference_entries.id', ondelete='CASCADE'))
    model: Mapped[str] = mapped_column(String(100))
    embedding: Mapped[list[float]] = mapped_column(Vector())


TABLES = ReferenceTables(entry=Entry, embedding=Embedding)
