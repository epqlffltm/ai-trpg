"""shortcuts

Revision ID: 3697d9b8eb2a
Revises: d9f1b3c5e7a9
Create Date: 2026-11-03 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '3697d9b8eb2a'
down_revision: str | Sequence[str] | None = 'd9f1b3c5e7a9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 단축어(#981). 캐릭터와 세계관의 초안에 제작자 단축어(목록), 사람마다 내 단축어(줄 하나에 목록).
# 있던 초안은 빈 목록이다. 되돌리면 적은 단축어가 사라진다(게시한 판의 문서에 굳은 것은 남는다)


def upgrade() -> None:
    for table in ('characters', 'worlds'):
        op.add_column(
            table,
            sa.Column('shortcuts', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        )
    op.create_table(
        'user_shortcuts',
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('items', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('owner_id', name=op.f('pk_user_shortcuts')),
    )


def downgrade() -> None:
    op.drop_table('user_shortcuts')
    for table in ('worlds', 'characters'):
        op.drop_column(table, 'shortcuts')
