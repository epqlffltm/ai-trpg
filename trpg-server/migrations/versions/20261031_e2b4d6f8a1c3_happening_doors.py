"""happening doors

Revision ID: e2b4d6f8a1c3
Revises: d1a3c5e7f9b2
Create Date: 2026-10-31 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'e2b4d6f8a1c3'
down_revision: str | Sequence[str] | None = 'd1a3c5e7f9b2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 판의 사건이 다룬 길의 문(#281). 잠그고 열고 고친 것을 사건의 줄에 적는다. 그 라운드의 서술이 읽는다


def upgrade() -> None:
    # 있던 사건은 문을 다루지 않았다
    op.add_column(
        'table_happenings',
        sa.Column(
            'doors',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('table_happenings', 'doors')
