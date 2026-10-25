"""models

Revision ID: e3f5a7b9c1d2
Revises: d2e4f6a8b0c1
Create Date: 2026-10-25 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e3f5a7b9c1d2'
down_revision: str | Sequence[str] | None = 'd2e4f6a8b0c1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 모델 목록의 표 셋(app/catalog/models.py)과 세션의 모델(conversations.model_slug).
# chat 서버의 표와 같은 모양이다. 회사의 대체 모델(vendor_fallback)이 없고 성인 등급의 세션에 쓰기(allows_adult)가 있다.
# 표는 비어서 만들어진다. 모델은 scripts.models sync 로 원본 파일(ai_core/model_catalog.toml)에서 들여온다.
# 창구와 생각의 방식의 CHECK 는 지금의 목록(ai_core/catalog_contract.py)으로 건다.
# 목록에 값이 늘면 새 마이그레이션으로 바꾼다(alembic check 는 CHECK 의 차이를 보지 못한다)


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
        sa.Column('reasoning_style', sa.String(length=20), nullable=True),
        sa.Column('enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('retires_on', sa.Date(), nullable=True),
        sa.Column('allows_adult', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("grade IN ('basic', 'standard', 'premium')", name=op.f('ck_ai_models_grade_allowed')),
        sa.CheckConstraint(
            "provider IN ('openai', 'anthropic', 'gemini', 'local', 'zai', 'deepinfra')",
            name=op.f('ck_ai_models_provider_allowed'),
        ),
        sa.CheckConstraint(
            "reasoning_style IS NULL OR reasoning_style IN ('adaptive', 'always', 'between_tools', 'budget', "
            "'level_minimal', 'level_low', 'budget_min', 'thinking_type')",
            name=op.f('ck_ai_models_reasoning_style_allowed'),
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
    op.add_column('conversations', sa.Column('model_slug', sa.String(length=48), nullable=True))
    op.create_index(op.f('ix_conversations_model_slug'), 'conversations', ['model_slug'], unique=False)
    op.create_foreign_key(
        op.f('fk_conversations_model_slug_ai_models'),
        'conversations',
        'ai_models',
        ['model_slug'],
        ['slug'],
        ondelete='RESTRICT',
    )


def downgrade() -> None:
    op.drop_constraint(op.f('fk_conversations_model_slug_ai_models'), 'conversations', type_='foreignkey')
    op.drop_index(op.f('ix_conversations_model_slug'), table_name='conversations')
    op.drop_column('conversations', 'model_slug')
    op.drop_index('ix_ai_model_snapshots_model_slug_id', table_name='ai_model_snapshots')
    op.drop_table('ai_model_snapshots')
    op.drop_index('ix_ai_model_costs_model_slug_effective_from', table_name='ai_model_costs')
    op.drop_table('ai_model_costs')
    op.drop_table('ai_models')
