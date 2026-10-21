"""reference korean

Revision ID: d7a3c9e5f2b8
Revises: c4f8a2d6e1b9
Create Date: 2026-10-21 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd7a3c9e5f2b8'
down_revision: str | Sequence[str] | None = 'c4f8a2d6e1b9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 참고 자료의 한국어 이름과 글(#482 4단계, app/references/translations.py). 지금의 줄은 빈 글이다.
# 데이터 파일을 다시 넣으면(scripts/references.py load) 채워지고, 글이 바뀐 줄의 벡터는 다시 만든다


def upgrade() -> None:
    op.add_column('reference_entries', sa.Column('name_ko', sa.String(length=100), server_default='', nullable=False))
    op.add_column('reference_entries', sa.Column('content_ko', sa.Text(), server_default='', nullable=False))
    op.create_check_constraint(
        op.f('ck_reference_entries_content_ko_length'), 'reference_entries', 'char_length(content_ko) <= 1000'
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_reference_entries_content_ko_length'), 'reference_entries', type_='check')
    op.drop_column('reference_entries', 'content_ko')
    op.drop_column('reference_entries', 'name_ko')
