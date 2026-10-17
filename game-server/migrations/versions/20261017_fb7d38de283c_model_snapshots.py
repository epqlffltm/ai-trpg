"""model snapshots

Revision ID: fb7d38de283c
Revises: ffea687ef859
Create Date: 2026-10-17 08:57:24.166114

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'fb7d38de283c'
down_revision: str | Sequence[str] | None = 'ffea687ef859'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 모델 목록에 날짜판을 바꾼 기록(ai_model_snapshots)을 더한다(app/catalog/models.py).
# 이름표는 상품 이름으로 고정하고, 날짜판(API 모델 이름)은 기록을 남기는 명령으로만 바꾼다(유저 결정, 2026-10-17)


def upgrade() -> None:
    op.create_table(
        'ai_model_snapshots',
        sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column('model_slug', sa.String(length=48), nullable=False),
        sa.Column('previous_api_model_id', sa.String(length=200), nullable=False),
        sa.Column('api_model_id', sa.String(length=200), nullable=False),
        sa.Column('note', sa.String(length=200), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            'previous_api_model_id <> api_model_id', name=op.f('ck_ai_model_snapshots_snapshot_changes')
        ),
        sa.ForeignKeyConstraint(
            ['model_slug'],
            ['ai_models.slug'],
            name=op.f('fk_ai_model_snapshots_model_slug_ai_models'),
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_model_snapshots')),
    )
    op.create_index('ix_ai_model_snapshots_model_slug_id', 'ai_model_snapshots', ['model_slug', 'id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_ai_model_snapshots_model_slug_id', table_name='ai_model_snapshots')
    op.drop_table('ai_model_snapshots')
