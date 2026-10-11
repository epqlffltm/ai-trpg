"""naming

Revision ID: f1a3c5e7b9d0
Revises: e0b2c4d6f8a1
Create Date: 2026-10-11 23:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f1a3c5e7b9d0'
down_revision: str | Sequence[str] | None = 'e0b2c4d6f8a1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 로어북 항목에 지목할 때 맞다고 받는 이름들. 있던 항목은 비운다(항목의 이름 하나가 정답이다)
    op.add_column(
        'lore_entries',
        sa.Column('true_names', sa.ARRAY(sa.String(length=50)), server_default='{}', nullable=False),
    )
    op.create_check_constraint(op.f('ck_lore_entries_true_names_count'), 'lore_entries', 'cardinality(true_names) <= 5')
    # 테이블의 인물을 지목해 진짜 이름을 맞힌 라운드. 있던 인물은 아직 모른다
    op.add_column('table_npcs', sa.Column('named_round', sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f('ck_table_npcs_named_round_positive'), 'table_npcs', 'named_round IS NULL OR named_round >= 1'
    )


def downgrade() -> None:
    op.drop_column('table_npcs', 'named_round')
    op.drop_column('lore_entries', 'true_names')
