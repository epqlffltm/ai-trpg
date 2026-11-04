"""table_snapshots

테이블의 장면 그림(#983). 테이블에 앉은 사람이 라운드의 장면을 그림 한 장으로 만들고, 누른 사람이 낸다.
한 테이블에 그리는 중인 것은 하나다(부분 유일 색인).

Revision ID: 4ae323b6d25d
Revises: 5cc2a5ea948d
Create Date: 2026-12-03 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '4ae323b6d25d'
down_revision: str | Sequence[str] | None = '5cc2a5ea948d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'table_snapshots',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=True),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('model', sa.String(length=80), nullable=False),
        sa.Column('reference', sa.String(length=80), nullable=False),
        sa.Column('price_code', sa.String(length=120), nullable=False),
        sa.Column('billing_status', sa.String(length=20), nullable=False),
        sa.Column('settle_attempts', sa.Integer(), nullable=False),
        sa.Column('next_settle_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('outcome', sa.String(length=20), nullable=True),
        sa.Column('error_code', sa.String(length=60), nullable=True),
        sa.Column('image_id', sa.Uuid(), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "billing_status IN ('pending', 'held', 'declined', 'capture_due', 'release_due', 'captured', "
            "'released', 'failed')",
            name=op.f('ck_table_snapshots_billing_status_allowed'),
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('ready', 'failed')", name=op.f('ck_table_snapshots_outcome_allowed')
        ),
        sa.CheckConstraint('round_number >= 1', name=op.f('ck_table_snapshots_round_number_positive')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_snapshots_table_id_game_tables'), ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_table_snapshots')),
        sa.UniqueConstraint('reference', name=op.f('uq_table_snapshots_reference')),
    )
    op.create_index(
        'ix_table_snapshots_billing_status_next_settle_at',
        'table_snapshots',
        ['billing_status', 'next_settle_at'],
        unique=False,
    )
    op.create_index('ix_table_snapshots_table_created', 'table_snapshots', ['table_id', 'created_at'], unique=False)
    op.create_index(
        'uq_table_snapshots_one_drawing',
        'table_snapshots',
        ['table_id'],
        unique=True,
        postgresql_where=sa.text('outcome IS NULL'),
    )


def downgrade() -> None:
    op.drop_index(
        'uq_table_snapshots_one_drawing', table_name='table_snapshots', postgresql_where=sa.text('outcome IS NULL')
    )
    op.drop_index('ix_table_snapshots_table_created', table_name='table_snapshots')
    op.drop_index('ix_table_snapshots_billing_status_next_settle_at', table_name='table_snapshots')
    op.drop_table('table_snapshots')
