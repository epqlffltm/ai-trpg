"""start_counts

캐릭터와 세계관에 대화와 세션을 시작한 모든 수(#985). 받아 온 수(work_starts)를 옮겨 적는다.
처음에는 이미 받아 둔 것에서 채운다.

Revision ID: d2f63000fa2d
Revises: be46a6face87
Create Date: 2026-12-01 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd2f63000fa2d'
down_revision: str | Sequence[str] | None = 'be46a6face87'
branch_labels: str | Sequence[str] | None = None
# 받아 둔 수의 표(work_starts)를 읽으므로 그 표를 만드는 마이그레이션 뒤에 돈다
depends_on: str | Sequence[str] | None = '3df1379bd8f4'


def upgrade() -> None:
    op.add_column('characters', sa.Column('start_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('worlds', sa.Column('start_count', sa.Integer(), server_default='0', nullable=False))
    # 이미 받아 둔 수가 있으면 옮겨 적는다. 다음 받기를 기다리지 않는다
    op.execute(
        'UPDATE characters SET start_count = ws.total FROM work_starts ws '
        "WHERE ws.kind = 'character' AND ws.work_id = characters.id"
    )
    op.execute(
        'UPDATE worlds SET start_count = ws.total FROM work_starts ws '
        "WHERE ws.kind = 'world' AND ws.work_id = worlds.id"
    )


def downgrade() -> None:
    op.drop_column('worlds', 'start_count')
    op.drop_column('characters', 'start_count')
