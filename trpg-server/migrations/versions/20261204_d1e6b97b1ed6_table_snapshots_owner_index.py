"""table_snapshots_owner_index

그린 사람의 장면 그림들(갤러리, #983)을 최근에 만든 것부터 찾는 색인.

Revision ID: d1e6b97b1ed6
Revises: 4ae323b6d25d
Create Date: 2026-12-04 10:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = 'd1e6b97b1ed6'
down_revision: str | Sequence[str] | None = '4ae323b6d25d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index('ix_table_snapshots_owner_created', 'table_snapshots', ['owner_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_table_snapshots_owner_created', table_name='table_snapshots')
