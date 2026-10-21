# trpg-server/app/references/models.py

"""
참고 자료의 테이블 둘.

  - reference_entries: 자료의 한 줄. 자료(source)와 key 로 찾는다. 다시 넣어도 id 는 그대로다.
  - reference_embeddings: 한 줄을 한 임베딩 모델로 바꾼 벡터. 줄 하나, 모델 하나마다 한 줄이다.

로어북의 벡터(lore_embeddings)와 따로 둔다. 로어북의 벡터는 게시한 판마다 만들고 판이 굳어 있어 다시 만들 일이 없다.
참고 자료는 판과 상관없이 하나뿐이고, 운영자가 자료를 다시 넣으면 바뀐 줄의 벡터만 다시 만든다.
로어북 항목과 같은 테이블에 넣으면 주인과 판이 없는 줄이 섞이고, 로어북과 도감이 asset 서버로 옮겨 갈 때 함께 딸려 간다.

벡터의 길이를 칸에 정해 두지 않는다(로어북의 벡터와 같은 까닭). 자료 하나가 천 줄 안쪽이라 색인 없이 모두 견준다.
위키백과처럼 큰 자료를 넣을 때 모델별로 길이를 정한 색인(HNSW)을 건다.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.assets.models import at_most, one_of
from app.core.database import Base
from app.lore.models import MODEL_NAME_MAX_LENGTH
from app.references.records import (
    REFERENCE_ALIAS_MAX_LENGTH,
    REFERENCE_CONTENT_MAX_LENGTH,
    REFERENCE_KEY_MAX_LENGTH,
    REFERENCE_MAX_ALIASES,
    REFERENCE_NAME_MAX_LENGTH,
    ReferenceKind,
    ReferenceSource,
)


class ReferenceEntry(Base):
    """참고 자료의 한 줄. 서술자가 읽는 글(content)과 원본의 수치(data)를 함께 둔다."""

    __tablename__ = 'reference_entries'
    __table_args__ = (
        # 같은 자료에 같은 key 는 하나다. 다시 넣을 때 이것으로 같은 줄을 찾는다. "이 자료의 줄들"을 찾는 색인을 겸한다
        UniqueConstraint('source', 'key'),
        CheckConstraint(one_of('source', ReferenceSource), name='source_allowed'),
        CheckConstraint(one_of('kind', ReferenceKind), name='kind_allowed'),
        CheckConstraint(at_most('content', REFERENCE_CONTENT_MAX_LENGTH), name='content_length'),
        CheckConstraint(f'cardinality(aliases) <= {REFERENCE_MAX_ALIASES}', name='aliases_count'),
        CheckConstraint(at_most('content_ko', REFERENCE_CONTENT_MAX_LENGTH), name='content_ko_length'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 어느 자료인가(ReferenceSource)
    source: Mapped[str] = mapped_column(String(20))

    # 자료 안의 이름(monsters/aboleth). 데이터 파일의 key 다
    key: Mapped[str] = mapped_column(String(REFERENCE_KEY_MAX_LENGTH))

    # 종류(ReferenceKind)
    kind: Mapped[str] = mapped_column(String(20))

    # 원본의 이름
    name: Mapped[str] = mapped_column(String(REFERENCE_NAME_MAX_LENGTH))

    # 장면에서 부를 다른 이름들(한국어 이름 등). 장면에 이 낱말이 나오면 고른다(로어북의 키워드와 같다)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String(REFERENCE_ALIAS_MAX_LENGTH)), default=list)

    # 서술자가 읽는 글. 수치가 없다(app/references/srd.py)
    content: Mapped[str] = mapped_column(Text, default='')

    # 원본의 수치. 서술자에게 가지 않는다
    data: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 한국어로 옮긴 이름과 글. 없으면 빈 글이다. 있으면 서술과 복사가 이것을 쓴다(app/references/translations.py)
    name_ko: Mapped[str] = mapped_column(String(REFERENCE_NAME_MAX_LENGTH), default='', server_default='')
    content_ko: Mapped[str] = mapped_column(Text, default='', server_default='')

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReferenceEmbedding(Base):
    """참고 자료의 한 줄을 한 모델로 바꾼 벡터. 줄의 글이 바뀌면 지우고 다시 만든다(app/references/loading.py)."""

    __tablename__ = 'reference_embeddings'
    __table_args__ = (
        # 같은 모델, 같은 줄의 벡터는 하나다. 두 작업이 함께 만들어도 하나만 들어간다.
        # "이 모델의 벡터들"을 찾는 색인을 겸한다(모델이 앞에 있다)
        UniqueConstraint('model', 'reference_id'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 어느 줄의 벡터인가. 줄을 지우면 벡터도 지운다
    reference_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('reference_entries.id', ondelete='CASCADE'))

    # 벡터를 만든 임베딩 모델의 이름
    model: Mapped[str] = mapped_column(String(MODEL_NAME_MAX_LENGTH))

    # 줄의 이름, 다른 이름, 글을 합친 글의 벡터(app/references/texts.py)
    embedding: Mapped[list[float]] = mapped_column(Vector())

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
