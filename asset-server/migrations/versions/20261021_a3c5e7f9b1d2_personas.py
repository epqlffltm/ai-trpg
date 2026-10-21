"""personas

Revision ID: a3c5e7f9b1d2
Revises:
Create Date: 2026-10-21 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a3c5e7f9b1d2'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# asset 서버의 첫 테이블. 계정 페르소나(#565, app/personas/models.py).
# 한 사람의 기본은 하나뿐이다(부분 고유 색인 uq_personas_default_per_owner)


def upgrade() -> None:
    op.create_table(
        'personas',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column('image_id', sa.Uuid(), nullable=True),
        sa.Column('age', sa.String(length=20), server_default='', nullable=False),
        sa.Column('gender', sa.String(length=20), server_default='', nullable=False),
        sa.Column('form_of_address', sa.String(length=30), server_default='', nullable=False),
        sa.Column('speech_examples', sa.Text(), server_default='', nullable=False),
        sa.Column('personality', sa.Text(), server_default='', nullable=False),
        sa.Column('is_default', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('revision', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('char_length(description) <= 1000', name=op.f('ck_personas_description_length')),
        sa.CheckConstraint('char_length(personality) <= 1000', name=op.f('ck_personas_personality_length')),
        sa.CheckConstraint('char_length(speech_examples) <= 1000', name=op.f('ck_personas_speech_examples_length')),
        sa.CheckConstraint('revision >= 1', name=op.f('ck_personas_revision_positive')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_personas')),
    )
    op.create_index(op.f('ix_personas_owner_id'), 'personas', ['owner_id'], unique=False)
    op.create_index(
        'uq_personas_default_per_owner', 'personas', ['owner_id'], unique=True, postgresql_where=sa.text('is_default')
    )


def downgrade() -> None:
    op.drop_index('uq_personas_default_per_owner', table_name='personas', postgresql_where=sa.text('is_default'))
    op.drop_index(op.f('ix_personas_owner_id'), table_name='personas')
    op.drop_table('personas')
