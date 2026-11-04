"""snapshots owner index

Revision ID: 991229f25424
Revises: 4bc44f779f85
Create Date: 2026-11-05 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = '991229f25424'
down_revision: str | Sequence[str] | None = '4bc44f779f85'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 내 장면 그림들(갤러리, GET /snapshots)을 주인과 만든 시각으로 찾는다(app/snapshots/models.py).
# 되돌려도 기록은 남는다(색인만 지운다)


def upgrade() -> None:
    op.create_index('ix_snapshots_owner_created', 'snapshots', ['owner_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_snapshots_owner_created', table_name='snapshots')
