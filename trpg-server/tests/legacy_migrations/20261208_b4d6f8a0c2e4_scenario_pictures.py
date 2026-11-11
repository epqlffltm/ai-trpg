"""scenario pictures

Revision ID: b4d6f8a0c2e4
Revises: e3bad76061cb
Create Date: 2026-12-08 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b4d6f8a0c2e4'
down_revision: str | Sequence[str] | None = 'e3bad76061cb'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 로어 항목마다의 그림(#1163). 시나리오에 {entry_id, image_id} 의 목록을 둔다.
# 장소의 배경, 인물의 그림, 사건의 컷신이다.
# 있던 시나리오는 그림이 없다(빈 목록). 굳힌 판은 고치지 않는다. 판의 pictures 는 비워도 되는 칸이라 없으면 빈 목록이다.
# 되돌리면 그림을 잃는다(그림의 기록은 남는다)


def upgrade() -> None:
    op.add_column(
        'scenarios',
        sa.Column(
            'pictures',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(op.f('ck_scenarios_pictures_count'), 'scenarios', 'jsonb_array_length(pictures) <= 200')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_scenarios_pictures_count'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'pictures')
