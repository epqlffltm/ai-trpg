"""model catalog

Revision ID: ffea687ef859
Revises: 0037e18ed88d
Create Date: 2026-10-17 08:01:03.932678

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'ffea687ef859'
down_revision: str | Sequence[str] | None = '0037e18ed88d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 모델 목록의 표 둘을 만든다(app/catalog/models.py). 모델(ai_models)과 원가 단가(ai_model_costs).
# 처음 데이터는 넣지 않는다. API 모델 이름은 공식 문서에서 확인하고 관리 명령(scripts/models.py)으로 넣는다


def upgrade() -> None:
    op.create_table(
        'ai_models',
        sa.Column('slug', sa.String(length=48), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('api_model_id', sa.String(length=200), nullable=False),
        sa.Column('display_name', sa.String(length=80), nullable=False),
        sa.Column('vendor', sa.String(length=30), nullable=False),
        sa.Column('grade', sa.String(length=10), nullable=False),
        sa.Column('supports_reasoning', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('supports_temperature', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('token_limit_field', sa.String(length=30), nullable=True),
        sa.Column('enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('retires_on', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("grade IN ('basic', 'standard', 'premium')", name=op.f('ck_ai_models_grade_allowed')),
        sa.CheckConstraint(
            "provider IN ('openai', 'anthropic', 'gemini', 'local')", name=op.f('ck_ai_models_provider_allowed')
        ),
        sa.CheckConstraint(
            "token_limit_field IS NULL OR token_limit_field IN ('max_tokens', 'max_completion_tokens')",
            name=op.f('ck_ai_models_token_field_allowed'),
        ),
        sa.PrimaryKeyConstraint('slug', name=op.f('pk_ai_models')),
        sa.UniqueConstraint('provider', 'api_model_id', name='uq_ai_models_api_model'),
    )
    op.create_table(
        'ai_model_costs',
        sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column('model_slug', sa.String(length=48), nullable=False),
        sa.Column('input_per_mtok', sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column('cached_input_per_mtok', sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column('cache_write_per_mtok', sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column('output_per_mtok', sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('checked_on', sa.Date(), nullable=False),
        sa.Column('note', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            'input_per_mtok >= 0 AND output_per_mtok >= 0'
            ' AND (cached_input_per_mtok IS NULL OR cached_input_per_mtok >= 0)'
            ' AND (cache_write_per_mtok IS NULL OR cache_write_per_mtok >= 0)',
            name=op.f('ck_ai_model_costs_prices_not_negative'),
        ),
        sa.ForeignKeyConstraint(
            ['model_slug'], ['ai_models.slug'], name=op.f('fk_ai_model_costs_model_slug_ai_models'), ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_model_costs')),
    )
    op.create_index(
        'ix_ai_model_costs_model_slug_effective_from',
        'ai_model_costs',
        ['model_slug', 'effective_from', 'id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_ai_model_costs_model_slug_effective_from', table_name='ai_model_costs')
    op.drop_table('ai_model_costs')
    op.drop_table('ai_models')
