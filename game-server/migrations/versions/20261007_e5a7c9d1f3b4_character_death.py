"""character death

Revision ID: e5a7c9d1f3b4
Revises: d4f6b8c0e2a3
Create Date: 2026-10-07 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'e5a7c9d1f3b4'
down_revision: str | Sequence[str] | None = 'd4f6b8c0e2a3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 죽음의 굴림에서 센 것은 음수가 아니다
DEATH_SAVES_NOT_NEGATIVE = 'death_successes >= 0 AND death_failures >= 0'
# 죽음의 굴림을 세는 것도, 죽는 것도 쓰러져 있을 때의 일이다
DEATH_ONLY_WHEN_DOWNED = 'hp = 0 OR (death_successes = 0 AND death_failures = 0 AND died_at IS NULL)'


def upgrade() -> None:
    # 칸 넷은 자동 생성이 찾은 그대로다.
    # 있던 시트는 센 것이 0 이고 죽지 않은 것으로 채운다. 이미 쓰러져 있던 캐릭터는 다음 라운드부터 굴린다.
    # 있던 라운드는 죽음의 굴림이 없었던 것으로 채운다
    op.add_column(
        'table_sheets', sa.Column('death_successes', sa.SmallInteger(), server_default=sa.text('0'), nullable=False)
    )
    op.add_column(
        'table_sheets', sa.Column('death_failures', sa.SmallInteger(), server_default=sa.text('0'), nullable=False)
    )
    op.add_column('table_sheets', sa.Column('died_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        'table_rounds',
        sa.Column(
            'death_saves', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'"), nullable=False
        ),
    )

    # 아래는 손으로 적었다. 자동 생성은 CHECK 가 생긴 것을 찾지 못한다
    op.create_check_constraint(
        op.f('ck_table_sheets_death_saves_not_negative'), 'table_sheets', DEATH_SAVES_NOT_NEGATIVE
    )
    op.create_check_constraint(op.f('ck_table_sheets_death_only_when_downed'), 'table_sheets', DEATH_ONLY_WHEN_DOWNED)


def downgrade() -> None:
    # 칸을 지우면 그 칸에 걸린 CHECK 도 함께 사라진다
    op.drop_column('table_rounds', 'death_saves')
    op.drop_column('table_sheets', 'died_at')
    op.drop_column('table_sheets', 'death_failures')
    op.drop_column('table_sheets', 'death_successes')
