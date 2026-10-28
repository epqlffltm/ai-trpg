# story-server/app/lore/models.py

"""
세계관의 로어북 항목의 벡터(lore_embeddings). 판의 사본(worlds) 하나, 임베딩 모델 하나, 항목 하나마다 한 줄이다.

사본마다 만든다(chat 의 표와 같은 모양). 사본은 사람마다, 판마다 하나라 같은 판을 여러 사람이 쓰면
같은 벡터가 여러 번 생긴다. 대신 사본을 지우면(탈퇴) 벡터도 함께 지워진다.
비공개 세계관의 설정에서 만든 벡터가 주인 없이 남지 않는다.

모델의 이름을 함께 적는다. 모델이 다르면 벡터의 공간이 달라 서로 견줄 수 없다. 찾을 때는 지금 모델의 줄만 본다.
벡터의 길이를 칸에 정하지 않는다(모델마다 다르다). 사본 하나의 벡터만 견주므로 색인 없이 다 견준다.
pgvector 는 extensions 스키마에 있다(docker/postgres/init/03-extensions.sql). 연결의 search_path 에 그 스키마를 더한다.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 항목의 id(asset 의 판과 같은 길이)와 모델 이름의 길이
ENTRY_ID_MAX_LENGTH = 40
MODEL_NAME_MAX_LENGTH = 100


class LoreEmbedding(Base):
    """판의 사본에 든 로어북 항목 하나를 한 모델로 바꾼 벡터. 항목은 (로어북의 id, 항목의 id)로 가리킨다."""

    __tablename__ = 'lore_embeddings'
    __table_args__ = (
        # 같은 사본, 같은 모델, 같은 항목의 벡터는 하나다. 두 작업이 함께 만들어도 하나만 들어간다.
        # "이 사본, 이 모델의 벡터들"을 찾는 색인을 겸한다
        UniqueConstraint('world_id', 'model', 'lorebook_id', 'entry_id'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    world_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('worlds.id', ondelete='CASCADE'))
    model: Mapped[str] = mapped_column(String(MODEL_NAME_MAX_LENGTH))
    lorebook_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    entry_id: Mapped[str] = mapped_column(String(ENTRY_ID_MAX_LENGTH))
    embedding: Mapped[list[float]] = mapped_column(Vector())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
