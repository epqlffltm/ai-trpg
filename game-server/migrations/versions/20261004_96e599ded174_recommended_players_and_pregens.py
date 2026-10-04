"""recommended players and pregens

Revision ID: 96e599ded174
Revises: 1327a114e5ff
Create Date: 2026-10-04 19:53:34.313026

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '96e599ded174'
down_revision: str | Sequence[str] | None = '1327a114e5ff'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 추천 인원의 범위. 모델(app/assets/models.py, app/listings/models.py)의 CHECK 와 같아야 한다
PLAYERS_RANGE = '1 <= min_players AND min_players <= max_players AND max_players <= 4'


def upgrade() -> None:
    # 추천 인원. 시나리오(초안)와 공개 정보에 같은 칸을 둔다.
    # 이미 있는 행이 있으므로 잠깐 기본값을 두고 만든 뒤 뗀다. 옛 행은 "1~4명"이 된다
    for table in ('scenarios', 'listings'):
        op.add_column(table, sa.Column('min_players', sa.SmallInteger(), server_default='1', nullable=False))
        op.add_column(table, sa.Column('max_players', sa.SmallInteger(), server_default='4', nullable=False))
        op.alter_column(table, 'min_players', server_default=None)
        op.alter_column(table, 'max_players', server_default=None)
        # 자동 생성은 CHECK 를 찾지 못한다
        op.create_check_constraint(op.f(f'ck_{table}_players_range'), table, PLAYERS_RANGE)

    # 프리젠. 옛 시나리오는 프리젠이 없는 것이 된다
    op.add_column(
        'scenarios', sa.Column('pregens', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False)
    )
    op.alter_column('scenarios', 'pregens', server_default=None)
    op.create_check_constraint(op.f('ck_scenarios_pregens_count'), 'scenarios', 'jsonb_array_length(pregens) <= 8')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_scenarios_pregens_count'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'pregens')
    for table in ('listings', 'scenarios'):
        op.drop_constraint(op.f(f'ck_{table}_players_range'), table, type_='check')
        op.drop_column(table, 'max_players')
        op.drop_column(table, 'min_players')
