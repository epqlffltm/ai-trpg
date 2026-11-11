"""whispers

Revision ID: fc7641ab2503
Revises: 6f045de249da
Create Date: 2026-10-13 08:15:28.604946

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'fc7641ab2503'
down_revision: str | Sequence[str] | None = '6f045de249da'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 서술자에게 줄 쪽지라는 조건. 모델(app/whispers/models.py 의 GM_CONDITION)과 같은 글자다
GM_CONDITION = 'gm_visible AND owner_id = sender_id'


def upgrade() -> None:
    # 사람마다의 쪽지함(#196). 쪽지 하나가 보낸 사람과 받은 사람의 쪽지함에 한 줄씩 적힌다
    op.create_table(
        'table_whispers',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('sender_id', sa.Uuid(), nullable=False),
        sa.Column('recipient_id', sa.Uuid(), nullable=False),
        sa.Column('sender_character_name', sa.String(length=50), nullable=True),
        sa.Column('recipient_character_name', sa.String(length=50), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('gm_visible', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('char_length(content) <= 500', name=op.f('ck_table_whispers_content_length')),
        sa.CheckConstraint('owner_id IN (sender_id, recipient_id)', name=op.f('ck_table_whispers_owner_is_party')),
        sa.CheckConstraint('round_number >= 1', name=op.f('ck_table_whispers_round_number_positive')),
        sa.CheckConstraint('sender_id <> recipient_id', name=op.f('ck_table_whispers_not_to_self')),
        sa.CheckConstraint('sequence >= 1', name=op.f('ck_table_whispers_sequence_positive')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_whispers_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_table_whispers')),
        sa.UniqueConstraint('table_id', 'owner_id', 'sequence', name=op.f('uq_table_whispers_table_id')),
    )
    op.create_index(
        'ix_table_whispers_gm',
        'table_whispers',
        ['table_id', 'round_number'],
        unique=False,
        postgresql_where=sa.text(GM_CONDITION),
    )
    # 있던 테이블은 알리지 않는다(기본값)
    op.add_column(
        'game_tables', sa.Column('whisper_notice', sa.Boolean(), server_default=sa.text('false'), nullable=False)
    )


def downgrade() -> None:
    op.drop_column('game_tables', 'whisper_notice')
    op.drop_index(
        'ix_table_whispers_gm',
        table_name='table_whispers',
        postgresql_where=sa.text(GM_CONDITION),
    )
    op.drop_table('table_whispers')
