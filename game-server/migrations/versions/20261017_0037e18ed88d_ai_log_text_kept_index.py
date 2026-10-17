"""ai log text kept index

Revision ID: 0037e18ed88d
Revises: a57c4e086d8d
Create Date: 2026-10-17 03:22:44.555472

"""

from collections.abc import Sequence

from alembic import op

revision: str = '0037e18ed88d'
down_revision: str | Sequence[str] | None = 'a57c4e086d8d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# AI 호출의 기록에서 원문이 남은 줄만 담는 색인을 더한다(#274, app/ai/retention.py).
# 보관 기간이 지난 원문을 오래된 것부터 찾는다. 비운 줄은 색인에서 빠진다.
# 조건의 글자는 모델(app/ai/models.py 의 TEXT_KEPT)과 같다. 앱의 코드를 가져오지 않고 여기에 적어 둔다
TEXT_KEPT = 'text IS NOT NULL'


def upgrade() -> None:
    op.create_index(
        'ix_ai_invocations_text_kept', 'ai_invocations', ['created_at'], unique=False, postgresql_where=TEXT_KEPT
    )


def downgrade() -> None:
    op.drop_index('ix_ai_invocations_text_kept', table_name='ai_invocations', postgresql_where=TEXT_KEPT)
