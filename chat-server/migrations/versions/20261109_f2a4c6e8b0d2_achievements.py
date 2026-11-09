"""achievements

Revision ID: f2a4c6e8b0d2
Revises: d3e5f7a9b1c2
Create Date: 2026-11-09 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f2a4c6e8b0d2'
down_revision: str | Sequence[str] | None = 'd3e5f7a9b1c2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 받은 업적과 대화한 사람(app/achievements/, docs/architecture/achievements.md 의 "chat").
# 사람마다, 캐릭터마다, 업적마다 처음 받은 것. 받은 때의 이름, 받는 법, 그림을 함께 적는다. 받은 대화는 지워지면 비운다.
# 대화한 사람은 달성률의 분모다. 이 표가 생긴 뒤부터 센다.
# 연 이벤트 씬의 표를 만든 리비전(d3e5f7a9b1c2)에서 갈라진다. 다른 마이그레이션의 차례에 기대지 않는다(upgrade heads)


def upgrade() -> None:
    op.create_table(
        'achievement_records',
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('character_source', sa.Uuid(), nullable=False),
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
        sa.PrimaryKeyConstraint('owner_id', 'character_source', 'achievement_id', name=op.f('pk_achievement_records')),
    )
    op.create_index(
        op.f('ix_achievement_records_character_source'), 'achievement_records', ['character_source'], unique=False
    )
    op.create_table(
        'character_players',
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('character_source', sa.Uuid(), nullable=False),
        sa.Column('first_played_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('owner_id', 'character_source', name=op.f('pk_character_players')),
    )
    op.create_index(
        op.f('ix_character_players_character_source'), 'character_players', ['character_source'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_character_players_character_source'), table_name='character_players')
    op.drop_table('character_players')
    op.drop_index(op.f('ix_achievement_records_character_source'), table_name='achievement_records')
    op.drop_table('achievement_records')
