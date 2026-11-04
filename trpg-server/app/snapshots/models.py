# trpg-server/app/snapshots/models.py

"""
장면 그림 한 장의 기록과 그 청구(table_snapshots, #983). chat·story 서버의 snapshots 와 같은 모양이다.

  - 누른 사람(owner_id)이 낸다. 테이블에 앉은 사람 누구나 누를 수 있다
  - 한 테이블에 그리는 중인 것(outcome 이 비어 있다)은 하나다(부분 유일 색인). 두 요청이 함께 와도 하나만 들어간다
  - 그림은 asset 서버의 그림이다(image_id). 주인은 누른 사람이고, 이 서버가 맡긴 그림이라 이 서버가 서명만으로 받아
    테이블의 사람들에게 대신 내준다(app/asset_server/client.py 의 fetch_kept)
  - 청구의 상태는 한 방향으로만 간다(SnapshotBilling). 서술 값의 청구(narration_charges)와 따로 둔다.
    값을 내는 사람, 이름표, 확정하는 때가 다르다
  - 테이블의 행이 지워지면 그 칸만 비운다. 기록은 결제 서버의 원장과 맞추려고 남는다
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.assets.models import one_of
from app.core.database import Base


class SnapshotBilling(enum.StrEnum):
    """한 장의 청구가 어디까지 왔나. 걸기 전 → 걸림(또는 거절) → 확정·반환할 차례 → 확정·반환(또는 실패)."""

    PENDING = 'pending'
    HELD = 'held'
    DECLINED = 'declined'
    CAPTURE_DUE = 'capture_due'
    RELEASE_DUE = 'release_due'
    CAPTURED = 'captured'
    RELEASED = 'released'
    FAILED = 'failed'


# 그리는 도중의 것(서버가 꺼지면 오래 남는다)과 결제 서버에 맡길 차례의 것
OPEN_STATUSES = frozenset({SnapshotBilling.PENDING, SnapshotBilling.HELD})
DUE_STATUSES = frozenset({SnapshotBilling.CAPTURE_DUE, SnapshotBilling.RELEASE_DUE})


class SnapshotOutcome(enum.StrEnum):
    """한 장이 어떻게 끝났나. 비어 있으면 그리는 중이다."""

    READY = 'ready'
    FAILED = 'failed'


class TableSnapshot(Base):
    """테이블의 장면 그림 한 장."""

    __tablename__ = 'table_snapshots'
    __table_args__ = (
        CheckConstraint(one_of('billing_status', SnapshotBilling), name='billing_status_allowed'),
        CheckConstraint(f'outcome IS NULL OR {one_of("outcome", SnapshotOutcome)}', name='outcome_allowed'),
        CheckConstraint('round_number >= 1', name='round_number_positive'),
        # 한 테이블에 그리는 중인 것은 하나다
        Index('uq_table_snapshots_one_drawing', 'table_id', unique=True, postgresql_where=text('outcome IS NULL')),
        # 테이블의 그림들을 만든 차례로 찾는다
        Index('ix_table_snapshots_table_created', 'table_id', 'created_at'),
        # 정리 작업이 맡길 차례가 된 청구를 찾는다
        Index('ix_table_snapshots_billing_status_next_settle_at', 'billing_status', 'next_settle_at'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('game_tables.id', ondelete='SET NULL'))
    # 그린 장면인 라운드의 번호. 라운드를 되돌리면 같은 번호가 새 장면을 갖는다. 그림은 그릴 때의 장면이다
    round_number: Mapped[int] = mapped_column(Integer)
    # 크레딧을 내는 사람(인증 서버의 public_id). 그림의 주인이기도 하다
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    # 그림 모델의 이름(gemini-nano-banana-2.1 같은 것)
    model: Mapped[str] = mapped_column(String(80))

    # 결제 서버의 홀드의 이름표(game:img:<id>)와 가격표 이름(narration.image.<이름표>)
    reference: Mapped[str] = mapped_column(String(80), unique=True)
    price_code: Mapped[str] = mapped_column(String(120))
    billing_status: Mapped[str] = mapped_column(String(20), default=SnapshotBilling.PENDING)
    settle_attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_settle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    outcome: Mapped[str | None] = mapped_column(String(20), default=None)
    # 왜 실패했나(refused, no_image, credit_short …). 공급자와 결제 서버의 답의 본문은 싣지 않는다
    error_code: Mapped[str | None] = mapped_column(String(60), default=None)
    # asset 서버의 그림 id. 다 그리고 맡긴 뒤에 채운다
    image_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    input_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    output_tokens: Mapped[int | None] = mapped_column(Integer, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
