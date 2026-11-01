"""world chapters

Revision ID: d9f1b3c5e7a9
Revises: c8e0a2b4d6f8
Create Date: 2026-11-01 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd9f1b3c5e7a9'
down_revision: str | Sequence[str] | None = 'c8e0a2b4d6f8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 세계관의 장(판의 형식 6, docs/architecture/chapters.md). 있던 초안은 장이 없다(빈 목록)


def upgrade() -> None:
    op.add_column(
        'worlds',
        sa.Column('chapters', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('worlds', 'chapters')
