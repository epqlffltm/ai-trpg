# game-server/app/lore/models.py

"""
로어북 항목의 벡터(lore_embeddings). 게시한 판의 항목 하나, 임베딩 모델 하나마다 한 줄이다.

판(scenario_versions)마다 만든다. 판은 굳은 뒤 바뀌지 않으므로 한 번 만들면 그만이고,
그 판으로 연 테이블들이 함께 쓴다. 테이블마다 만들면 같은 벡터가 테이블 수만큼 쌓인다.

모델의 이름을 함께 적는다. 모델이 다르면 벡터의 공간이 달라 서로 견줄 수 없다.
모델을 바꾸면 새 모델의 줄을 새로 만든다(scripts/index_lore.py). 찾을 때는 지금 모델의 줄만 본다.

벡터의 길이를 칸에 정해 두지 않는다(vector, vector(1024) 가 아니다). 모델마다 길이가 다르다.
가까운 것을 찾는 색인(HNSW)은 길이가 정해져야 걸 수 있다. 지금은 판 하나의 항목이 많아야 1,000개라 색인 없이 다 견준다.
큰 자료(SRD, 위키백과)를 넣을 때 모델별로 길이를 정한 색인을 건다.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 모델 이름의 최대 길이. Ollama 의 이름(bge-m3:567m-fp16 등)이 들어가면 된다
MODEL_NAME_MAX_LENGTH = 100


class LoreEmbedding(Base):
    """판의 로어북 항목 하나를 한 모델로 바꾼 벡터."""

    __tablename__ = 'lore_embeddings'
    __table_args__ = (
        # 같은 판, 같은 모델, 같은 항목의 벡터는 하나다. 두 작업이 함께 만들어도 하나만 들어간다.
        # "이 판, 이 모델의 벡터들"을 찾는 색인을 겸한다(판과 모델이 앞에 있다)
        UniqueConstraint('version_id', 'model', 'entry_id'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 어느 판의 항목인가. 판은 지우지 않지만, 지워진다면 벡터도 쓸모가 없다
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('scenario_versions.id', ondelete='CASCADE'))

    # 판의 복사본 안에서 항목의 id(EntrySnapshot.id). 초안의 항목이 지워져도 판의 항목은 남으므로 외래 키를 걸지 않는다
    entry_id: Mapped[uuid.UUID] = mapped_column(Uuid)

    # 벡터를 만든 임베딩 모델의 이름
    model: Mapped[str] = mapped_column(String(MODEL_NAME_MAX_LENGTH))

    # 항목의 이름, 키워드, 내용을 합친 글의 벡터(app/lore/texts.py)
    embedding: Mapped[list[float]] = mapped_column(Vector())

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
