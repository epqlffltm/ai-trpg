"""npc fights

Revision ID: 7c3e5a9f1d48
Revises: 6e1a9c4d2b75
Create Date: 2026-10-19 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '7c3e5a9f1d48'
down_revision: str | Sequence[str] | None = '6e1a9c4d2b75'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NPC 가 처음 싸운 라운드(#457). 싸우기 전인 인물에게서는 훔치기가 쉽다.
    # 이미 맞은 적이 있는 인물도 비워 둔다. 그때는 싸움을 세지 않았다
    op.add_column('table_npcs', sa.Column('fought_round', sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f('ck_table_npcs_fought_round_positive'), 'table_npcs', 'fought_round IS NULL OR fought_round >= 1'
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_table_npcs_fought_round_positive'), 'table_npcs', type_='check')
    op.drop_column('table_npcs', 'fought_round')
