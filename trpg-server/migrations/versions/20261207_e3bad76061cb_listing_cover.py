"""listing cover

Revision ID: e3bad76061cb
Revises: 9b2d4f6a8c10
Create Date: 2026-12-07 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e3bad76061cb'
down_revision: str | Sequence[str] | None = '9b2d4f6a8c10'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 시나리오의 표지 그림(#1164). 공개 정보에 제작자가 올린 그림(portraits)의 id 를 둔다. 있던 공개 정보는 표지가 없다.
# 표지로 쓰는 동안 그 그림의 기록은 지우지 못한다(RESTRICT). 되돌리면 표지를 잃는다(그림의 기록은 남는다)


def upgrade() -> None:
    op.add_column('listings', sa.Column('cover_image_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_listings_cover_image_id'), 'listings', ['cover_image_id'], unique=False)
    op.create_foreign_key(
        op.f('fk_listings_cover_image_id_portraits'),
        'listings',
        'portraits',
        ['cover_image_id'],
        ['id'],
        ondelete='RESTRICT',
    )


def downgrade() -> None:
    op.drop_constraint(op.f('fk_listings_cover_image_id_portraits'), 'listings', type_='foreignkey')
    op.drop_index(op.f('ix_listings_cover_image_id'), table_name='listings')
    op.drop_column('listings', 'cover_image_id')
