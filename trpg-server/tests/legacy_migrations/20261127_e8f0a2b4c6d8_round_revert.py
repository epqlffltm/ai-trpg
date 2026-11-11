"""round revert

Revision ID: e8f0a2b4c6d8
Revises: d7e9f1a3b5c7
Create Date: 2026-11-27 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'e8f0a2b4c6d8'
down_revision: str | Sequence[str] | None = 'd7e9f1a3b5c7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 방장이 바로 앞 라운드를 되돌린다(#288).
#   - table_rounds.reverted_at: 되돌린 시각. 되돌린 라운드는 지우지 않고 기록으로 남긴다
#   - 번호의 유일 조건을 되돌리지 않은 라운드에만 건다. 다시 여는 라운드가 되돌린 라운드의 번호를 쓴다
#   - game_tables.revert_count: 되돌린 수. 서술 값의 이름표가 앞서 같은 번호로 지은 것과 겹치지 않게 끝에 붙는다
#   - round_snapshots: 라운드를 닫기 직전의 게임 상태. 테이블마다 마지막 하나다
# 되돌리면(downgrade) 되돌린 라운드를 지운다. 같은 번호가 둘이면 옛 유일 조건을 걸 수 없다.
# 그 라운드의 청구(narration_charges)도 함께 지워진다(CASCADE). 결제 서버의 기록은 그대로다


def upgrade() -> None:
    op.add_column('table_rounds', sa.Column('reverted_at', sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint(op.f('uq_table_rounds_table_id'), 'table_rounds', type_='unique')
    op.create_index(
        'uq_table_rounds_number',
        'table_rounds',
        ['table_id', 'number'],
        unique=True,
        postgresql_where=sa.text('reverted_at IS NULL'),
    )
    op.add_column('game_tables', sa.Column('revert_count', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.create_table(
        'round_snapshots',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('round_id', sa.Uuid(), nullable=False),
        sa.Column('state', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('taken_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['round_id'], ['table_rounds.id'], name=op.f('fk_round_snapshots_round_id_table_rounds'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_round_snapshots_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('table_id', name=op.f('pk_round_snapshots')),
    )
    op.create_index(op.f('ix_round_snapshots_round_id'), 'round_snapshots', ['round_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_round_snapshots_round_id'), table_name='round_snapshots')
    op.drop_table('round_snapshots')
    op.drop_column('game_tables', 'revert_count')
    op.execute('DELETE FROM table_rounds WHERE reverted_at IS NOT NULL')
    op.drop_index('uq_table_rounds_number', table_name='table_rounds', postgresql_where=sa.text('reverted_at IS NULL'))
    op.create_unique_constraint(op.f('uq_table_rounds_table_id'), 'table_rounds', ['table_id', 'number'])
    op.drop_column('table_rounds', 'reverted_at')
