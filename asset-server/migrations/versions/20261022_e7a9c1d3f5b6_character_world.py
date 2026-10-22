"""character world

Revision ID: e7a9c1d3f5b6
Revises: d6f8b0c2e4a5
Create Date: 2026-10-22 23:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'e7a9c1d3f5b6'
down_revision: str | Sequence[str] | None = 'd6f8b0c2e4a5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 캐릭터의 지도(장소, 길, 처음 있는 장소)와 물건(물건, 시작 소지품). chat 의 만드는 순서 4.
# 있던 캐릭터는 모두 비어 있다(지도와 물건이 없는 캐릭터다)


def upgrade() -> None:
    op.add_column('characters', sa.Column('places', postgresql.JSONB(), server_default='[]', nullable=False))
    op.add_column('characters', sa.Column('paths', postgresql.JSONB(), server_default='[]', nullable=False))
    op.add_column('characters', sa.Column('start_place', sa.String(length=40), nullable=True))
    op.add_column('characters', sa.Column('items', postgresql.JSONB(), server_default='[]', nullable=False))
    op.add_column('characters', sa.Column('start_items', postgresql.JSONB(), server_default='[]', nullable=False))


def downgrade() -> None:
    op.drop_column('characters', 'start_items')
    op.drop_column('characters', 'items')
    op.drop_column('characters', 'start_place')
    op.drop_column('characters', 'paths')
    op.drop_column('characters', 'places')
