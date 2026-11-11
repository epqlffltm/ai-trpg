"""baseline

Revision ID: fbdb2bc58f5e
Revises:
Create Date: 2026-11-11 04:23:57.102814

첫 배포 전에 쌓인 마이그레이션 172개를 하나로 합친 기준선(#1273). 빈 스키마에 지금의 표를 한 번에 만든다.
모델에서 자동으로 만든 뒤, 모델이 모르는 것(운영자 기록을 고치지 못하게 하는 함수와 트리거)을 손으로 더했다.
옛 사슬로 만든 스키마와 같은지는 tools/compare_schemas.py 로 견주었다.
옛 마이그레이션이 하던 데이터 옮기기는 빈 DB 에서 할 일이 없어 넣지 않았다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = 'fbdb2bc58f5e'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 운영자의 감사 기록은 덧붙이기만 한다. 고치기와 지우기를 트리거가 막는다(trpg-server 와 같다).
# TRUNCATE 는 막지 않는다(테스트가 비울 때 쓴다). 함수와 트리거에 스키마 이름을 붙이지 않는다
APPEND_ONLY = ('operator_reads', 'operator_actions')


def forbid_rewrites(table: str) -> None:
    """그 표의 고치기와 지우기를 막는 함수와 트리거를 만든다."""
    op.execute(
        f"""
        CREATE FUNCTION {table}_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '{table} 는 덧붙이기만 한다(%)', TG_OP;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {table}_no_rewrite
        BEFORE UPDATE OR DELETE ON {table}
        FOR EACH ROW EXECUTE FUNCTION {table}_append_only()
        """
    )


def allow_rewrites(table: str) -> None:
    """forbid_rewrites 를 되돌린다."""
    op.execute(f'DROP TRIGGER {table}_no_rewrite ON {table}')
    op.execute(f'DROP FUNCTION {table}_append_only()')


def require_extensions() -> None:
    """
    pgvector 와 pg_trgm 이 켜져 있지 않으면 알아볼 수 있는 말로 멈춘다.

    게임 계정은 확장을 켤 수 없다(슈퍼유저만 된다). 그래서 여기서 켜지 않고, 켜져 있는지만 본다.
    켜져 있지 않으면 vector 타입과 gin_trgm_ops 가 "없는 타입", "없는 연산자 묶음"이라는 알기 어려운 오류로 실패한다.
    """
    for name, where in (('vector', '"로어북 검색"'), ('pg_trgm', '"준비"')):
        found = op.get_bind().scalar(sa.text('SELECT 1 FROM pg_extension WHERE extname = :name'), {'name': name})
        if found is None:
            raise RuntimeError(
                f'{name} 이 켜져 있지 않습니다. docker/postgres/init/03-extensions.sql 을 슈퍼유저로 실행하세요'
                f'(trpg-server/README.md 의 {where})'
            )


def upgrade() -> None:
    require_extensions()
    op.create_table(
        'ai_invocations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('purpose', sa.String(length=40), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=True),
        sa.Column('round_number', sa.Integer(), nullable=True),
        sa.Column('host_id', sa.Uuid(), nullable=True),
        sa.Column('provider', sa.String(length=40), nullable=False),
        sa.Column('model', sa.String(length=200), nullable=False),
        sa.Column('prompt_version', sa.String(length=40), nullable=False),
        sa.Column('reasoning', sa.String(length=20), nullable=False),
        sa.Column('narration_style', sa.String(length=20), nullable=True),
        sa.Column('outcome', sa.String(length=20), nullable=False),
        sa.Column('error', sa.String(length=40), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('finish_reason', sa.String(length=40), nullable=True),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('temperature', sa.Float(), nullable=True),
        sa.Column('max_tokens', sa.Integer(), nullable=True),
        sa.Column('lore_entry_ids', postgresql.ARRAY(sa.Uuid()), server_default='{}', nullable=False),
        sa.Column('memory_rounds', postgresql.ARRAY(sa.Integer()), server_default='{}', nullable=False),
        sa.Column('reference_ids', postgresql.ARRAY(sa.Uuid()), server_default='{}', nullable=False),
        sa.Column('input_digest', sa.String(length=64), nullable=True),
        sa.Column('cached_input_tokens', sa.Integer(), nullable=True),
        sa.Column('cache_write_tokens', sa.Integer(), nullable=True),
        sa.Column('reasoning_tokens', sa.Integer(), nullable=True),
        sa.Column('model_slug', sa.String(length=48), nullable=True),
        sa.Column('cost_usd', sa.Numeric(precision=14, scale=8), nullable=True),
        sa.Column('cost_id', sa.Integer(), nullable=True),
        sa.Column('input_chars', sa.Integer(), nullable=True),
        sa.CheckConstraint("(outcome = 'ok') = (error IS NULL)", name=op.f('ck_ai_invocations_error_unless_ok')),
        sa.CheckConstraint("outcome <> 'failed' OR text IS NULL", name=op.f('ck_ai_invocations_no_text_when_failed')),
        sa.CheckConstraint("outcome IN ('ok', 'rejected', 'failed')", name=op.f('ck_ai_invocations_outcome_allowed')),
        sa.CheckConstraint(
            'cached_input_tokens >= 0 AND cache_write_tokens >= 0 AND reasoning_tokens >= 0',
            name=op.f('ck_ai_invocations_token_details_not_negative'),
        ),
        sa.CheckConstraint('cost_usd >= 0', name=op.f('ck_ai_invocations_cost_not_negative')),
        sa.CheckConstraint('input_chars >= 0', name=op.f('ck_ai_invocations_input_chars_not_negative')),
        sa.CheckConstraint(
            'input_tokens >= 0 AND output_tokens >= 0', name=op.f('ck_ai_invocations_tokens_not_negative')
        ),
        sa.CheckConstraint('latency_ms >= 0', name=op.f('ck_ai_invocations_latency_not_negative')),
        sa.CheckConstraint('max_tokens > 0', name=op.f('ck_ai_invocations_max_tokens_positive')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_invocations')),
    )
    op.create_index('ix_ai_invocations_table_id_created_at', 'ai_invocations', ['table_id', 'created_at'], unique=False)
    op.create_index(
        'ix_ai_invocations_text_kept',
        'ai_invocations',
        ['created_at'],
        unique=False,
        postgresql_where='text IS NOT NULL',
    )
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
        sa.Column('vendor_fallback', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("grade IN ('basic', 'standard', 'premium')", name=op.f('ck_ai_models_grade_allowed')),
        sa.CheckConstraint(
            "provider IN ('openai', 'anthropic', 'gemini', 'local', 'zai', 'deepinfra', 'xai')",
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
    op.create_index(
        'uq_ai_models_vendor_fallback',
        'ai_models',
        ['vendor'],
        unique=True,
        postgresql_where=sa.text('vendor_fallback'),
    )
    op.create_table(
        'assets',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('visibility', sa.String(length=20), nullable=False),
        sa.Column('rating', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("rating IN ('all', 'adult')", name=op.f('ck_assets_rating_allowed')),
        sa.CheckConstraint(
            "type IN ('world', 'rulebook', 'scenario', 'lorebook', 'bestiary', 'campaign')",
            name=op.f('ck_assets_type_allowed'),
        ),
        sa.CheckConstraint("visibility IN ('private')", name=op.f('ck_assets_visibility_allowed')),
        sa.CheckConstraint('char_length(description) <= 1000', name=op.f('ck_assets_description_length')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_assets')),
    )
    op.create_index(op.f('ix_assets_owner_id'), 'assets', ['owner_id'], unique=False)
    op.create_index(
        'ix_assets_title_trgm',
        'assets',
        ['title'],
        unique=False,
        postgresql_using='gin',
        postgresql_ops={'title': 'extensions.gin_trgm_ops'},
    )
    op.create_table(
        'operator_actions',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('operator_id', sa.Uuid(), nullable=False),
        sa.Column('acted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('action', sa.String(length=30), nullable=False),
        sa.Column('target_id', sa.Uuid(), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=False),
        sa.Column('request_id', sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "action IN ('scenario_sanction', 'table_end', 'publishing_ban', 'publishing_unban')",
            name=op.f('ck_operator_actions_action_allowed'),
        ),
        sa.CheckConstraint("btrim(reason) <> ''", name=op.f('ck_operator_actions_reason_not_blank')),
        sa.CheckConstraint('char_length(reason) <= 200', name=op.f('ck_operator_actions_reason_length')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_operator_actions')),
        info={'append_only': True},
    )
    op.create_index('ix_operator_actions_operator', 'operator_actions', ['operator_id', 'acted_at'], unique=False)
    op.create_index('ix_operator_actions_target', 'operator_actions', ['target_id', 'acted_at'], unique=False)
    op.create_table(
        'operator_reads',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('operator_id', sa.Uuid(), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('target_kind', sa.String(length=30), nullable=False),
        sa.Column('target_id', sa.Uuid(), nullable=False),
        sa.Column('target_number', sa.Integer(), nullable=True),
        sa.Column('reason', sa.String(length=200), nullable=False),
        sa.Column('request_id', sa.String(length=128), nullable=True),
        sa.CheckConstraint("btrim(reason) <> ''", name=op.f('ck_operator_reads_reason_not_blank')),
        sa.CheckConstraint(
            "target_kind IN ('table', 'table_events', 'table_messages', 'table_whispers', 'scenario', "
            "'scenario_version')",
            name=op.f('ck_operator_reads_target_kind_allowed'),
        ),
        sa.CheckConstraint('char_length(reason) <= 200', name=op.f('ck_operator_reads_reason_length')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_operator_reads')),
        info={'append_only': True},
    )
    op.create_index('ix_operator_reads_operator', 'operator_reads', ['operator_id', 'read_at'], unique=False)
    op.create_index('ix_operator_reads_target', 'operator_reads', ['target_id', 'read_at'], unique=False)
    op.create_table(
        'outgoing_notifications',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column('source_key', sa.String(length=128), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('kind', sa.String(length=64), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_error', sa.String(length=40), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'failed')", name=op.f('ck_outgoing_notifications_status_allowed')),
        sa.CheckConstraint('attempts >= 0', name=op.f('ck_outgoing_notifications_attempts_not_negative')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_outgoing_notifications')),
        sa.UniqueConstraint('source_key', name=op.f('uq_outgoing_notifications_source_key')),
    )
    op.create_index(
        'ix_outgoing_notifications_due',
        'outgoing_notifications',
        ['next_attempt_at'],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),
    )
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
    op.create_table(
        'portraits',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_portraits')),
    )
    op.create_index('ix_portraits_owner_created', 'portraits', ['owner_id', 'created_at'], unique=False)
    op.create_table(
        'publishing_bans',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('banned_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('banned_by', sa.Uuid(), nullable=True),
        sa.Column('reason', sa.String(length=200), nullable=False),
        sa.Column('lifted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('lifted_by', sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint('user_id', name=op.f('pk_publishing_bans')),
    )
    op.create_table(
        'reference_entries',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('aliases', postgresql.ARRAY(sa.String(length=30)), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('name_ko', sa.String(length=100), server_default='', nullable=False),
        sa.Column('content_ko', sa.Text(), server_default='', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("kind IN ('monster', 'item')", name=op.f('ck_reference_entries_kind_allowed')),
        sa.CheckConstraint("source IN ('srd51')", name=op.f('ck_reference_entries_source_allowed')),
        sa.CheckConstraint('cardinality(aliases) <= 5', name=op.f('ck_reference_entries_aliases_count')),
        sa.CheckConstraint('char_length(content) <= 1000', name=op.f('ck_reference_entries_content_length')),
        sa.CheckConstraint('char_length(content_ko) <= 1000', name=op.f('ck_reference_entries_content_ko_length')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_reference_entries')),
        sa.UniqueConstraint('source', 'key', name=op.f('uq_reference_entries_source')),
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
    op.create_table(
        'bestiaries',
        sa.Column('asset_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ['asset_id'], ['assets.id'], name=op.f('fk_bestiaries_asset_id_assets'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('asset_id', name=op.f('pk_bestiaries')),
    )
    op.create_table(
        'campaigns',
        sa.Column('asset_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ['asset_id'], ['assets.id'], name=op.f('fk_campaigns_asset_id_assets'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('asset_id', name=op.f('pk_campaigns')),
    )
    op.create_table(
        'lorebooks',
        sa.Column('asset_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ['asset_id'], ['assets.id'], name=op.f('fk_lorebooks_asset_id_assets'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('asset_id', name=op.f('pk_lorebooks')),
    )
    op.create_table(
        'reference_embeddings',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('reference_id', sa.Uuid(), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('embedding', Vector(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['reference_id'],
            ['reference_entries.id'],
            name=op.f('fk_reference_embeddings_reference_id_reference_entries'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_reference_embeddings')),
        sa.UniqueConstraint('model', 'reference_id', name=op.f('uq_reference_embeddings_model')),
    )
    op.create_index(
        op.f('ix_reference_embeddings_reference_id'), 'reference_embeddings', ['reference_id'], unique=False
    )
    op.create_table(
        'rulebooks',
        sa.Column('gm_guide', sa.Text(), nullable=False),
        sa.Column('rules', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('asset_id', sa.Uuid(), nullable=False),
        sa.CheckConstraint('char_length(gm_guide) <= 4000', name=op.f('ck_rulebooks_gm_guide_length')),
        sa.ForeignKeyConstraint(
            ['asset_id'], ['assets.id'], name=op.f('fk_rulebooks_asset_id_assets'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('asset_id', name=op.f('pk_rulebooks')),
    )
    op.create_table(
        'worlds',
        sa.Column('setting', sa.Text(), nullable=False),
        sa.Column('gm_notes', sa.Text(), nullable=False),
        sa.Column('references_allowed', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('asset_id', sa.Uuid(), nullable=False),
        sa.CheckConstraint('char_length(gm_notes) <= 4000', name=op.f('ck_worlds_gm_notes_length')),
        sa.CheckConstraint('char_length(setting) <= 8000', name=op.f('ck_worlds_setting_length')),
        sa.ForeignKeyConstraint(
            ['asset_id'], ['assets.id'], name=op.f('fk_worlds_asset_id_assets'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('asset_id', name=op.f('pk_worlds')),
    )
    op.create_table(
        'campaign_versions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('campaign_id', sa.Uuid(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('char_length(note) <= 500', name=op.f('ck_campaign_versions_note_length')),
        sa.CheckConstraint('number >= 1', name=op.f('ck_campaign_versions_number_positive')),
        sa.ForeignKeyConstraint(
            ['campaign_id'],
            ['campaigns.asset_id'],
            name=op.f('fk_campaign_versions_campaign_id_campaigns'),
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_campaign_versions')),
        sa.UniqueConstraint('campaign_id', 'number', name=op.f('uq_campaign_versions_campaign_id')),
    )
    op.create_table(
        'lore_entries',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('lorebook_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('keywords', postgresql.ARRAY(sa.String(length=30)), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('kind', sa.String(length=20), server_default='other', nullable=False),
        sa.Column('true_names', postgresql.ARRAY(sa.String(length=50)), server_default='{}', nullable=False),
        sa.Column('copied_source', sa.String(length=20), nullable=True),
        sa.Column('copied_key', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "kind IN ('person', 'place', 'item', 'faction', 'species', 'legend', 'event', 'other')",
            name=op.f('ck_lore_entries_kind_allowed'),
        ),
        sa.CheckConstraint(
            '(copied_source IS NULL) = (copied_key IS NULL)', name=op.f('ck_lore_entries_copied_from_paired')
        ),
        sa.CheckConstraint('cardinality(keywords) <= 5', name=op.f('ck_lore_entries_keywords_count')),
        sa.CheckConstraint('cardinality(true_names) <= 5', name=op.f('ck_lore_entries_true_names_count')),
        sa.CheckConstraint('char_length(content) <= 500', name=op.f('ck_lore_entries_content_length')),
        sa.ForeignKeyConstraint(
            ['lorebook_id'],
            ['lorebooks.asset_id'],
            name=op.f('fk_lore_entries_lorebook_id_lorebooks'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_lore_entries')),
    )
    op.create_index(op.f('ix_lore_entries_lorebook_id'), 'lore_entries', ['lorebook_id'], unique=False)
    op.create_table(
        'monsters',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('bestiary_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('unique', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('copied_source', sa.String(length=20), nullable=True),
        sa.Column('copied_key', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "kind IN ('humanoid', 'beast', 'undead', 'construct', 'other')", name=op.f('ck_monsters_kind_allowed')
        ),
        sa.CheckConstraint(
            '(copied_source IS NULL) = (copied_key IS NULL)', name=op.f('ck_monsters_copied_from_paired')
        ),
        sa.CheckConstraint('char_length(content) <= 500', name=op.f('ck_monsters_content_length')),
        sa.ForeignKeyConstraint(
            ['bestiary_id'],
            ['bestiaries.asset_id'],
            name=op.f('fk_monsters_bestiary_id_bestiaries'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_monsters')),
    )
    op.create_index(op.f('ix_monsters_bestiary_id'), 'monsters', ['bestiary_id'], unique=False)
    op.create_table(
        'scenarios',
        sa.Column('rulebook_id', sa.Uuid(), nullable=True),
        sa.Column('world_id', sa.Uuid(), nullable=True),
        sa.Column('openings', postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column('min_players', sa.SmallInteger(), nullable=False),
        sa.Column('max_players', sa.SmallInteger(), nullable=False),
        sa.Column('pregens', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            'character_modes',
            postgresql.ARRAY(sa.String(length=20)),
            server_default=sa.text("'{pregen,custom}'"),
            nullable=False,
        ),
        sa.Column('reroll_allowed', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('xp_split', sa.String(length=10), server_default=sa.text("'share'"), nullable=False),
        sa.Column('improvised_encounters', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('narration_style', sa.String(length=20), server_default=sa.text("'classic'"), nullable=False),
        sa.Column('narration_model', sa.String(length=48), nullable=True),
        sa.Column('default_sheet', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            'npc_sheets', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            'items', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            'starting_items',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column('currency', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            'quests', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column('start_place', sa.Uuid(), nullable=True),
        sa.Column(
            'routes', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column('landmarks', postgresql.ARRAY(sa.Uuid()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            'monster_sheets',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            'encounters', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            'place_items',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            'covers', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            'pictures', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            'submaps', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            'traps', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            'wanders', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            'happenings', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            'chapters', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            'achievements',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            'npc_places', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column('default_npc_sheet', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('hp_base', sa.SmallInteger(), nullable=True),
        sa.Column('hp_cap', sa.SmallInteger(), nullable=True),
        sa.Column('start_day', sa.SmallInteger(), server_default=sa.text('1'), nullable=False),
        sa.Column('start_hour', sa.SmallInteger(), server_default=sa.text('8'), nullable=False),
        sa.Column('round_minutes', sa.Integer(), server_default=sa.text('10'), nullable=False),
        sa.Column('asset_id', sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "cardinality(character_modes) >= 1 AND character_modes <@ ARRAY['pregen', 'custom', 'manual', "
            "'point_buy', 'rolled']::varchar[]",
            name=op.f('ck_scenarios_character_modes_allowed'),
        ),
        sa.CheckConstraint(
            "char_length(array_to_string(openings, '')) <= 10000", name=op.f('ck_scenarios_openings_length')
        ),
        sa.CheckConstraint(
            "narration_style IN ('none', 'classic', 'web_novel', 'hardboiled', 'emotional', 'action', 'dopamine', "
            "'literary')",
            name=op.f('ck_scenarios_narration_style_allowed'),
        ),
        sa.CheckConstraint("xp_split IN ('each', 'share')", name=op.f('ck_scenarios_xp_split_allowed')),
        sa.CheckConstraint(
            '(hp_base IS NULL) = (hp_cap IS NULL) AND (hp_base IS NULL OR (hp_base >= 1 AND hp_base <= hp_cap'
            ' AND hp_cap <= 999))',
            name=op.f('ck_scenarios_player_made_hp'),
        ),
        sa.CheckConstraint(
            '1 <= min_players AND min_players <= max_players AND max_players <= 4',
            name=op.f('ck_scenarios_players_range'),
        ),
        sa.CheckConstraint('cardinality(landmarks) <= 100', name=op.f('ck_scenarios_landmarks_count')),
        sa.CheckConstraint('cardinality(openings) <= 5', name=op.f('ck_scenarios_openings_count')),
        sa.CheckConstraint(
            'improvised_encounters BETWEEN 0 AND 20', name=op.f('ck_scenarios_improvised_encounters_range')
        ),
        sa.CheckConstraint('jsonb_array_length(achievements) <= 50', name=op.f('ck_scenarios_achievements_count')),
        sa.CheckConstraint('jsonb_array_length(chapters) <= 20', name=op.f('ck_scenarios_chapters_count')),
        sa.CheckConstraint('jsonb_array_length(covers) <= 100', name=op.f('ck_scenarios_covers_count')),
        sa.CheckConstraint('jsonb_array_length(encounters) <= 50', name=op.f('ck_scenarios_encounters_count')),
        sa.CheckConstraint('jsonb_array_length(happenings) <= 50', name=op.f('ck_scenarios_happenings_count')),
        sa.CheckConstraint('jsonb_array_length(items) <= 100', name=op.f('ck_scenarios_items_count')),
        sa.CheckConstraint('jsonb_array_length(monster_sheets) <= 100', name=op.f('ck_scenarios_monster_sheets_count')),
        sa.CheckConstraint('jsonb_array_length(npc_places) <= 100', name=op.f('ck_scenarios_npc_places_count')),
        sa.CheckConstraint('jsonb_array_length(npc_sheets) <= 100', name=op.f('ck_scenarios_npc_sheets_count')),
        sa.CheckConstraint('jsonb_array_length(pictures) <= 200', name=op.f('ck_scenarios_pictures_count')),
        sa.CheckConstraint('jsonb_array_length(place_items) <= 100', name=op.f('ck_scenarios_place_items_count')),
        sa.CheckConstraint('jsonb_array_length(pregens) <= 8', name=op.f('ck_scenarios_pregens_count')),
        sa.CheckConstraint('jsonb_array_length(quests) <= 50', name=op.f('ck_scenarios_quests_count')),
        sa.CheckConstraint('jsonb_array_length(routes) <= 200', name=op.f('ck_scenarios_routes_count')),
        sa.CheckConstraint('jsonb_array_length(starting_items) <= 20', name=op.f('ck_scenarios_starting_items_count')),
        sa.CheckConstraint('jsonb_array_length(submaps) <= 50', name=op.f('ck_scenarios_submaps_count')),
        sa.CheckConstraint('jsonb_array_length(traps) <= 50', name=op.f('ck_scenarios_traps_count')),
        sa.CheckConstraint('jsonb_array_length(wanders) <= 50', name=op.f('ck_scenarios_wanders_count')),
        sa.CheckConstraint('round_minutes BETWEEN 1 AND 10080', name=op.f('ck_scenarios_round_minutes_range')),
        sa.CheckConstraint('start_day BETWEEN 1 AND 999', name=op.f('ck_scenarios_start_day_range')),
        sa.CheckConstraint('start_hour BETWEEN 0 AND 23', name=op.f('ck_scenarios_start_hour_range')),
        sa.ForeignKeyConstraint(
            ['asset_id'], ['assets.id'], name=op.f('fk_scenarios_asset_id_assets'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['rulebook_id'],
            ['rulebooks.asset_id'],
            name=op.f('fk_scenarios_rulebook_id_rulebooks'),
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['world_id'], ['worlds.asset_id'], name=op.f('fk_scenarios_world_id_worlds'), ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('asset_id', name=op.f('pk_scenarios')),
    )
    op.create_index(op.f('ix_scenarios_rulebook_id'), 'scenarios', ['rulebook_id'], unique=False)
    op.create_index(op.f('ix_scenarios_world_id'), 'scenarios', ['world_id'], unique=False)
    op.create_table(
        'banners',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('scenario_id', sa.Uuid(), nullable=False),
        sa.Column('position', sa.SmallInteger(), nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('ends_at IS NULL OR starts_at < ends_at', name=op.f('ck_banners_period_order')),
        sa.CheckConstraint('position >= 0 AND position <= 999', name=op.f('ck_banners_position_range')),
        sa.ForeignKeyConstraint(
            ['scenario_id'], ['scenarios.asset_id'], name=op.f('fk_banners_scenario_id_scenarios'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_banners')),
    )
    op.create_index(op.f('ix_banners_scenario_id'), 'banners', ['scenario_id'], unique=False)
    op.create_table(
        'campaign_episodes',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('campaign_id', sa.Uuid(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('scenario_id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(length=30), nullable=False),
        sa.CheckConstraint('0 <= position AND position < 10', name=op.f('ck_campaign_episodes_position_range')),
        sa.CheckConstraint('char_length(title) <= 30', name=op.f('ck_campaign_episodes_title_length')),
        sa.ForeignKeyConstraint(
            ['campaign_id'],
            ['campaigns.asset_id'],
            name=op.f('fk_campaign_episodes_campaign_id_campaigns'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['scenario_id'],
            ['scenarios.asset_id'],
            name=op.f('fk_campaign_episodes_scenario_id_scenarios'),
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_campaign_episodes')),
        sa.UniqueConstraint('campaign_id', 'position', name='uq_campaign_episodes_position'),
        sa.UniqueConstraint('campaign_id', 'scenario_id', name='uq_campaign_episodes_scenario'),
    )
    op.create_index(op.f('ix_campaign_episodes_scenario_id'), 'campaign_episodes', ['scenario_id'], unique=False)
    op.create_table(
        'campaign_runs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('campaign_id', sa.Uuid(), nullable=False),
        sa.Column('version_id', sa.Uuid(), nullable=False),
        sa.Column('host_id', sa.Uuid(), nullable=False),
        sa.Column('position', sa.SmallInteger(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('playing', 'ended')", name=op.f('ck_campaign_runs_status_allowed')),
        sa.CheckConstraint('0 <= position AND position < 10', name=op.f('ck_campaign_runs_position_range')),
        sa.ForeignKeyConstraint(
            ['campaign_id'],
            ['campaigns.asset_id'],
            name=op.f('fk_campaign_runs_campaign_id_campaigns'),
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['version_id'],
            ['campaign_versions.id'],
            name=op.f('fk_campaign_runs_version_id_campaign_versions'),
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_campaign_runs')),
    )
    op.create_index(op.f('ix_campaign_runs_campaign_id'), 'campaign_runs', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_campaign_runs_host_id'), 'campaign_runs', ['host_id'], unique=False)
    op.create_index(op.f('ix_campaign_runs_version_id'), 'campaign_runs', ['version_id'], unique=False)
    op.create_table(
        'scenario_bestiaries',
        sa.Column('scenario_id', sa.Uuid(), nullable=False),
        sa.Column('bestiary_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ['bestiary_id'],
            ['bestiaries.asset_id'],
            name=op.f('fk_scenario_bestiaries_bestiary_id_bestiaries'),
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['scenario_id'],
            ['scenarios.asset_id'],
            name=op.f('fk_scenario_bestiaries_scenario_id_scenarios'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('scenario_id', 'bestiary_id', name=op.f('pk_scenario_bestiaries')),
    )
    op.create_index(op.f('ix_scenario_bestiaries_bestiary_id'), 'scenario_bestiaries', ['bestiary_id'], unique=False)
    op.create_table(
        'scenario_lorebooks',
        sa.Column('scenario_id', sa.Uuid(), nullable=False),
        sa.Column('lorebook_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ['lorebook_id'],
            ['lorebooks.asset_id'],
            name=op.f('fk_scenario_lorebooks_lorebook_id_lorebooks'),
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['scenario_id'],
            ['scenarios.asset_id'],
            name=op.f('fk_scenario_lorebooks_scenario_id_scenarios'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('scenario_id', 'lorebook_id', name=op.f('pk_scenario_lorebooks')),
    )
    op.create_index(op.f('ix_scenario_lorebooks_lorebook_id'), 'scenario_lorebooks', ['lorebook_id'], unique=False)
    op.create_table(
        'scenario_players',
        sa.Column('scenario_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('first_played_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['scenario_id'],
            ['scenarios.asset_id'],
            name=op.f('fk_scenario_players_scenario_id_scenarios'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('scenario_id', 'user_id', name=op.f('pk_scenario_players')),
    )
    op.create_index(op.f('ix_scenario_players_user_id'), 'scenario_players', ['user_id'], unique=False)
    op.create_table(
        'scenario_versions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('scenario_id', sa.Uuid(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('char_length(note) <= 500', name=op.f('ck_scenario_versions_note_length')),
        sa.CheckConstraint('number >= 1', name=op.f('ck_scenario_versions_number_positive')),
        sa.ForeignKeyConstraint(
            ['scenario_id'],
            ['scenarios.asset_id'],
            name=op.f('fk_scenario_versions_scenario_id_scenarios'),
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_scenario_versions')),
        sa.UniqueConstraint('scenario_id', 'number', name=op.f('uq_scenario_versions_scenario_id')),
    )
    op.create_table(
        'campaign_carries',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('run_id', sa.Uuid(), nullable=False),
        sa.Column('position', sa.SmallInteger(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('carry', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('0 <= position AND position < 10', name=op.f('ck_campaign_carries_position_range')),
        sa.ForeignKeyConstraint(
            ['run_id'], ['campaign_runs.id'], name=op.f('fk_campaign_carries_run_id_campaign_runs'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_campaign_carries')),
        sa.UniqueConstraint('run_id', 'position', 'user_id', name='uq_campaign_carries_person'),
    )
    op.create_index(op.f('ix_campaign_carries_user_id'), 'campaign_carries', ['user_id'], unique=False)
    op.create_table(
        'campaign_quest_results',
        sa.Column('run_id', sa.Uuid(), nullable=False),
        sa.Column('position', sa.SmallInteger(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('result', sa.String(length=20), nullable=False),
        sa.CheckConstraint("result IN ('succeeded', 'failed')", name=op.f('ck_campaign_quest_results_result_allowed')),
        sa.CheckConstraint('0 <= position AND position < 10', name=op.f('ck_campaign_quest_results_position_range')),
        sa.ForeignKeyConstraint(
            ['run_id'],
            ['campaign_runs.id'],
            name=op.f('fk_campaign_quest_results_run_id_campaign_runs'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('run_id', 'position', 'entry_id', name=op.f('pk_campaign_quest_results')),
    )
    op.create_table(
        'game_tables',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('host_id', sa.Uuid(), nullable=False),
        sa.Column('version_id', sa.Uuid(), nullable=False),
        sa.Column('scenario_id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(length=100), nullable=False),
        sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('opening_index', sa.SmallInteger(), nullable=False),
        sa.Column('chapter_id', sa.String(length=40), nullable=True),
        sa.Column('chapter_round', sa.Integer(), nullable=True),
        sa.Column(
            'chapter_path',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column('improvised_encounters', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('capacity', sa.SmallInteger(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('rating', sa.String(length=20), nullable=False),
        sa.Column('invite_code', sa.String(length=12), nullable=False),
        sa.Column('is_public', sa.Boolean(), nullable=False),
        sa.Column(
            'character_modes',
            postgresql.ARRAY(sa.String(length=20)),
            server_default=sa.text("'{pregen,custom}'"),
            nullable=False,
        ),
        sa.Column('password_hash', sa.String(length=200), nullable=True),
        sa.Column('narration_style', sa.String(length=20), server_default=sa.text("'classic'"), nullable=False),
        sa.Column('narration_model', sa.String(length=48), nullable=True),
        sa.Column('input_step', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('output_step', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('retire_notice_for', sa.Date(), nullable=True),
        sa.Column('retire_notice_days', sa.SmallInteger(), nullable=True),
        sa.Column('round_time_limit', sa.Integer(), nullable=True),
        sa.Column('credit_wait_seconds', sa.Integer(), server_default=sa.text('300'), nullable=False),
        sa.Column('remove_short_payers', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('whisper_notice', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('references_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('friendly_fire', sa.String(length=20), server_default=sa.text("'off'"), nullable=False),
        sa.Column('turn_mode', sa.String(length=20), server_default=sa.text("'together'"), nullable=False),
        sa.Column('turn_cycle', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column(
            'turn_queue', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            'turn_waits', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            'turn_foes', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            'turn_stances',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column('last_sequence', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('last_message_sequence', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('revert_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "cardinality(character_modes) >= 1 AND character_modes <@ ARRAY['pregen', 'custom', 'manual', "
            "'point_buy', 'rolled']::varchar[]",
            name=op.f('ck_game_tables_character_modes_allowed'),
        ),
        sa.CheckConstraint(
            "friendly_fire IN ('off', 'prank', 'full')", name=op.f('ck_game_tables_friendly_fire_allowed')
        ),
        sa.CheckConstraint("jsonb_typeof(chapter_path) = 'array'", name=op.f('ck_game_tables_chapter_path_is_array')),
        sa.CheckConstraint("jsonb_typeof(turn_foes) = 'array'", name=op.f('ck_game_tables_turn_foes_is_array')),
        sa.CheckConstraint("jsonb_typeof(turn_queue) = 'array'", name=op.f('ck_game_tables_turn_queue_is_array')),
        sa.CheckConstraint("jsonb_typeof(turn_stances) = 'object'", name=op.f('ck_game_tables_turn_stances_is_object')),
        sa.CheckConstraint("jsonb_typeof(turn_waits) = 'array'", name=op.f('ck_game_tables_turn_waits_is_array')),
        sa.CheckConstraint(
            "narration_style IN ('none', 'classic', 'web_novel', 'hardboiled', 'emotional', 'action', 'dopamine', "
            "'literary')",
            name=op.f('ck_game_tables_narration_style_allowed'),
        ),
        sa.CheckConstraint("rating IN ('all', 'adult')", name=op.f('ck_game_tables_rating_allowed')),
        sa.CheckConstraint("status IN ('recruiting', 'playing', 'ended')", name=op.f('ck_game_tables_status_allowed')),
        sa.CheckConstraint("turn_mode IN ('together', 'turns')", name=op.f('ck_game_tables_turn_mode_allowed')),
        sa.CheckConstraint('capacity BETWEEN 1 AND 4', name=op.f('ck_game_tables_capacity_range')),
        sa.CheckConstraint(
            'credit_wait_seconds BETWEEN 30 AND 3600', name=op.f('ck_game_tables_credit_wait_seconds_range')
        ),
        sa.CheckConstraint('input_step BETWEEN 0 AND 2', name=op.f('ck_game_tables_input_step_range')),
        sa.CheckConstraint('opening_index >= 0', name=op.f('ck_game_tables_opening_index_not_negative')),
        sa.CheckConstraint('output_step BETWEEN 0 AND 2', name=op.f('ck_game_tables_output_step_range')),
        sa.CheckConstraint('password_hash IS NULL OR is_public', name=op.f('ck_game_tables_password_needs_public')),
        sa.CheckConstraint(
            'round_time_limit IS NULL OR round_time_limit BETWEEN 30 AND 3600',
            name=op.f('ck_game_tables_round_time_limit_range'),
        ),
        sa.CheckConstraint('turn_cycle >= 0', name=op.f('ck_game_tables_turn_cycle_not_negative')),
        sa.ForeignKeyConstraint(
            ['scenario_id'],
            ['scenarios.asset_id'],
            name=op.f('fk_game_tables_scenario_id_scenarios'),
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['version_id'],
            ['scenario_versions.id'],
            name=op.f('fk_game_tables_version_id_scenario_versions'),
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_game_tables')),
        sa.UniqueConstraint('invite_code', name=op.f('uq_game_tables_invite_code')),
    )
    op.create_index(op.f('ix_game_tables_host_id'), 'game_tables', ['host_id'], unique=False)
    op.create_index(op.f('ix_game_tables_scenario_id'), 'game_tables', ['scenario_id'], unique=False)
    op.create_index(op.f('ix_game_tables_version_id'), 'game_tables', ['version_id'], unique=False)
    op.create_table(
        'listings',
        sa.Column('scenario_id', sa.Uuid(), nullable=False),
        sa.Column('version_id', sa.Uuid(), nullable=True),
        sa.Column('rating', sa.String(length=20), nullable=False),
        sa.Column('min_players', sa.SmallInteger(), nullable=False),
        sa.Column('max_players', sa.SmallInteger(), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('tagline', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('genre', sa.String(length=30), nullable=False),
        sa.Column('tags', postgresql.ARRAY(sa.String(length=20)), nullable=False),
        sa.Column('cover_image_id', sa.Uuid(), nullable=True),
        sa.Column('unlisted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('heart_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("rating IN ('all', 'adult')", name=op.f('ck_listings_rating_allowed')),
        sa.CheckConstraint(
            '(version_id IS NULL) = (published_at IS NULL)', name=op.f('ck_listings_published_together')
        ),
        sa.CheckConstraint(
            '1 <= min_players AND min_players <= max_players AND max_players <= 4',
            name=op.f('ck_listings_players_range'),
        ),
        sa.CheckConstraint('cardinality(tags) <= 10', name=op.f('ck_listings_tags_count')),
        sa.CheckConstraint('char_length(description) <= 5000', name=op.f('ck_listings_description_length')),
        sa.CheckConstraint('heart_count >= 0', name=op.f('ck_listings_heart_count_not_negative')),
        sa.ForeignKeyConstraint(
            ['cover_image_id'], ['portraits.id'], name=op.f('fk_listings_cover_image_id_portraits'), ondelete='RESTRICT'
        ),
        sa.ForeignKeyConstraint(
            ['scenario_id'], ['scenarios.asset_id'], name=op.f('fk_listings_scenario_id_scenarios'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['version_id'],
            ['scenario_versions.id'],
            name=op.f('fk_listings_version_id_scenario_versions'),
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('scenario_id', name=op.f('pk_listings')),
    )
    op.create_index(op.f('ix_listings_cover_image_id'), 'listings', ['cover_image_id'], unique=False)
    op.create_index(op.f('ix_listings_genre'), 'listings', ['genre'], unique=False)
    op.create_index(op.f('ix_listings_published_at'), 'listings', ['published_at'], unique=False)
    op.create_index(
        'ix_listings_tagline_trgm',
        'listings',
        ['tagline'],
        unique=False,
        postgresql_using='gin',
        postgresql_ops={'tagline': 'extensions.gin_trgm_ops'},
    )
    op.create_index(op.f('ix_listings_version_id'), 'listings', ['version_id'], unique=False)
    op.create_table(
        'lore_embeddings',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('version_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('embedding', Vector(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['version_id'],
            ['scenario_versions.id'],
            name=op.f('fk_lore_embeddings_version_id_scenario_versions'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_lore_embeddings')),
        sa.UniqueConstraint('version_id', 'model', 'entry_id', name=op.f('uq_lore_embeddings_version_id')),
    )
    op.create_table(
        'scenario_sanctions',
        sa.Column('version_id', sa.Uuid(), nullable=False),
        sa.Column('scenario_id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('operator_id', sa.Uuid(), nullable=False),
        sa.Column('sanctioned_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ['version_id'],
            ['scenario_versions.id'],
            name=op.f('fk_scenario_sanctions_version_id_scenario_versions'),
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('version_id', name=op.f('pk_scenario_sanctions')),
    )
    op.create_index('ix_scenario_sanctions_owner', 'scenario_sanctions', ['owner_id', 'sanctioned_at'], unique=False)
    op.create_table(
        'campaign_seats',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('carry_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ['carry_id'],
            ['campaign_carries.id'],
            name=op.f('fk_campaign_seats_carry_id_campaign_carries'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_campaign_seats_table_id_game_tables'), ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('table_id', 'user_id', name=op.f('pk_campaign_seats')),
    )
    op.create_index(op.f('ix_campaign_seats_carry_id'), 'campaign_seats', ['carry_id'], unique=False)
    op.create_table(
        'campaign_tables',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('run_id', sa.Uuid(), nullable=False),
        sa.Column('position', sa.SmallInteger(), nullable=False),
        sa.CheckConstraint('0 <= position AND position < 10', name=op.f('ck_campaign_tables_position_range')),
        sa.ForeignKeyConstraint(
            ['run_id'], ['campaign_runs.id'], name=op.f('fk_campaign_tables_run_id_campaign_runs'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_campaign_tables_table_id_game_tables'), ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('table_id', name=op.f('pk_campaign_tables')),
        sa.UniqueConstraint('run_id', 'position', name='uq_campaign_tables_position'),
    )
    op.create_table(
        'listing_hearts',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('scenario_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['scenario_id'],
            ['listings.scenario_id'],
            name=op.f('fk_listing_hearts_scenario_id_listings'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('user_id', 'scenario_id', name=op.f('pk_listing_hearts')),
    )
    op.create_index(op.f('ix_listing_hearts_scenario_id'), 'listing_hearts', ['scenario_id'], unique=False)
    op.create_index('ix_listing_hearts_user_created', 'listing_hearts', ['user_id', 'created_at'], unique=False)
    op.create_table(
        'player_achievements',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('scenario_id', sa.Uuid(), nullable=False),
        sa.Column('achievement_id', sa.String(length=40), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=True),
        sa.Column('earned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['scenario_id'],
            ['scenarios.asset_id'],
            name=op.f('fk_player_achievements_scenario_id_scenarios'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['table_id'],
            ['game_tables.id'],
            name=op.f('fk_player_achievements_table_id_game_tables'),
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('user_id', 'scenario_id', 'achievement_id', name=op.f('pk_player_achievements')),
    )
    op.create_index(
        'ix_player_achievements_scenario_achievement',
        'player_achievements',
        ['scenario_id', 'achievement_id'],
        unique=False,
    )
    op.create_index(op.f('ix_player_achievements_table_id'), 'player_achievements', ['table_id'], unique=False)
    op.create_table(
        'round_memories',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('embedding', Vector(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('round_number >= 1', name=op.f('ck_round_memories_round_number_positive')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_round_memories_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_round_memories')),
        sa.UniqueConstraint('table_id', 'model', 'round_number', name=op.f('uq_round_memories_table_id')),
    )
    op.create_table(
        'table_achievements',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('achievement_id', sa.String(length=40), nullable=False),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('user_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('round_number >= 1', name=op.f('ck_table_achievements_round_number_positive')),
        sa.ForeignKeyConstraint(
            ['table_id'],
            ['game_tables.id'],
            name=op.f('fk_table_achievements_table_id_game_tables'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('table_id', 'achievement_id', name=op.f('pk_table_achievements')),
    )
    op.create_table(
        'table_clocks',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('minutes', sa.Integer(), nullable=False),
        sa.Column('next_step_minutes', sa.Integer(), nullable=True),
        sa.CheckConstraint('minutes >= 0', name=op.f('ck_table_clocks_minutes_not_negative')),
        sa.CheckConstraint('next_step_minutes BETWEEN 0 AND 10080', name=op.f('ck_table_clocks_next_step_range')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_clocks_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('table_id', name=op.f('pk_table_clocks')),
    )
    op.create_table(
        'table_departures',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('character_name', sa.String(length=50), nullable=True),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('last_sequence', sa.Integer(), nullable=False),
        sa.Column('left_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("kind IN ('left', 'kicked', 'dropped')", name=op.f('ck_table_departures_kind_allowed')),
        sa.CheckConstraint('last_sequence >= 1', name=op.f('ck_table_departures_last_sequence_positive')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_departures_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('table_id', 'user_id', name=op.f('pk_table_departures')),
    )
    op.create_index('ix_table_departures_user_id_left_at', 'table_departures', ['user_id', 'left_at'], unique=False)
    op.create_table(
        'table_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=40), nullable=False),
        sa.Column('actor_id', sa.Uuid(), nullable=True),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('caused_by_sequence', sa.Integer(), nullable=True),
        sa.Column('action_group_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('caused_by_sequence < sequence', name=op.f('ck_table_events_cause_comes_first')),
        sa.CheckConstraint('sequence >= 1', name=op.f('ck_table_events_sequence_positive')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_events_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_table_events')),
        sa.UniqueConstraint('table_id', 'sequence', name=op.f('uq_table_events_table_id')),
    )
    op.create_table(
        'table_found_routes',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('from_place', sa.Uuid(), nullable=False),
        sa.Column('to_place', sa.Uuid(), nullable=False),
        sa.Column('found_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['table_id'],
            ['game_tables.id'],
            name=op.f('fk_table_found_routes_table_id_game_tables'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('table_id', 'from_place', 'to_place', name=op.f('pk_table_found_routes')),
    )
    op.create_table(
        'table_happenings',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('moves', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            'npc_moves', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            'doors', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            'traps', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('round_number >= 1', name=op.f('ck_table_happenings_round_number_positive')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_happenings_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('table_id', 'entry_id', name=op.f('pk_table_happenings')),
    )
    op.create_table(
        'table_members',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('character_name', sa.String(length=50), nullable=True),
        sa.Column('character_description', sa.Text(), nullable=False),
        sa.Column('character_mode', sa.String(length=20), nullable=True),
        sa.Column('pregen_index', sa.SmallInteger(), nullable=True),
        sa.Column('abilities', postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True),
        sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('friendly_fire', sa.String(length=20), server_default=sa.text("'off'"), nullable=False),
        sa.CheckConstraint(
            "(abilities IS NOT NULL) = (character_mode IS NOT NULL AND character_mode NOT IN ('pregen', 'custom'))",
            name=op.f('ck_table_members_abilities_need_player_made_mode'),
        ),
        sa.CheckConstraint(
            "(pregen_index IS NOT NULL) = (character_mode IS NOT DISTINCT FROM 'pregen')",
            name=op.f('ck_table_members_pregen_needs_pregen_mode'),
        ),
        sa.CheckConstraint(
            "abilities IS NULL OR jsonb_typeof(abilities) = 'object'", name=op.f('ck_table_members_abilities_is_object')
        ),
        sa.CheckConstraint(
            "character_mode IN ('pregen', 'custom', 'manual', 'point_buy', 'rolled')",
            name=op.f('ck_table_members_character_mode_allowed'),
        ),
        sa.CheckConstraint(
            "friendly_fire IN ('off', 'prank', 'full')", name=op.f('ck_table_members_friendly_fire_allowed')
        ),
        sa.CheckConstraint(
            '(character_mode IS NULL) = (character_name IS NULL)',
            name=op.f('ck_table_members_character_mode_needs_character'),
        ),
        sa.CheckConstraint(
            'char_length(character_description) <= 1000', name=op.f('ck_table_members_description_length')
        ),
        sa.CheckConstraint(
            'character_name IS NOT NULL OR pregen_index IS NULL', name=op.f('ck_table_members_pregen_needs_character')
        ),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_members_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('table_id', 'user_id', name=op.f('pk_table_members')),
        sa.UniqueConstraint('table_id', 'pregen_index', name=op.f('uq_table_members_table_id')),
    )
    op.create_index(op.f('ix_table_members_user_id'), 'table_members', ['user_id'], unique=False)
    op.create_table(
        'table_messages',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('character_name', sa.String(length=50), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('char_length(content) <= 500', name=op.f('ck_table_messages_content_length')),
        sa.CheckConstraint('sequence >= 1', name=op.f('ck_table_messages_sequence_positive')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_messages_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_table_messages')),
        sa.UniqueConstraint('table_id', 'sequence', name=op.f('uq_table_messages_table_id')),
    )
    op.create_table(
        'table_monsters',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('monster_id', sa.Uuid(), nullable=False),
        sa.Column('number', sa.SmallInteger(), nullable=False),
        sa.Column('place_id', sa.Uuid(), nullable=False),
        sa.Column('home_place_id', sa.Uuid(), nullable=False),
        sa.Column('patrol_leg', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('abilities', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('max_hp', sa.SmallInteger(), nullable=False),
        sa.Column('hp', sa.SmallInteger(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default=sa.text("'alive'"), nullable=False),
        sa.Column('engaged_round', sa.Integer(), nullable=True),
        sa.Column('fought_round', sa.Integer(), nullable=True),
        sa.Column('last_foe', sa.Uuid(), nullable=True),
        sa.Column('surprise', sa.String(length=20), nullable=True),
        sa.Column(
            'resources', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column('xp_given', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("(status = 'alive') = (hp > 0)", name=op.f('ck_table_monsters_alive_when_hp')),
        sa.CheckConstraint("jsonb_typeof(abilities) = 'object'", name=op.f('ck_table_monsters_abilities_is_object')),
        sa.CheckConstraint("jsonb_typeof(resources) = 'object'", name=op.f('ck_table_monsters_resources_is_object')),
        sa.CheckConstraint("status IN ('alive', 'downed', 'dead')", name=op.f('ck_table_monsters_status_allowed')),
        sa.CheckConstraint(
            "surprise IN ('none', 'monsters', 'party')", name=op.f('ck_table_monsters_surprise_allowed')
        ),
        sa.CheckConstraint(
            'engaged_round IS NULL OR engaged_round >= 1', name=op.f('ck_table_monsters_engaged_round_positive')
        ),
        sa.CheckConstraint(
            'fought_round IS NULL OR fought_round >= 1', name=op.f('ck_table_monsters_fought_round_positive')
        ),
        sa.CheckConstraint('hp BETWEEN 0 AND max_hp', name=op.f('ck_table_monsters_hp_range')),
        sa.CheckConstraint('max_hp >= 1', name=op.f('ck_table_monsters_max_hp_positive')),
        sa.CheckConstraint('number >= 1', name=op.f('ck_table_monsters_number_positive')),
        sa.CheckConstraint('patrol_leg >= 0', name=op.f('ck_table_monsters_patrol_leg_not_negative')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_monsters_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_table_monsters')),
        sa.UniqueConstraint('table_id', 'monster_id', 'number', name=op.f('uq_table_monsters_table_id')),
    )
    op.create_table(
        'table_npcs',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('abilities', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('max_hp', sa.SmallInteger(), nullable=False),
        sa.Column('hp', sa.SmallInteger(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default=sa.text("'alive'"), nullable=False),
        sa.Column('named_round', sa.Integer(), nullable=True),
        sa.Column('attitude', sa.String(length=20), server_default=sa.text("'neutral'"), nullable=False),
        sa.Column('fell_round', sa.Integer(), nullable=True),
        sa.Column('fought_round', sa.Integer(), nullable=True),
        sa.Column('robbed_round', sa.Integer(), nullable=True),
        sa.Column(
            'resources', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column('place_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("(status = 'alive') = (hp > 0)", name=op.f('ck_table_npcs_alive_when_hp')),
        sa.CheckConstraint(
            "attitude IN ('friendly', 'neutral', 'wary', 'hostile')", name=op.f('ck_table_npcs_attitude_allowed')
        ),
        sa.CheckConstraint("jsonb_typeof(abilities) = 'object'", name=op.f('ck_table_npcs_abilities_is_object')),
        sa.CheckConstraint("jsonb_typeof(resources) = 'object'", name=op.f('ck_table_npcs_resources_is_object')),
        sa.CheckConstraint("status IN ('alive', 'downed', 'dead')", name=op.f('ck_table_npcs_status_allowed')),
        sa.CheckConstraint('fell_round IS NULL OR fell_round >= 1', name=op.f('ck_table_npcs_fell_round_positive')),
        sa.CheckConstraint(
            'fought_round IS NULL OR fought_round >= 1', name=op.f('ck_table_npcs_fought_round_positive')
        ),
        sa.CheckConstraint('hp BETWEEN 0 AND max_hp', name=op.f('ck_table_npcs_hp_range')),
        sa.CheckConstraint('max_hp >= 1', name=op.f('ck_table_npcs_max_hp_positive')),
        sa.CheckConstraint('named_round IS NULL OR named_round >= 1', name=op.f('ck_table_npcs_named_round_positive')),
        sa.CheckConstraint(
            'robbed_round IS NULL OR robbed_round >= 1', name=op.f('ck_table_npcs_robbed_round_positive')
        ),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_npcs_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('table_id', 'entry_id', name=op.f('pk_table_npcs')),
    )
    op.create_table(
        'table_place_items',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('slot', sa.SmallInteger(), nullable=False),
        sa.Column('place_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('count', sa.SmallInteger(), nullable=False),
        sa.Column('hidden', sa.Boolean(), nullable=False),
        sa.CheckConstraint('count >= 0', name=op.f('ck_table_place_items_count_not_negative')),
        sa.CheckConstraint('slot >= 0', name=op.f('ck_table_place_items_slot_not_negative')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_place_items_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('table_id', 'slot', name=op.f('pk_table_place_items')),
    )
    op.create_table(
        'table_quests',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('due_at', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('hidden', 'active', 'succeeded', 'failed')", name=op.f('ck_table_quests_status_allowed')
        ),
        sa.CheckConstraint('due_at IS NULL OR due_at >= 0', name=op.f('ck_table_quests_due_at_not_negative')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_quests_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('table_id', 'entry_id', name=op.f('pk_table_quests')),
    )
    op.create_table(
        'table_rolls',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('dice', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('scores', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('times_rolled', sa.SmallInteger(), nullable=False),
        sa.Column('character_number', sa.SmallInteger(), server_default=sa.text('1'), nullable=False),
        sa.Column('reroll_granted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('rolled_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(dice) = 'array' AND jsonb_typeof(scores) = 'array'",
            name=op.f('ck_table_rolls_rolls_are_arrays'),
        ),
        sa.CheckConstraint('character_number >= 1', name=op.f('ck_table_rolls_character_number_positive')),
        sa.CheckConstraint('times_rolled >= 1', name=op.f('ck_table_rolls_times_rolled_positive')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_rolls_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('table_id', 'user_id', name=op.f('pk_table_rolls')),
    )
    op.create_table(
        'table_rounds',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('cycle', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.Uuid(), nullable=True),
        sa.Column('scene', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deadline_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('narration_model', sa.String(length=48), nullable=True),
        sa.Column('input_step', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('output_step', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('announced_credits', sa.String(length=32), nullable=True),
        sa.Column('announced_tier', sa.String(length=20), nullable=True),
        sa.Column('closing_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('narration_failed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('auto_retries', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('narration_failures', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column(
            'death_saves', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'"), nullable=False
        ),
        sa.Column(
            'expired_quests', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'"), nullable=False
        ),
        sa.Column('turns', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'"), nullable=False),
        sa.Column('arrivals', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'"), nullable=False),
        sa.Column('moves', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('narration_style', sa.String(length=20), nullable=True),
        sa.Column('reverted_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "narration_style IN ('none', 'classic', 'web_novel', 'hardboiled', 'emotional', 'action', 'dopamine', "
            "'literary')",
            name=op.f('ck_table_rounds_narration_style_allowed'),
        ),
        sa.CheckConstraint('auto_retries >= 0', name=op.f('ck_table_rounds_auto_retries_not_negative')),
        sa.CheckConstraint('cycle >= 1', name=op.f('ck_table_rounds_cycle_positive')),
        sa.CheckConstraint('input_step BETWEEN 0 AND 2', name=op.f('ck_table_rounds_input_step_range')),
        sa.CheckConstraint('narration_failures >= 0', name=op.f('ck_table_rounds_narration_failures_not_negative')),
        sa.CheckConstraint('number >= 1', name=op.f('ck_table_rounds_number_positive')),
        sa.CheckConstraint('output_step BETWEEN 0 AND 2', name=op.f('ck_table_rounds_output_step_range')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_rounds_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_table_rounds')),
    )
    op.create_index(
        'ix_table_rounds_failed',
        'table_rounds',
        ['narration_failed_at'],
        unique=False,
        postgresql_where='narration_failed_at IS NOT NULL AND closed_at IS NULL',
    )
    op.create_index(
        'ix_table_rounds_open_deadline',
        'table_rounds',
        ['deadline_at'],
        unique=False,
        postgresql_where='closed_at IS NULL AND closing_at IS NULL',
    )
    op.create_index(op.f('ix_table_rounds_table_id'), 'table_rounds', ['table_id'], unique=False)
    op.create_index(
        'uq_table_rounds_number',
        'table_rounds',
        ['table_id', 'number'],
        unique=True,
        postgresql_where='reverted_at IS NULL',
    )
    op.create_index(
        'uq_table_rounds_open', 'table_rounds', ['table_id'], unique=True, postgresql_where='closed_at IS NULL'
    )
    op.create_table(
        'table_route_locks',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('from_place', sa.Uuid(), nullable=False),
        sa.Column('to_place', sa.Uuid(), nullable=False),
        sa.Column('locked', sa.Boolean(), nullable=False),
        sa.Column('barred', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('broken', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('lock_item', sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            'NOT broken OR (NOT locked AND NOT barred)', name=op.f('ck_table_route_locks_broken_is_open')
        ),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_route_locks_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('table_id', 'from_place', 'to_place', name=op.f('pk_table_route_locks')),
        sa.UniqueConstraint('table_id', 'lock_item', name=op.f('uq_table_route_locks_table_id')),
    )
    op.create_table(
        'table_snapshots',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=True),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('model', sa.String(length=80), nullable=False),
        sa.Column('reference', sa.String(length=80), nullable=False),
        sa.Column('price_code', sa.String(length=120), nullable=False),
        sa.Column('billing_status', sa.String(length=20), nullable=False),
        sa.Column('settle_attempts', sa.Integer(), nullable=False),
        sa.Column('next_settle_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('outcome', sa.String(length=20), nullable=True),
        sa.Column('error_code', sa.String(length=60), nullable=True),
        sa.Column('image_id', sa.Uuid(), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "billing_status IN ('pending', 'held', 'declined', 'capture_due', 'release_due', 'captured', 'released', "
            "'failed')",
            name=op.f('ck_table_snapshots_billing_status_allowed'),
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('ready', 'failed')", name=op.f('ck_table_snapshots_outcome_allowed')
        ),
        sa.CheckConstraint('round_number >= 1', name=op.f('ck_table_snapshots_round_number_positive')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_snapshots_table_id_game_tables'), ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_table_snapshots')),
        sa.UniqueConstraint('reference', name=op.f('uq_table_snapshots_reference')),
    )
    op.create_index(
        'ix_table_snapshots_billing_status_next_settle_at',
        'table_snapshots',
        ['billing_status', 'next_settle_at'],
        unique=False,
    )
    op.create_index('ix_table_snapshots_owner_created', 'table_snapshots', ['owner_id', 'created_at'], unique=False)
    op.create_index('ix_table_snapshots_table_created', 'table_snapshots', ['table_id', 'created_at'], unique=False)
    op.create_index(
        'uq_table_snapshots_one_drawing',
        'table_snapshots',
        ['table_id'],
        unique=True,
        postgresql_where=sa.text('outcome IS NULL'),
    )
    op.create_table(
        'table_traps',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('place_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('set_by', sa.Uuid(), nullable=True),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('found_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_reason', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("ended_reason IN ('sprung', 'disarmed')", name=op.f('ck_table_traps_ended_reason_allowed')),
        sa.CheckConstraint('(ended_at IS NULL) = (ended_reason IS NULL)', name=op.f('ck_table_traps_end_has_reason')),
        sa.CheckConstraint('round_number >= 1', name=op.f('ck_table_traps_round_number_positive')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_traps_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_table_traps')),
    )
    op.create_index(op.f('ix_table_traps_table_id'), 'table_traps', ['table_id'], unique=False)
    op.create_table(
        'table_visits',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('visited_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_visits_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('table_id', 'entry_id', name=op.f('pk_table_visits')),
    )
    op.create_table(
        'table_whispers',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('sender_id', sa.Uuid(), nullable=False),
        sa.Column('recipient_id', sa.Uuid(), nullable=False),
        sa.Column('sender_character_name', sa.String(length=50), nullable=True),
        sa.Column('recipient_character_name', sa.String(length=50), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('gm_visible', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('char_length(content) <= 500', name=op.f('ck_table_whispers_content_length')),
        sa.CheckConstraint('owner_id IN (sender_id, recipient_id)', name=op.f('ck_table_whispers_owner_is_party')),
        sa.CheckConstraint('round_number >= 1', name=op.f('ck_table_whispers_round_number_positive')),
        sa.CheckConstraint('sender_id <> recipient_id', name=op.f('ck_table_whispers_not_to_self')),
        sa.CheckConstraint('sequence >= 1', name=op.f('ck_table_whispers_sequence_positive')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_whispers_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_table_whispers')),
        sa.UniqueConstraint('table_id', 'owner_id', 'sequence', name=op.f('uq_table_whispers_table_id')),
    )
    op.create_index(
        'ix_table_whispers_gm',
        'table_whispers',
        ['table_id', 'round_number'],
        unique=False,
        postgresql_where=sa.text('gm_visible AND owner_id = sender_id'),
    )
    op.create_table(
        'narration_charges',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('round_id', sa.Uuid(), nullable=False),
        sa.Column('payer_id', sa.Uuid(), nullable=False),
        sa.Column('reference', sa.String(length=200), nullable=False),
        sa.Column('renewals', sa.Integer(), server_default='0', nullable=False),
        sa.Column('price_code', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_error', sa.String(length=40), nullable=True),
        sa.Column('held_credits', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'held', 'short', 'capture_due', 'captured', 'release_due', 'released', 'failed')",
            name=op.f('ck_narration_charges_status_allowed'),
        ),
        sa.CheckConstraint('attempts >= 0', name=op.f('ck_narration_charges_attempts_not_negative')),
        sa.ForeignKeyConstraint(
            ['round_id'],
            ['table_rounds.id'],
            name=op.f('fk_narration_charges_round_id_table_rounds'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_narration_charges')),
        sa.UniqueConstraint('reference', name=op.f('uq_narration_charges_reference')),
        sa.UniqueConstraint('round_id', 'payer_id', name=op.f('uq_narration_charges_round_id')),
    )
    op.create_index(
        'ix_narration_charges_due',
        'narration_charges',
        ['next_attempt_at'],
        unique=False,
        postgresql_where="status IN ('pending', 'held', 'capture_due', 'release_due')",
    )
    op.create_index(
        'ix_narration_charges_open',
        'narration_charges',
        ['round_id'],
        unique=False,
        postgresql_where="status IN ('pending', 'held', 'short')",
    )
    op.create_table(
        'round_declarations',
        sa.Column('round_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('character_name', sa.String(length=50), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('action', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('outcome', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('char_length(content) <= 1000', name=op.f('ck_round_declarations_content_length')),
        sa.ForeignKeyConstraint(
            ['round_id'],
            ['table_rounds.id'],
            name=op.f('fk_round_declarations_round_id_table_rounds'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('round_id', 'user_id', name=op.f('pk_round_declarations')),
    )
    op.create_table(
        'round_snapshots',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('round_id', sa.Uuid(), nullable=False),
        sa.Column('state', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('taken_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['round_id'], ['table_rounds.id'], name=op.f('fk_round_snapshots_round_id_table_rounds'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_round_snapshots_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('table_id', name=op.f('pk_round_snapshots')),
    )
    op.create_index(op.f('ix_round_snapshots_round_id'), 'round_snapshots', ['round_id'], unique=False)
    op.create_table(
        'table_monster_items',
        sa.Column('monster_id', sa.Uuid(), nullable=False),
        sa.Column('slot', sa.SmallInteger(), nullable=False),
        sa.Column('count', sa.SmallInteger(), nullable=False),
        sa.CheckConstraint('count >= 0', name=op.f('ck_table_monster_items_count_not_negative')),
        sa.CheckConstraint('slot >= 0', name=op.f('ck_table_monster_items_slot_not_negative')),
        sa.ForeignKeyConstraint(
            ['monster_id'],
            ['table_monsters.id'],
            name=op.f('fk_table_monster_items_monster_id_table_monsters'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('monster_id', 'slot', name=op.f('pk_table_monster_items')),
    )
    op.create_table(
        'table_npc_items',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('slot', sa.SmallInteger(), nullable=False),
        sa.Column('count', sa.SmallInteger(), nullable=False),
        sa.CheckConstraint('count >= 0', name=op.f('ck_table_npc_items_count_not_negative')),
        sa.CheckConstraint('slot >= 0', name=op.f('ck_table_npc_items_slot_not_negative')),
        sa.ForeignKeyConstraint(
            ['table_id', 'entry_id'],
            ['table_npcs.table_id', 'table_npcs.entry_id'],
            name=op.f('fk_table_npc_items_table_id_table_npcs'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('table_id', 'entry_id', 'slot', name=op.f('pk_table_npc_items')),
    )
    op.create_table(
        'table_sheets',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('number', sa.SmallInteger(), server_default=sa.text('1'), nullable=False),
        sa.Column('character_name', sa.String(length=50), nullable=False),
        sa.Column('pregen_index', sa.SmallInteger(), nullable=True),
        sa.Column('abilities', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('max_hp', sa.SmallInteger(), nullable=False),
        sa.Column('hp', sa.SmallInteger(), nullable=False),
        sa.Column('death_successes', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('death_failures', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('downed_by_big_hit', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('died_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('place_id', sa.Uuid(), nullable=True),
        sa.Column('money', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column(
            'resources', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            'skills', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            'resistances',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column('xp', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('points', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("jsonb_typeof(resistances) = 'array'", name=op.f('ck_table_sheets_resistances_is_array')),
        sa.CheckConstraint("jsonb_typeof(resources) = 'object'", name=op.f('ck_table_sheets_resources_is_object')),
        sa.CheckConstraint("jsonb_typeof(skills) = 'array'", name=op.f('ck_table_sheets_skills_is_array')),
        sa.CheckConstraint(
            'death_successes >= 0 AND death_failures >= 0', name=op.f('ck_table_sheets_death_saves_not_negative')
        ),
        sa.CheckConstraint(
            'hp = 0 OR (death_successes = 0 AND death_failures = 0 AND died_at IS NULL)',
            name=op.f('ck_table_sheets_death_only_when_downed'),
        ),
        sa.CheckConstraint('hp BETWEEN 0 AND max_hp', name=op.f('ck_table_sheets_hp_range')),
        sa.CheckConstraint('max_hp >= 1', name=op.f('ck_table_sheets_max_hp_positive')),
        sa.CheckConstraint('money BETWEEN 0 AND 1000000', name=op.f('ck_table_sheets_money_range')),
        sa.CheckConstraint('number >= 1', name=op.f('ck_table_sheets_number_positive')),
        sa.CheckConstraint('points >= 0', name=op.f('ck_table_sheets_points_not_negative')),
        sa.CheckConstraint('xp >= 0', name=op.f('ck_table_sheets_xp_not_negative')),
        sa.ForeignKeyConstraint(
            ['table_id', 'user_id'],
            ['table_members.table_id', 'table_members.user_id'],
            name=op.f('fk_table_sheets_table_id_table_members'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_table_sheets')),
        sa.UniqueConstraint('table_id', 'pregen_index', name='uq_table_sheets_pregen'),
        sa.UniqueConstraint('table_id', 'user_id', 'number', name='uq_table_sheets_number'),
    )
    op.create_index(
        'uq_table_sheets_living',
        'table_sheets',
        ['table_id', 'user_id'],
        unique=True,
        postgresql_where='died_at IS NULL',
    )
    op.create_table(
        'table_injuries',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('sheet_id', sa.Uuid(), nullable=True),
        sa.Column('npc_entry_id', sa.Uuid(), nullable=True),
        sa.Column('monster_id', sa.Uuid(), nullable=True),
        sa.Column('injury', sa.String(length=20), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('ends_after_round', sa.Integer(), nullable=True),
        sa.Column('heals_at', sa.Integer(), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "source IN ('injury_table', 'called_shot', 'aftermath', 'item', 'resource', 'skill', 'attack', 'trap')",
            name=op.f('ck_table_injuries_source_allowed'),
        ),
        sa.CheckConstraint(
            'ends_after_round IS NULL OR ends_after_round > round_number',
            name=op.f('ck_table_injuries_ends_after_start'),
        ),
        sa.CheckConstraint('ends_after_round IS NULL OR heals_at IS NULL', name=op.f('ck_table_injuries_one_end')),
        sa.CheckConstraint('heals_at IS NULL OR heals_at >= 0', name=op.f('ck_table_injuries_heals_at_not_negative')),
        sa.CheckConstraint(
            'num_nonnulls(sheet_id, npc_entry_id, monster_id) = 1', name=op.f('ck_table_injuries_one_holder')
        ),
        sa.CheckConstraint('round_number >= 1', name=op.f('ck_table_injuries_round_number_positive')),
        sa.ForeignKeyConstraint(
            ['monster_id'],
            ['table_monsters.id'],
            name=op.f('fk_table_injuries_monster_id_table_monsters'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['sheet_id'], ['table_sheets.id'], name=op.f('fk_table_injuries_sheet_id_table_sheets'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['table_id', 'npc_entry_id'],
            ['table_npcs.table_id', 'table_npcs.entry_id'],
            name=op.f('fk_table_injuries_table_id_table_npcs'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_injuries_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_table_injuries')),
    )
    op.create_index(
        'ix_table_injuries_active', 'table_injuries', ['table_id'], unique=False, postgresql_where='ended_at IS NULL'
    )
    op.create_index('ix_table_injuries_monster_id', 'table_injuries', ['monster_id'], unique=False)
    op.create_index('ix_table_injuries_npc', 'table_injuries', ['table_id', 'npc_entry_id'], unique=False)
    op.create_index('ix_table_injuries_sheet_id', 'table_injuries', ['sheet_id'], unique=False)
    op.create_table(
        'table_items',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('sheet_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('count', sa.SmallInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('count BETWEEN 1 AND 99', name=op.f('ck_table_items_count_range')),
        sa.ForeignKeyConstraint(
            ['sheet_id'], ['table_sheets.id'], name=op.f('fk_table_items_sheet_id_table_sheets'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_items_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_table_items')),
        sa.UniqueConstraint('sheet_id', 'entry_id', name='uq_table_items_entry'),
    )
    op.create_index(op.f('ix_table_items_table_id'), 'table_items', ['table_id'], unique=False)
    op.create_table(
        'table_worn',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('sheet_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.Uuid(), nullable=False),
        sa.Column('slots', postgresql.ARRAY(sa.String(length=20)), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('cardinality(slots) >= 1', name=op.f('ck_table_worn_slots_not_empty')),
        sa.ForeignKeyConstraint(
            ['sheet_id'], ['table_sheets.id'], name=op.f('fk_table_worn_sheet_id_table_sheets'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_worn_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_table_worn')),
    )
    op.create_index(op.f('ix_table_worn_sheet_id'), 'table_worn', ['sheet_id'], unique=False)
    op.create_index(op.f('ix_table_worn_table_id'), 'table_worn', ['table_id'], unique=False)
    for table in APPEND_ONLY:
        forbid_rewrites(table)


def downgrade() -> None:
    for table in APPEND_ONLY:
        allow_rewrites(table)
    op.drop_index(op.f('ix_table_worn_table_id'), table_name='table_worn')
    op.drop_index(op.f('ix_table_worn_sheet_id'), table_name='table_worn')
    op.drop_table('table_worn')
    op.drop_index(op.f('ix_table_items_table_id'), table_name='table_items')
    op.drop_table('table_items')
    op.drop_index('ix_table_injuries_sheet_id', table_name='table_injuries')
    op.drop_index('ix_table_injuries_npc', table_name='table_injuries')
    op.drop_index('ix_table_injuries_monster_id', table_name='table_injuries')
    op.drop_index('ix_table_injuries_active', table_name='table_injuries', postgresql_where='ended_at IS NULL')
    op.drop_table('table_injuries')
    op.drop_index('uq_table_sheets_living', table_name='table_sheets', postgresql_where='died_at IS NULL')
    op.drop_table('table_sheets')
    op.drop_table('table_npc_items')
    op.drop_table('table_monster_items')
    op.drop_index(op.f('ix_round_snapshots_round_id'), table_name='round_snapshots')
    op.drop_table('round_snapshots')
    op.drop_table('round_declarations')
    op.drop_index(
        'ix_narration_charges_open',
        table_name='narration_charges',
        postgresql_where="status IN ('pending', 'held', 'short')",
    )
    op.drop_index(
        'ix_narration_charges_due',
        table_name='narration_charges',
        postgresql_where="status IN ('pending', 'held', 'capture_due', 'release_due')",
    )
    op.drop_table('narration_charges')
    op.drop_index(
        'ix_table_whispers_gm',
        table_name='table_whispers',
        postgresql_where=sa.text('gm_visible AND owner_id = sender_id'),
    )
    op.drop_table('table_whispers')
    op.drop_table('table_visits')
    op.drop_index(op.f('ix_table_traps_table_id'), table_name='table_traps')
    op.drop_table('table_traps')
    op.drop_index(
        'uq_table_snapshots_one_drawing', table_name='table_snapshots', postgresql_where=sa.text('outcome IS NULL')
    )
    op.drop_index('ix_table_snapshots_table_created', table_name='table_snapshots')
    op.drop_index('ix_table_snapshots_owner_created', table_name='table_snapshots')
    op.drop_index('ix_table_snapshots_billing_status_next_settle_at', table_name='table_snapshots')
    op.drop_table('table_snapshots')
    op.drop_table('table_route_locks')
    op.drop_index('uq_table_rounds_open', table_name='table_rounds', postgresql_where='closed_at IS NULL')
    op.drop_index('uq_table_rounds_number', table_name='table_rounds', postgresql_where='reverted_at IS NULL')
    op.drop_index(op.f('ix_table_rounds_table_id'), table_name='table_rounds')
    op.drop_index(
        'ix_table_rounds_open_deadline',
        table_name='table_rounds',
        postgresql_where='closed_at IS NULL AND closing_at IS NULL',
    )
    op.drop_index(
        'ix_table_rounds_failed',
        table_name='table_rounds',
        postgresql_where='narration_failed_at IS NOT NULL AND closed_at IS NULL',
    )
    op.drop_table('table_rounds')
    op.drop_table('table_rolls')
    op.drop_table('table_quests')
    op.drop_table('table_place_items')
    op.drop_table('table_npcs')
    op.drop_table('table_monsters')
    op.drop_table('table_messages')
    op.drop_index(op.f('ix_table_members_user_id'), table_name='table_members')
    op.drop_table('table_members')
    op.drop_table('table_happenings')
    op.drop_table('table_found_routes')
    op.drop_table('table_events')
    op.drop_index('ix_table_departures_user_id_left_at', table_name='table_departures')
    op.drop_table('table_departures')
    op.drop_table('table_clocks')
    op.drop_table('table_achievements')
    op.drop_table('round_memories')
    op.drop_index(op.f('ix_player_achievements_table_id'), table_name='player_achievements')
    op.drop_index('ix_player_achievements_scenario_achievement', table_name='player_achievements')
    op.drop_table('player_achievements')
    op.drop_index('ix_listing_hearts_user_created', table_name='listing_hearts')
    op.drop_index(op.f('ix_listing_hearts_scenario_id'), table_name='listing_hearts')
    op.drop_table('listing_hearts')
    op.drop_table('campaign_tables')
    op.drop_index(op.f('ix_campaign_seats_carry_id'), table_name='campaign_seats')
    op.drop_table('campaign_seats')
    op.drop_index('ix_scenario_sanctions_owner', table_name='scenario_sanctions')
    op.drop_table('scenario_sanctions')
    op.drop_table('lore_embeddings')
    op.drop_index(op.f('ix_listings_version_id'), table_name='listings')
    op.drop_index(
        'ix_listings_tagline_trgm',
        table_name='listings',
        postgresql_using='gin',
        postgresql_ops={'tagline': 'extensions.gin_trgm_ops'},
    )
    op.drop_index(op.f('ix_listings_published_at'), table_name='listings')
    op.drop_index(op.f('ix_listings_genre'), table_name='listings')
    op.drop_index(op.f('ix_listings_cover_image_id'), table_name='listings')
    op.drop_table('listings')
    op.drop_index(op.f('ix_game_tables_version_id'), table_name='game_tables')
    op.drop_index(op.f('ix_game_tables_scenario_id'), table_name='game_tables')
    op.drop_index(op.f('ix_game_tables_host_id'), table_name='game_tables')
    op.drop_table('game_tables')
    op.drop_table('campaign_quest_results')
    op.drop_index(op.f('ix_campaign_carries_user_id'), table_name='campaign_carries')
    op.drop_table('campaign_carries')
    op.drop_table('scenario_versions')
    op.drop_index(op.f('ix_scenario_players_user_id'), table_name='scenario_players')
    op.drop_table('scenario_players')
    op.drop_index(op.f('ix_scenario_lorebooks_lorebook_id'), table_name='scenario_lorebooks')
    op.drop_table('scenario_lorebooks')
    op.drop_index(op.f('ix_scenario_bestiaries_bestiary_id'), table_name='scenario_bestiaries')
    op.drop_table('scenario_bestiaries')
    op.drop_index(op.f('ix_campaign_runs_version_id'), table_name='campaign_runs')
    op.drop_index(op.f('ix_campaign_runs_host_id'), table_name='campaign_runs')
    op.drop_index(op.f('ix_campaign_runs_campaign_id'), table_name='campaign_runs')
    op.drop_table('campaign_runs')
    op.drop_index(op.f('ix_campaign_episodes_scenario_id'), table_name='campaign_episodes')
    op.drop_table('campaign_episodes')
    op.drop_index(op.f('ix_banners_scenario_id'), table_name='banners')
    op.drop_table('banners')
    op.drop_index(op.f('ix_scenarios_world_id'), table_name='scenarios')
    op.drop_index(op.f('ix_scenarios_rulebook_id'), table_name='scenarios')
    op.drop_table('scenarios')
    op.drop_index(op.f('ix_monsters_bestiary_id'), table_name='monsters')
    op.drop_table('monsters')
    op.drop_index(op.f('ix_lore_entries_lorebook_id'), table_name='lore_entries')
    op.drop_table('lore_entries')
    op.drop_table('campaign_versions')
    op.drop_table('worlds')
    op.drop_table('rulebooks')
    op.drop_index(op.f('ix_reference_embeddings_reference_id'), table_name='reference_embeddings')
    op.drop_table('reference_embeddings')
    op.drop_table('lorebooks')
    op.drop_table('campaigns')
    op.drop_table('bestiaries')
    op.drop_index('ix_ai_model_snapshots_model_slug_id', table_name='ai_model_snapshots')
    op.drop_table('ai_model_snapshots')
    op.drop_index('ix_ai_model_costs_model_slug_effective_from', table_name='ai_model_costs')
    op.drop_table('ai_model_costs')
    op.drop_table('reference_entries')
    op.drop_table('publishing_bans')
    op.drop_index('ix_portraits_owner_created', table_name='portraits')
    op.drop_table('portraits')
    op.drop_index(op.f('ix_personas_owner_id'), table_name='personas')
    op.drop_table('personas')
    op.drop_index(
        'ix_outgoing_notifications_due',
        table_name='outgoing_notifications',
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_table('outgoing_notifications')
    op.drop_index('ix_operator_reads_target', table_name='operator_reads')
    op.drop_index('ix_operator_reads_operator', table_name='operator_reads')
    op.drop_table('operator_reads')
    op.drop_index('ix_operator_actions_target', table_name='operator_actions')
    op.drop_index('ix_operator_actions_operator', table_name='operator_actions')
    op.drop_table('operator_actions')
    op.drop_index(
        'ix_assets_title_trgm',
        table_name='assets',
        postgresql_using='gin',
        postgresql_ops={'title': 'extensions.gin_trgm_ops'},
    )
    op.drop_index(op.f('ix_assets_owner_id'), table_name='assets')
    op.drop_table('assets')
    op.drop_index('uq_ai_models_vendor_fallback', table_name='ai_models', postgresql_where=sa.text('vendor_fallback'))
    op.drop_table('ai_models')
    op.drop_index('ix_ai_invocations_text_kept', table_name='ai_invocations', postgresql_where='text IS NOT NULL')
    op.drop_index('ix_ai_invocations_table_id_created_at', table_name='ai_invocations')
    op.drop_table('ai_invocations')
