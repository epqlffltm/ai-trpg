# game-server/app/drafts/models.py

"""
장부 초안의 줄. 서술 뒤에 모델이 쓴 초안 중 서버의 검증을 거친 것을 한 줄씩 적는다.

줄 하나가 장부의 변경 하나다(물건 하나를 몇 개, 퀘스트 하나의 상태). 방장은 줄마다 받아들이거나 버린다.
받아들이기 전에는 장부(소지품, 퀘스트)를 바꾸지 않는다. 고치지 않고 상태만 옮긴다.

  - pending: 방장의 결정을 기다린다
  - accepted / rejected: 방장이 받아들였다 / 버렸다
  - expired: 다음 라운드의 초안이 오기 전에 결정하지 않았다. 그사이 장면이 바뀌어 낡은 초안이다

방장만 본다. 숨긴 퀘스트가 드러났다는 초안이 있을 수 있다. 다른 사람은 받아들인 뒤의 장부 이벤트로 안다.
테이블이 지워지면 함께 지워진다.

스키마 이름을 적지 않는다. 연결의 search_path 가 정한다(app/core/database.py).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.assets.models import one_of
from app.core.database import Base


class DraftKind(enum.StrEnum):
    """초안 한 줄이 무엇을 바꾸는가."""

    # 캐릭터 하나가 물건 하나를 몇 개 손에 넣었다
    FOUND_ITEM = 'found_item'
    # 퀘스트 하나의 상태가 바뀌었다
    QUEST_CHANGE = 'quest_change'


class DraftStatus(enum.StrEnum):
    """초안 한 줄의 처지."""

    PENDING = 'pending'
    ACCEPTED = 'accepted'
    REJECTED = 'rejected'
    EXPIRED = 'expired'


class LedgerDraft(Base):
    """장부 초안의 한 줄. 어느 테이블의 몇 라운드의 장면에서 나왔고, 무엇을 바꾸자는가."""

    __tablename__ = 'ledger_drafts'
    __table_args__ = (
        CheckConstraint(one_of('kind', DraftKind), name='kind_allowed'),
        CheckConstraint(one_of('status', DraftStatus), name='status_allowed'),
        CheckConstraint('round_number >= 1', name='round_number_positive'),
        CheckConstraint('position >= 0', name='position_not_negative'),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name='payload_is_object'),
        # 방장이 기다리는 줄을 찾고, 다음 초안이 올 때 기다리던 줄을 만료시킨다.
        # 테이블이 지워질 때 그 테이블의 줄을 찾는 데도 쓴다(앞 칸이 table_id)
        Index('ix_ledger_drafts_table_status', 'table_id', 'status'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 어느 테이블의 초안인가. 테이블의 행이 지워지면 함께 지워진다
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('game_tables.id', ondelete='CASCADE'))
    # 어느 라운드의 장면에서 나왔는가
    round_number: Mapped[int] = mapped_column(Integer)
    # 한 번의 초안 안에서 몇 번째 줄인가. 0 부터. 한 트랜잭션에서 함께 적어 만든 시각이 같으므로 이것으로 늘어놓는다
    position: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))
    # 바꾸자는 내용. found_item 이면 {user_id, character_name, entry_id, name, count},
    # quest_change 면 {entry_id, name, previous, status}. 이름은 초안을 쓸 때의 것이다
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default=DraftStatus.PENDING)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 방장이 결정했거나 만료된 때. 기다리는 동안은 비어 있다
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
