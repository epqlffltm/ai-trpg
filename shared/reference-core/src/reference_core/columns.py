# shared/reference-core/src/reference_core/columns.py

"""
참고 자료의 표 둘의 칸과 제약. 서버의 ORM 클래스가 이것을 물려받는다(mixin).

  - reference_entries: 자료의 한 줄. 자료(source)와 key 로 찾는다. 다시 넣어도 id 는 그대로다.
  - reference_embeddings: 한 줄을 한 임베딩 모델로 바꾼 벡터. 줄 하나, 모델 하나마다 한 줄이다.

표는 서버마다 제 DB 에 있다(trpg, chat, story. 2026-11-22 유저 결정의 안 A). 모양은 여기 한 곳에 둔다.
서버가 칸을 따로 적으면 같은 데이터 파일을 넣는 표가 서버마다 조금씩 달라진다.
서버의 클래스는 이것과 서버의 Base 를 물려받고 docstring 만 적는다. 마이그레이션은 서버마다 만든다.

제약의 이름(source_allowed 등)은 서버의 Base 의 이름 규칙(server_core 의 NAMING_CONVENTION)에 붙는다.
벡터의 길이를 칸에 정해 두지 않는다. 모델마다 다르다. 자료가 천 줄 안쪽이라 색인 없이 모두 견준다.
"""

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from reference_core.records import (
    REFERENCE_ALIAS_MAX_LENGTH,
    REFERENCE_CONTENT_MAX_LENGTH,
    REFERENCE_KEY_MAX_LENGTH,
    REFERENCE_MAX_ALIASES,
    REFERENCE_NAME_MAX_LENGTH,
    ReferenceKind,
    ReferenceSource,
)

# 표의 이름. 벡터의 표가 줄의 표를 가리킨다
ENTRY_TABLE = 'reference_entries'
EMBEDDING_TABLE = 'reference_embeddings'
# 자료와 종류의 칸의 길이
SOURCE_MAX_LENGTH = 20
KIND_MAX_LENGTH = 20
# 임베딩 모델의 이름의 길이. 서버의 로어북의 벡터(lore_embeddings.model)와 같다
MODEL_NAME_MAX_LENGTH = 100


def one_of(column: str, values: type[enum.StrEnum]) -> str:
    """칸의 값이 그 목록 안에 있다는 CHECK 의 글자."""
    allowed = ', '.join(f"'{value}'" for value in values)
    return f'{column} IN ({allowed})'


def at_most(column: str, max_length: int) -> str:
    """칸의 글자 수가 상한을 넘지 않는다는 CHECK 의 글자."""
    return f'char_length({column}) <= {max_length}'


def entry_constraints() -> tuple:
    """reference_entries 의 제약들. 표마다 새로 만든다(제약 하나는 한 표에만 붙는다)."""
    return (
        # 같은 자료에 같은 key 는 하나다. 다시 넣을 때 이것으로 같은 줄을 찾는다. "이 자료의 줄들"을 찾는 색인을 겸한다
        UniqueConstraint('source', 'key'),
        CheckConstraint(one_of('source', ReferenceSource), name='source_allowed'),
        CheckConstraint(one_of('kind', ReferenceKind), name='kind_allowed'),
        CheckConstraint(at_most('content', REFERENCE_CONTENT_MAX_LENGTH), name='content_length'),
        CheckConstraint(f'cardinality(aliases) <= {REFERENCE_MAX_ALIASES}', name='aliases_count'),
        CheckConstraint(at_most('content_ko', REFERENCE_CONTENT_MAX_LENGTH), name='content_ko_length'),
    )


def embedding_constraints() -> tuple:
    """reference_embeddings 의 제약들."""
    return (
        # 같은 모델, 같은 줄의 벡터는 하나다. 두 작업이 함께 만들어도 하나만 들어간다.
        # "이 모델의 벡터들"을 찾는 색인을 겸한다(모델이 앞에 있다)
        UniqueConstraint('model', 'reference_id'),
    )


class ReferenceEntryColumns:
    """참고 자료의 한 줄의 칸. 서술자가 읽는 글(content)과 원본의 수치(data)를 함께 둔다."""

    __tablename__ = ENTRY_TABLE

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> tuple:
        return entry_constraints()

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 어느 자료인가(ReferenceSource)
    source: Mapped[str] = mapped_column(String(SOURCE_MAX_LENGTH))

    # 자료 안의 이름(monsters/aboleth). 데이터 파일의 key 다
    key: Mapped[str] = mapped_column(String(REFERENCE_KEY_MAX_LENGTH))

    # 종류(ReferenceKind)
    kind: Mapped[str] = mapped_column(String(KIND_MAX_LENGTH))

    # 원본의 이름
    name: Mapped[str] = mapped_column(String(REFERENCE_NAME_MAX_LENGTH))

    # 장면에서 부를 다른 이름들(한국어 이름 등). 글에 이 낱말이 나오면 고른다(로어북의 키워드와 같다)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String(REFERENCE_ALIAS_MAX_LENGTH)), default=list)

    # 서술자가 읽는 글. 수치가 없다(reference_core/srd.py)
    content: Mapped[str] = mapped_column(Text, default='')

    # 원본의 수치와 출처. 서술자에게 가지 않는다
    data: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 한국어로 옮긴 이름과 글. 없으면 빈 글이다. 있으면 서술과 복사가 이것을 쓴다(reference_core/translations.py)
    name_ko: Mapped[str] = mapped_column(String(REFERENCE_NAME_MAX_LENGTH), default='', server_default='')
    content_ko: Mapped[str] = mapped_column(Text, default='', server_default='')

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReferenceEmbeddingColumns:
    """참고 자료의 한 줄을 한 모델로 바꾼 벡터의 칸. 줄의 글이 바뀌면 지우고 다시 만든다(reference_core/loading.py)."""

    __tablename__ = EMBEDDING_TABLE

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> tuple:
        return embedding_constraints()

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 어느 줄의 벡터인가. 줄을 지우면 벡터도 지운다
    reference_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f'{ENTRY_TABLE}.id', ondelete='CASCADE'), index=True)

    # 벡터를 만든 임베딩 모델의 이름
    model: Mapped[str] = mapped_column(String(MODEL_NAME_MAX_LENGTH))

    # 줄의 이름, 다른 이름, 글을 합친 글의 벡터(reference_core/texts.py)
    embedding: Mapped[list[float]] = mapped_column(Vector())

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
