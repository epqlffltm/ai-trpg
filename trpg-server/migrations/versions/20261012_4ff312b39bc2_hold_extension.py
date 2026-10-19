"""hold extension

Revision ID: 4ff312b39bc2
Revises: 21a7d0baeff8
Create Date: 2026-10-12 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '4ff312b39bc2'
down_revision: str | Sequence[str] | None = '21a7d0baeff8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 정리 작업이 부를 청구의 조건. 걸린(held) 청구를 더했다. 연장할 때가 되면 부른다.
# 모델(app/billing/models.py 의 DUE_CONDITION)과 같은 글자다
OLD_DUE_CONDITION = "status IN ('pending', 'capture_due', 'release_due')"
NEW_DUE_CONDITION = "status IN ('pending', 'held', 'capture_due', 'release_due')"


def upgrade() -> None:
    # 만료되어 돌려받은 홀드를 새 이름표로 다시 건 횟수. 있던 청구는 0 이다(다시 건 적이 없다)
    op.add_column('narration_charges', sa.Column('renewals', sa.Integer(), server_default='0', nullable=False))
    # 있던 걸린 청구의 next_attempt_at 은 지나간 시각이다. 올린 뒤 첫 바퀴에 모두 연장된다.
    # 결제 서버의 만료(#149)가 생긴 뒤 아직 연장한 적이 없는 홀드들이다
    op.drop_index('ix_narration_charges_due', table_name='narration_charges', postgresql_where=OLD_DUE_CONDITION)
    op.create_index(
        'ix_narration_charges_due',
        'narration_charges',
        ['next_attempt_at'],
        unique=False,
        postgresql_where=NEW_DUE_CONDITION,
    )


def downgrade() -> None:
    op.drop_index('ix_narration_charges_due', table_name='narration_charges', postgresql_where=NEW_DUE_CONDITION)
    op.create_index(
        'ix_narration_charges_due',
        'narration_charges',
        ['next_attempt_at'],
        unique=False,
        postgresql_where=OLD_DUE_CONDITION,
    )
    op.drop_column('narration_charges', 'renewals')
