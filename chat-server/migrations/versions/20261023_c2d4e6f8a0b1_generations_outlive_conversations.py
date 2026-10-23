"""generations outlive conversations

Revision ID: c2d4e6f8a0b1
Revises: b1c3d5e7f9a0
Create Date: 2026-10-23 00:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c2d4e6f8a0b1'
down_revision: str | Sequence[str] | None = 'b1c3d5e7f9a0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 탈퇴하면 대화를 지운다(#670). 청구 기록(generations)은 남기고 대화와 말을 가리키는 칸만 비운다(2026-10-23 유저 결정).
# 그래서 세 칸을 비울 수 있게 하고, 가리키는 것이 지워지면 비운다(SET NULL). 지금까지는 함께 지웠다(CASCADE)
COLUMNS = (
    ('conversation_id', 'conversations'),
    ('parent_id', 'messages'),
    ('message_id', 'messages'),
)


def replace_foreign_key(column: str, table: str, ondelete: str) -> None:
    """generations 의 그 칸의 외래 키를 같은 이름으로 다시 건다."""
    name = op.f(f'fk_generations_{column}_{table}')
    op.drop_constraint(name, 'generations', type_='foreignkey')
    op.create_foreign_key(name, 'generations', table, [column], ['id'], ondelete=ondelete)


def upgrade() -> None:
    op.alter_column('generations', 'conversation_id', existing_type=sa.Uuid(), nullable=True)
    op.alter_column('generations', 'parent_id', existing_type=sa.Uuid(), nullable=True)
    for column, table in COLUMNS:
        replace_foreign_key(column, table, 'SET NULL')


def downgrade() -> None:
    # 대화를 잃은 기록은 되돌릴 곳이 없다. 다시 비울 수 없게 하기 전에 지운다
    op.execute('DELETE FROM generations WHERE conversation_id IS NULL OR parent_id IS NULL')
    for column, table in COLUMNS:
        replace_foreign_key(column, table, 'CASCADE')
    op.alter_column('generations', 'parent_id', existing_type=sa.Uuid(), nullable=False)
    op.alter_column('generations', 'conversation_id', existing_type=sa.Uuid(), nullable=False)
