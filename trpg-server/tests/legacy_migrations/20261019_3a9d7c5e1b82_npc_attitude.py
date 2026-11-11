"""npc attitude

Revision ID: 3a9d7c5e1b82
Revises: 8b4f2d6e9a71
Create Date: 2026-10-19 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '3a9d7c5e1b82'
down_revision: str | Sequence[str] | None = '8b4f2d6e9a71'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NPC 의 태도(#474). 이미 있는 인물은 중립이다(판 형식 37 보다 옛 판의 인물과 같다)
    op.add_column(
        'table_npcs', sa.Column('attitude', sa.String(length=20), server_default=sa.text("'neutral'"), nullable=False)
    )
    op.create_check_constraint(
        op.f('ck_table_npcs_attitude_allowed'), 'table_npcs', "attitude IN ('friendly', 'neutral', 'hostile')"
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_table_npcs_attitude_allowed'), 'table_npcs', type_='check')
    op.drop_column('table_npcs', 'attitude')
