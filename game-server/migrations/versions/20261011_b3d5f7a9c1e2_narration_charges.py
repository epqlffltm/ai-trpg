"""narration charges

Revision ID: b3d5f7a9c1e2
Revises: a2c4e6f8b0d1
Create Date: 2026-10-11 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b3d5f7a9c1e2'
down_revision: str | Sequence[str] | None = 'a2c4e6f8b0d1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 정리 작업이 찾는 청구의 조건. 모델(app/billing/models.py 의 DUE_CONDITION)과 같은 글자다
DUE_CONDITION = "status IN ('pending', 'capture_due', 'release_due')"

# 진행 중인 테이블의 닫히지 않은 라운드(열림, 닫는 중)마다 방장에게 청구를 하나 만든다.
# 이 마이그레이션 뒤에 여는 라운드와 같은 모양이다(app/billing/charges.py 의 charge_round, reference_for).
# 그러지 않으면 지금 진행 중인 라운드만 청구 없이 서술된다. 결제 서버를 켜지 않았으면 받지 않고 그대로 지나간다
BACKFILL = """
INSERT INTO narration_charges (id, round_id, payer_id, reference, price_code, status, attempts)
SELECT gen_random_uuid(), r.id, t.host_id,
       'narration:' || r.table_id || ':' || r.number || ':' || t.host_id,
       'narration.standard', 'pending', 0
FROM table_rounds AS r
JOIN game_tables AS t ON t.id = r.table_id
WHERE r.closed_at IS NULL AND t.status = 'playing'
"""


def upgrade() -> None:
    op.create_table(
        'narration_charges',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('round_id', sa.Uuid(), nullable=False),
        sa.Column('payer_id', sa.Uuid(), nullable=False),
        sa.Column('reference', sa.String(length=200), nullable=False),
        sa.Column('price_code', sa.String(length=40), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_error', sa.String(length=40), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'held', 'short', 'capture_due', 'captured', 'release_due', 'released', 'failed')",
            name=op.f('ck_narration_charges_status_allowed'),
        ),
        sa.CheckConstraint('attempts >= 0', name=op.f('ck_narration_charges_attempts_not_negative')),
        sa.ForeignKeyConstraint(
            ['round_id'],
            ['table_rounds.id'],
            name=op.f('fk_narration_charges_round_id_table_rounds'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_narration_charges')),
        sa.UniqueConstraint('reference', name=op.f('uq_narration_charges_reference')),
        sa.UniqueConstraint('round_id', 'payer_id', name=op.f('uq_narration_charges_round_id')),
    )
    op.create_index(
        'ix_narration_charges_due',
        'narration_charges',
        ['next_attempt_at'],
        unique=False,
        postgresql_where=DUE_CONDITION,
    )
    op.execute(BACKFILL)


def downgrade() -> None:
    op.drop_index('ix_narration_charges_due', table_name='narration_charges', postgresql_where=DUE_CONDITION)
    op.drop_table('narration_charges')
