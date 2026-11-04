"""snapshots

Revision ID: 5ef001f39ec2
Revises: 3b2bac77b5aa
Create Date: 2026-11-04 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '5ef001f39ec2'
down_revision: str | Sequence[str] | None = '3b2bac77b5aa'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 장면 그림 한 장의 기록과 청구(#983, app/snapshots/models.py). 한 대화에 그리는 중인 것은 하나다(부분 유일 색인).
# 되돌리면 기록이 사라진다(asset 에 맡긴 그림은 남는다)


def upgrade() -> None:
    op.create_table(
        'snapshots',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=True),
        sa.Column('message_id', sa.Uuid(), nullable=True),
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
            "billing_status IN ('pending', 'held', 'declined', 'capture_due', 'release_due', 'captured', 'released', "
            "'failed')",
            name=op.f('ck_snapshots_billing_status_allowed'),
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('ready', 'failed')", name=op.f('ck_snapshots_outcome_allowed')
        ),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_snapshots_conversation_id_conversations'),
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['message_id'], ['messages.id'], name=op.f('fk_snapshots_message_id_messages'), ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_snapshots')),
        sa.UniqueConstraint('reference', name=op.f('uq_snapshots_reference')),
    )
    op.create_index(
        'ix_snapshots_billing_status_next_settle_at', 'snapshots', ['billing_status', 'next_settle_at'], unique=False
    )
    op.create_index('ix_snapshots_conversation_created', 'snapshots', ['conversation_id', 'created_at'], unique=False)
    op.create_index(
        'uq_snapshots_one_drawing',
        'snapshots',
        ['conversation_id'],
        unique=True,
        postgresql_where=sa.text('outcome IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_snapshots_one_drawing', table_name='snapshots', postgresql_where=sa.text('outcome IS NULL'))
    op.drop_index('ix_snapshots_conversation_created', table_name='snapshots')
    op.drop_index('ix_snapshots_billing_status_next_settle_at', table_name='snapshots')
    op.drop_table('snapshots')
