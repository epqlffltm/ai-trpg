# game-server/app/memory/models.py

"""
지난 라운드의 벡터(round_memories). 테이블의 라운드 하나, 임베딩 모델 하나마다 한 줄이다.

로어북의 벡터(app/lore/models.py)는 판마다 만든다. 판은 굳어 있어 여러 테이블이 함께 쓴다.
기억은 플레이하면서 생기는 글이라 테이블마다 만든다. 테이블이 지워지면 함께 지워진다.

글은 저장하지 않는다. 라운드(table_rounds)에 이미 있고, 기억의 글은 라운드에서 다시 만든다(app/memory/texts.py).
같은 글을 두 군데 두면 어느 쪽이 맞는지 따져야 한다.

모델의 이름을 함께 적는다. 모델이 다르면 벡터를 견줄 수 없다. 찾을 때는 지금 모델의 줄만 본다.
벡터의 길이를 칸에 정해 두지 않는다(로어북과 같다). 테이블 하나의 라운드는 많아야 수백 개라 색인 없이 다 견준다.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.lore.models import MODEL_NAME_MAX_LENGTH


class RoundMemory(Base):
    """테이블의 지난 라운드 하나를 한 모델로 바꾼 벡터."""

    __tablename__ = 'round_memories'
    __table_args__ = (
        # 같은 테이블, 같은 모델, 같은 라운드의 벡터는 하나다. 두 작업이 함께 만들어도 하나만 들어간다.
        # "이 테이블, 이 모델의 벡터들"을 찾는 색인을 겸한다(테이블과 모델이 앞에 있다)
        UniqueConstraint('table_id', 'model', 'round_number'),
        CheckConstraint('round_number >= 1', name='round_number_positive'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 어느 테이블의 라운드인가
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('game_tables.id', ondelete='CASCADE'))

    # 라운드의 번호. 이 라운드에 한 말과 그 결과(다음 라운드의 장면)를 합친 글의 벡터다
    round_number: Mapped[int] = mapped_column(Integer)

    # 벡터를 만든 임베딩 모델의 이름
    model: Mapped[str] = mapped_column(String(MODEL_NAME_MAX_LENGTH))

    embedding: Mapped[list[float]] = mapped_column(Vector())

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
