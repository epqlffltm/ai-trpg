"""happening traps

Revision ID: b5d7f9a1c3e6
Revises: f9b1d3e5a7c0
Create Date: 2026-11-19 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b5d7f9a1c3e6'
down_revision: str | Sequence[str] | None = 'f9b1d3e5a7c0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 사건이 옮긴 쪽이 밟은 덫(#806 ②-c). 일어난 사건의 줄에 밟은 덫들(traps)을 둔다. 있던 줄은 밟은 것이 없다.
# 되돌리면 그 칸을 지운다. 이미 적힌 trap_sprung 이벤트와 바뀐 상태는 그대로다. 서술은 그 칸 없이 사건을 그린다


def upgrade() -> None:
    op.add_column(
        'table_happenings',
        sa.Column(
            'traps',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('table_happenings', 'traps')
