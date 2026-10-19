"""open charges index

Revision ID: 21a7d0baeff8
Revises: b3d5f7a9c1e2
Create Date: 2026-10-12 10:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = '21a7d0baeff8'
down_revision: str | Sequence[str] | None = 'b3d5f7a9c1e2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 끝나지 않은 청구의 조건. 모델(app/billing/models.py 의 OPEN_CONDITION)과 같은 글자다
OPEN_CONDITION = "status IN ('pending', 'held', 'short')"


def upgrade() -> None:
    # 정리 작업이 5초마다 끝난 테이블의 끝나지 않은 청구를 찾는다.
    # 이 색인이 없으면 바퀴마다 지금까지의 청구를 모두 훑는다. 끝나지 않은 청구만 담으므로 테이블이 쌓여도 작다
    op.create_index(
        'ix_narration_charges_open', 'narration_charges', ['round_id'], unique=False, postgresql_where=OPEN_CONDITION
    )


def downgrade() -> None:
    op.drop_index('ix_narration_charges_open', table_name='narration_charges', postgresql_where=OPEN_CONDITION)
