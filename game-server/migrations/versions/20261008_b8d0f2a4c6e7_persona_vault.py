"""persona vault

Revision ID: b8d0f2a4c6e7
Revises: a7c9e1f3b5d6
Create Date: 2026-10-08 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b8d0f2a4c6e7'
down_revision: str | Sequence[str] | None = 'a7c9e1f3b5d6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 자동 생성이 찾은 그대로다. CHECK 도 새로 만드는 테이블에 함께 걸리므로 자동 생성이 적었다
    op.create_table(
        'personas',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('abilities', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True),
        sa.Column('rulebook_title', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "abilities IS NULL OR jsonb_typeof(abilities) = 'object'", name=op.f('ck_personas_abilities_is_object')
        ),
        sa.CheckConstraint('char_length(description) <= 1000', name=op.f('ck_personas_description_length')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_personas')),
    )
    op.create_index(op.f('ix_personas_owner_id'), 'personas', ['owner_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_personas_owner_id'), table_name='personas')
    op.drop_table('personas')
