"""quest due at

Revision ID: 64ab661f4014
Revises: be6f94759fa1
Create Date: 2026-10-15 23:19:01.328853

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '64ab661f4014'
down_revision: str | Sequence[str] | None = 'be6f94759fa1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 테이블의 퀘스트에 기한이 끝나는 게임 안의 시각(분)을 적는 칸을 더한다.
# 채우지 않는다. 지금까지의 판에는 퀘스트의 기한이 없다(판 형식 27 부터 있다). 모두 기한 없이 그대로다


def upgrade() -> None:
    op.add_column('table_quests', sa.Column('due_at', sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f('ck_table_quests_due_at_not_negative'), 'table_quests', 'due_at IS NULL OR due_at >= 0'
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_table_quests_due_at_not_negative'), 'table_quests', type_='check')
    op.drop_column('table_quests', 'due_at')
