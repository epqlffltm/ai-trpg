"""reference looks

Revision ID: 1cd15fd4de77
Revises: 9b4e2f6a1c58
Create Date: 2026-11-27 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '1cd15fd4de77'
down_revision: str | Sequence[str] | None = '9b4e2f6a1c58'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 참고 자료의 생김새 글(#1338). 벡터로 바꿀 글이 이름과 생김새 글이다(reference_core/texts.py).
#   - reference_entries.look_ko: 번역 파일의 look. 서술자에게 가는 글(content_ko)의 맨 앞에도 있다. 300자
# 있던 줄은 빈 글이 된다. 다음 load 가 채우고 그 줄의 벡터를 지운다(index 가 다시 만든다)


def upgrade() -> None:
    op.add_column('reference_entries', sa.Column('look_ko', sa.Text(), server_default='', nullable=False))
    op.create_check_constraint(
        op.f('ck_reference_entries_look_ko_length'), 'reference_entries', 'char_length(look_ko) <= 300'
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_reference_entries_look_ko_length'), 'reference_entries', type_='check')
    op.drop_column('reference_entries', 'look_ko')
