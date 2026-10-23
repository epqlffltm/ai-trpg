"""event scenes

Revision ID: d3e5f7a9b1c2
Revises: c2d4e6f8a0b1
Create Date: 2026-10-23 01:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd3e5f7a9b1c2'
down_revision: str | Sequence[str] | None = 'c2d4e6f8a0b1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 이벤트 씬(#669).
#   - message_states.shown: 그 가지에서 나온 이벤트 씬의 id. 있던 상태는 나온 것이 없다(빈 목록)
#   - messages.event_scene: 그 말에 답하는 차례에 나온 이벤트 씬의 id
#   - scene_unlocks: 계정마다 연(해금 대상) 이벤트 씬. 대화를 가리키지 않아 대화를 지워도 남는다


def upgrade() -> None:
    op.add_column(
        'message_states',
        sa.Column('shown', postgresql.ARRAY(sa.String(length=40)), server_default='{}', nullable=False),
    )
    op.add_column('messages', sa.Column('event_scene', sa.String(length=40), nullable=True))
    op.create_table(
        'scene_unlocks',
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('character_source', sa.Uuid(), nullable=False),
        sa.Column('scene_id', sa.String(length=40), nullable=False),
        sa.Column('unlocked_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('owner_id', 'character_source', 'scene_id', name=op.f('pk_scene_unlocks')),
    )
    op.create_index('ix_scene_unlocks_owner_unlocked', 'scene_unlocks', ['owner_id', 'unlocked_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_scene_unlocks_owner_unlocked', table_name='scene_unlocks')
    op.drop_table('scene_unlocks')
    op.drop_column('messages', 'event_scene')
    op.drop_column('message_states', 'shown')
