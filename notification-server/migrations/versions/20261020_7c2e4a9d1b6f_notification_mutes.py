"""notification mutes

Revision ID: 7c2e4a9d1b6f
Revises: 3f9a1c7e5b2d
Create Date: 2026-10-20 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '7c2e4a9d1b6f'
down_revision: str | Sequence[str] | None = '3f9a1c7e5b2d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 사용자가 끈 알림의 종류(#525). 사람과 종류가 기본 키다. 줄이 있으면 꺼져 있다. 규칙은 app/mutes/service.py 에 있다.
#   - 알림을 넣을 때 (user_id, kind) 로 한 줄을 찾는다. 기본 키의 색인으로 찾으므로 색인을 따로 두지 않는다
#   - 되돌리면 모두의 끈 설정이 지워져 모든 종류가 다시 켜진다


def upgrade() -> None:
    op.create_table(
        'notification_mutes',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('kind', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind ~ '^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*$'", name=op.f('ck_notification_mutes_kind_format')
        ),
        sa.PrimaryKeyConstraint('user_id', 'kind', name=op.f('pk_notification_mutes')),
    )


def downgrade() -> None:
    op.drop_table('notification_mutes')
