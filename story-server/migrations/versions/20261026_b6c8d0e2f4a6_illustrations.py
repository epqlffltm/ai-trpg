"""illustrations

Revision ID: b6c8d0e2f4a6
Revises: a5b7c9d1e3f5
Create Date: 2026-10-26 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b6c8d0e2f4a6'
down_revision: str | Sequence[str] | None = 'a5b7c9d1e3f5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 연 일러스트(app/records/). 사람마다, 세계관마다, 장면(종류와 id)마다 처음 연 것.
# 연 때의 그림과 그 장면이 부르는 인물들을 함께 적는다. 연 세션은 지워지면 비운다


def upgrade() -> None:
    op.create_table(
        'illustration_unlocks',
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('world_source', sa.Uuid(), nullable=False),
        sa.Column('scene_kind', sa.String(length=10), nullable=False),
        sa.Column('scene_id', sa.String(length=40), nullable=False),
        sa.Column('image_id', sa.Uuid(), nullable=False),
        sa.Column('cast', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_illustration_unlocks_conversation_id_conversations'),
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint(
            'owner_id', 'world_source', 'scene_kind', 'scene_id', name=op.f('pk_illustration_unlocks')
        ),
    )


def downgrade() -> None:
    op.drop_table('illustration_unlocks')
