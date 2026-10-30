"""world hiding

Revision ID: c8e0a2b4d6f8
Revises: b6d8f0a2c4e5
Create Date: 2026-10-31 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c8e0a2b4d6f8'
down_revision: str | Sequence[str] | None = 'b6d8f0a2c4e5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 운영자가 세계관을 숨긴다(캐릭터의 숨김과 같다, app/operators/).
#   - worlds.hidden_at: 숨긴 시각. 있던 세계관은 숨기지 않은 것이다
#   - operator_actions 의 조치 종류에 world_hide, world_unhide 를 더한다. 표는 덧붙이기만 하므로 행은 그대로다
# 되돌리면 세계관의 숨김이 풀린다. 세계관을 숨긴 기록이 있으면 조치 종류의 검사를 되돌리지 못한다(기록은 지우지 않는다)
CHECK = 'ck_operator_actions_action_allowed'
BEFORE = "action IN ('character_hide', 'character_unhide', 'reports_dismiss')"
AFTER = "action IN ('character_hide', 'character_unhide', 'reports_dismiss', 'world_hide', 'world_unhide')"


def upgrade() -> None:
    op.add_column('worlds', sa.Column('hidden_at', sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint(op.f(CHECK), 'operator_actions', type_='check')
    op.create_check_constraint(op.f(CHECK), 'operator_actions', AFTER)


def downgrade() -> None:
    op.drop_constraint(op.f(CHECK), 'operator_actions', type_='check')
    op.create_check_constraint(op.f(CHECK), 'operator_actions', BEFORE)
    op.drop_column('worlds', 'hidden_at')
