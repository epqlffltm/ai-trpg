"""achievements

Revision ID: c4d6e8f0a2b4
Revises: b6c8d0e2f4a6
Create Date: 2026-11-09 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c4d6e8f0a2b4'
down_revision: str | Sequence[str] | None = 'b6c8d0e2f4a6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 받은 업적과 플레이한 사람(app/records/, docs/architecture/achievements.md 의 "story").
# 사람마다, 세계관마다, 업적마다 처음 받은 것. 받은 때의 이름, 받는 법, 그림을 함께 적는다. 받은 세션은 지워지면 비운다.
# 플레이한 사람은 달성률의 분모다. 이 표가 생긴 뒤부터 센다.
# 연 일러스트의 표를 만든 리비전(b6c8d0e2f4a6)에서 갈라진다. 다른 마이그레이션의 차례에 기대지 않는다(upgrade heads)


def upgrade() -> None:
    op.create_table(
        'achievement_records',
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('world_source', sa.Uuid(), nullable=False),
        sa.Column('achievement_id', sa.String(length=40), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column('image_id', sa.Uuid(), nullable=True),
        sa.Column('conversation_id', sa.Uuid(), nullable=True),
        sa.Column('earned_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_achievement_records_conversation_id_conversations'),
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('owner_id', 'world_source', 'achievement_id', name=op.f('pk_achievement_records')),
    )
    op.create_index(op.f('ix_achievement_records_world_source'), 'achievement_records', ['world_source'], unique=False)
    op.create_table(
        'world_players',
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('world_source', sa.Uuid(), nullable=False),
        sa.Column('first_played_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('owner_id', 'world_source', name=op.f('pk_world_players')),
    )
    op.create_index(op.f('ix_world_players_world_source'), 'world_players', ['world_source'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_world_players_world_source'), table_name='world_players')
    op.drop_table('world_players')
    op.drop_index(op.f('ix_achievement_records_world_source'), table_name='achievement_records')
    op.drop_table('achievement_records')
