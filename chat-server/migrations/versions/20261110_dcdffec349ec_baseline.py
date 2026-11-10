"""baseline

Revision ID: dcdffec349ec
Revises:
Create Date: 2026-11-10 20:21:45.632314

첫 배포 전에 쌓인 마이그레이션 27개를 하나로 합친 기준선(#1273). 빈 스키마에 지금의 표를 한 번에 만든다.
모델에서 자동으로 만든 뒤, 모델이 모르는 것(운영자 기록을 고치지 못하게 하는 함수와 트리거)을 손으로 더했다.
옛 사슬로 만든 스키마와 같은지는 tools/compare_schemas.py 로 견주었다.
옛 마이그레이션이 하던 데이터 옮기기는 빈 DB 에서 할 일이 없어 넣지 않았다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = 'dcdffec349ec'
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
    op.create_table(
        'character_players',
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('character_source', sa.Uuid(), nullable=False),
        sa.Column('first_played_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('owner_id', 'character_source', name=op.f('pk_character_players')),
    )
    op.create_index(
        op.f('ix_character_players_character_source'), 'character_players', ['character_source'], unique=False
    )
    op.create_table(
        'characters',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('source_id', sa.Uuid(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('rating', sa.String(length=10), nullable=False),
        sa.Column('document', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("rating IN ('all', 'adult')", name=op.f('ck_characters_rating_allowed')),
        sa.CheckConstraint('version >= 1', name=op.f('ck_characters_version_positive')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_characters')),
        sa.UniqueConstraint('owner_id', 'source_id', 'version', name='uq_characters_owner_source_version'),
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
            "action IN ('report_action', 'report_dismiss')", name=op.f('ck_operator_actions_action_allowed')
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
        sa.Column('reason', sa.String(length=200), nullable=False),
        sa.Column('request_id', sa.String(length=128), nullable=True),
        sa.CheckConstraint("btrim(reason) <> ''", name=op.f('ck_operator_reads_reason_not_blank')),
        sa.CheckConstraint("target_kind IN ('message_report')", name=op.f('ck_operator_reads_target_kind_allowed')),
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
        'scene_unlocks',
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('character_source', sa.Uuid(), nullable=False),
        sa.Column('scene_id', sa.String(length=40), nullable=False),
        sa.Column('unlocked_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('owner_id', 'character_source', 'scene_id', name=op.f('pk_scene_unlocks')),
    )
    op.create_index('ix_scene_unlocks_owner_unlocked', 'scene_unlocks', ['owner_id', 'unlocked_at'], unique=False)
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
        'conversations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('character_id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('model_slug', sa.String(length=48), nullable=True),
        sa.Column('start_title', sa.Text(), nullable=False),
        sa.Column('start_situation', sa.Text(), nullable=False),
        sa.Column('start_hour', sa.SmallInteger(), server_default='12', nullable=False),
        sa.Column('active_leaf_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('generating_since', sa.DateTime(timezone=True), nullable=True),
        sa.Column('summarizing_since', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('start_hour BETWEEN 0 AND 23', name=op.f('ck_conversations_start_hour_in_day')),
        sa.ForeignKeyConstraint(
            ['character_id'],
            ['characters.id'],
            name=op.f('fk_conversations_character_id_characters'),
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['model_slug'], ['ai_models.slug'], name=op.f('fk_conversations_model_slug_ai_models'), ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_conversations')),
    )
    op.create_index(op.f('ix_conversations_active_leaf_id'), 'conversations', ['active_leaf_id'], unique=False)
    op.create_index(op.f('ix_conversations_character_id'), 'conversations', ['character_id'], unique=False)
    op.create_index(op.f('ix_conversations_model_slug'), 'conversations', ['model_slug'], unique=False)
    op.create_index('ix_conversations_owner_updated', 'conversations', ['owner_id', 'updated_at'], unique=False)
    op.create_table(
        'lore_embeddings',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('character_id', sa.Uuid(), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('lorebook_id', sa.Uuid(), nullable=False),
        sa.Column('entry_id', sa.String(length=40), nullable=False),
        sa.Column('embedding', Vector(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['character_id'],
            ['characters.id'],
            name=op.f('fk_lore_embeddings_character_id_characters'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_lore_embeddings')),
        sa.UniqueConstraint(
            'character_id', 'model', 'lorebook_id', 'entry_id', name=op.f('uq_lore_embeddings_character_id')
        ),
    )
    op.create_table(
        'achievement_records',
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('character_source', sa.Uuid(), nullable=False),
        sa.Column('achievement_id', sa.String(length=40), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column('image_id', sa.Uuid(), nullable=True),
        sa.Column('conversation_id', sa.Uuid(), nullable=True),
        sa.Column('earned_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_achievement_records_conversation_id_conversations'),
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('owner_id', 'character_source', 'achievement_id', name=op.f('pk_achievement_records')),
    )
    op.create_index(
        op.f('ix_achievement_records_character_source'), 'achievement_records', ['character_source'], unique=False
    )
    op.create_index(
        op.f('ix_achievement_records_conversation_id'), 'achievement_records', ['conversation_id'], unique=False
    )
    op.create_table(
        'conversation_personas',
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('source_id', sa.Uuid(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('image_id', sa.Uuid(), nullable=True),
        sa.Column('age', sa.Text(), nullable=False),
        sa.Column('gender', sa.Text(), nullable=False),
        sa.Column('form_of_address', sa.Text(), nullable=False),
        sa.Column('speech_examples', sa.Text(), nullable=False),
        sa.Column('personality', sa.Text(), nullable=False),
        sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_conversation_personas_conversation_id_conversations'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('conversation_id', name=op.f('pk_conversation_personas')),
    )
    op.create_table(
        'memory_notes',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('source', sa.String(length=10), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("source IN ('user', 'summary')", name=op.f('ck_memory_notes_source_allowed')),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_memory_notes_conversation_id_conversations'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_memory_notes')),
    )
    op.create_index(op.f('ix_memory_notes_conversation_id'), 'memory_notes', ['conversation_id'], unique=False)
    op.create_table(
        'messages',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('parent_id', sa.Uuid(), nullable=True),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('suggestions', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
        sa.Column('edited', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('event_scene', sa.String(length=40), nullable=True),
        sa.Column('expression', sa.String(length=20), nullable=True),
        sa.Column('changes', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('shortcut_body', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant', 'action')", name=op.f('ck_messages_role_allowed')),
        sa.CheckConstraint("status IN ('complete', 'partial', 'failed')", name=op.f('ck_messages_status_allowed')),
        sa.CheckConstraint('cardinality(suggestions) <= 3', name=op.f('ck_messages_suggestions_at_most_three')),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_messages_conversation_id_conversations'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['parent_id'], ['messages.id'], name=op.f('fk_messages_parent_id_messages'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_messages')),
    )
    op.create_index('ix_messages_conversation_parent', 'messages', ['conversation_id', 'parent_id'], unique=False)
    op.create_index(op.f('ix_messages_parent_id'), 'messages', ['parent_id'], unique=False)
    op.create_table(
        'bookmarks',
        sa.Column('message_id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('note', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_bookmarks_conversation_id_conversations'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['message_id'], ['messages.id'], name=op.f('fk_bookmarks_message_id_messages'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('message_id', name=op.f('pk_bookmarks')),
    )
    op.create_index(op.f('ix_bookmarks_conversation_id'), 'bookmarks', ['conversation_id'], unique=False)
    op.create_table(
        'generations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=True),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('parent_id', sa.Uuid(), nullable=True),
        sa.Column('message_id', sa.Uuid(), nullable=True),
        sa.Column('model_slug', sa.String(length=48), nullable=False),
        sa.Column('reference', sa.String(length=80), nullable=False),
        sa.Column('price_code', sa.String(length=120), nullable=False),
        sa.Column('billing_status', sa.String(length=20), nullable=False),
        sa.Column('settle_attempts', sa.Integer(), nullable=False),
        sa.Column('next_settle_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('outcome', sa.String(length=20), nullable=True),
        sa.Column('error_code', sa.String(length=60), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Numeric(precision=14, scale=8), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "billing_status IN ('pending', 'held', 'declined', 'capture_due', 'release_due', 'captured', 'released', "
            "'failed')",
            name=op.f('ck_generations_billing_status_allowed'),
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('complete', 'partial', 'failed')",
            name=op.f('ck_generations_outcome_allowed'),
        ),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_generations_conversation_id_conversations'),
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['message_id'], ['messages.id'], name=op.f('fk_generations_message_id_messages'), ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(
            ['model_slug'], ['ai_models.slug'], name=op.f('fk_generations_model_slug_ai_models'), ondelete='RESTRICT'
        ),
        sa.ForeignKeyConstraint(
            ['parent_id'], ['messages.id'], name=op.f('fk_generations_parent_id_messages'), ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_generations')),
        sa.UniqueConstraint('reference', name=op.f('uq_generations_reference')),
    )
    op.create_index(
        'ix_generations_billing_status_next_settle_at',
        'generations',
        ['billing_status', 'next_settle_at'],
        unique=False,
    )
    op.create_index(op.f('ix_generations_conversation_id'), 'generations', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_generations_message_id'), 'generations', ['message_id'], unique=False)
    op.create_index(op.f('ix_generations_model_slug'), 'generations', ['model_slug'], unique=False)
    op.create_index(op.f('ix_generations_parent_id'), 'generations', ['parent_id'], unique=False)
    op.create_table(
        'message_reports',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('reporter_id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('message_id', sa.Uuid(), nullable=False),
        sa.Column('character_id', sa.Uuid(), nullable=False),
        sa.Column('character_version', sa.Integer(), nullable=False),
        sa.Column('character_name', sa.Text(), nullable=False),
        sa.Column('model_slug', sa.String(length=100), nullable=True),
        sa.Column('reason', sa.String(length=20), nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('context', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('handled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('handled_by', sa.Uuid(), nullable=True),
        sa.Column('outcome', sa.String(length=20), nullable=True),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('actioned', 'dismissed')", name=op.f('ck_message_reports_outcome_allowed')
        ),
        sa.CheckConstraint(
            "reason IN ('spam', 'abuse', 'sexual', 'minor', 'illegal', 'other')",
            name=op.f('ck_message_reports_reason_allowed'),
        ),
        sa.CheckConstraint(
            '(handled_at IS NULL) = (handled_by IS NULL) AND (handled_at IS NULL) = (outcome IS NULL)',
            name=op.f('ck_message_reports_handled_together'),
        ),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_message_reports_conversation_id_conversations'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['message_id'], ['messages.id'], name=op.f('fk_message_reports_message_id_messages'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_message_reports')),
        sa.UniqueConstraint('reporter_id', 'message_id', name='uq_message_reports_reporter_message'),
    )
    op.create_index(op.f('ix_message_reports_conversation_id'), 'message_reports', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_message_reports_message_id'), 'message_reports', ['message_id'], unique=False)
    op.create_index(
        'ix_message_reports_open',
        'message_reports',
        ['created_at'],
        unique=False,
        postgresql_where='handled_at IS NULL',
    )
    op.create_table(
        'message_states',
        sa.Column('message_id', sa.Uuid(), nullable=False),
        sa.Column('place', sa.String(length=40), nullable=True),
        sa.Column('minutes', sa.Integer(), nullable=False),
        sa.Column('inventory', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('visited', postgresql.ARRAY(sa.String(length=40)), nullable=False),
        sa.Column('outfit', postgresql.ARRAY(sa.String(length=40)), server_default='{}', nullable=False),
        sa.Column('affection', sa.Integer(), nullable=True),
        sa.Column('fired', postgresql.ARRAY(sa.String(length=40)), server_default='{}', nullable=False),
        sa.Column('shown', postgresql.ARRAY(sa.String(length=40)), server_default='{}', nullable=False),
        sa.Column('received', postgresql.ARRAY(sa.String(length=40)), server_default='{}', nullable=False),
        sa.CheckConstraint(
            'affection IS NULL OR affection BETWEEN 0 AND 100', name=op.f('ck_message_states_affection_in_range')
        ),
        sa.CheckConstraint('minutes >= 0', name=op.f('ck_message_states_minutes_not_negative')),
        sa.ForeignKeyConstraint(
            ['message_id'], ['messages.id'], name=op.f('fk_message_states_message_id_messages'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('message_id', name=op.f('pk_message_states')),
    )
    op.create_table(
        'snapshots',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=True),
        sa.Column('message_id', sa.Uuid(), nullable=True),
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
            name=op.f('ck_snapshots_billing_status_allowed'),
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('ready', 'failed')", name=op.f('ck_snapshots_outcome_allowed')
        ),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_snapshots_conversation_id_conversations'),
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['message_id'], ['messages.id'], name=op.f('fk_snapshots_message_id_messages'), ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_snapshots')),
        sa.UniqueConstraint('reference', name=op.f('uq_snapshots_reference')),
    )
    op.create_index(
        'ix_snapshots_billing_status_next_settle_at', 'snapshots', ['billing_status', 'next_settle_at'], unique=False
    )
    op.create_index('ix_snapshots_conversation_created', 'snapshots', ['conversation_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_snapshots_message_id'), 'snapshots', ['message_id'], unique=False)
    op.create_index('ix_snapshots_owner_created', 'snapshots', ['owner_id', 'created_at'], unique=False)
    op.create_index(
        'uq_snapshots_one_drawing',
        'snapshots',
        ['conversation_id'],
        unique=True,
        postgresql_where=sa.text('outcome IS NULL'),
    )
    op.create_table(
        'summaries',
        sa.Column('message_id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('model_slug', sa.String(length=48), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Numeric(precision=14, scale=8), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_summaries_conversation_id_conversations'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['message_id'], ['messages.id'], name=op.f('fk_summaries_message_id_messages'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('message_id', name=op.f('pk_summaries')),
    )
    op.create_index(op.f('ix_summaries_conversation_id'), 'summaries', ['conversation_id'], unique=False)
    # 서로 가리키는 표라 둘을 만든 뒤에 건다
    op.create_foreign_key(
        'fk_conversations_active_leaf_id_messages',
        'conversations',
        'messages',
        ['active_leaf_id'],
        ['id'],
        ondelete='SET NULL',
    )
    for table in APPEND_ONLY:
        forbid_rewrites(table)


def downgrade() -> None:
    op.drop_constraint('fk_conversations_active_leaf_id_messages', 'conversations', type_='foreignkey')
    for table in APPEND_ONLY:
        allow_rewrites(table)
    op.drop_index(op.f('ix_summaries_conversation_id'), table_name='summaries')
    op.drop_table('summaries')
    op.drop_index('uq_snapshots_one_drawing', table_name='snapshots', postgresql_where=sa.text('outcome IS NULL'))
    op.drop_index('ix_snapshots_owner_created', table_name='snapshots')
    op.drop_index(op.f('ix_snapshots_message_id'), table_name='snapshots')
    op.drop_index('ix_snapshots_conversation_created', table_name='snapshots')
    op.drop_index('ix_snapshots_billing_status_next_settle_at', table_name='snapshots')
    op.drop_table('snapshots')
    op.drop_table('message_states')
    op.drop_index('ix_message_reports_open', table_name='message_reports', postgresql_where='handled_at IS NULL')
    op.drop_index(op.f('ix_message_reports_message_id'), table_name='message_reports')
    op.drop_index(op.f('ix_message_reports_conversation_id'), table_name='message_reports')
    op.drop_table('message_reports')
    op.drop_index(op.f('ix_generations_parent_id'), table_name='generations')
    op.drop_index(op.f('ix_generations_model_slug'), table_name='generations')
    op.drop_index(op.f('ix_generations_message_id'), table_name='generations')
    op.drop_index(op.f('ix_generations_conversation_id'), table_name='generations')
    op.drop_index('ix_generations_billing_status_next_settle_at', table_name='generations')
    op.drop_table('generations')
    op.drop_index(op.f('ix_bookmarks_conversation_id'), table_name='bookmarks')
    op.drop_table('bookmarks')
    op.drop_index(op.f('ix_messages_parent_id'), table_name='messages')
    op.drop_index('ix_messages_conversation_parent', table_name='messages')
    op.drop_table('messages')
    op.drop_index(op.f('ix_memory_notes_conversation_id'), table_name='memory_notes')
    op.drop_table('memory_notes')
    op.drop_table('conversation_personas')
    op.drop_index(op.f('ix_achievement_records_conversation_id'), table_name='achievement_records')
    op.drop_index(op.f('ix_achievement_records_character_source'), table_name='achievement_records')
    op.drop_table('achievement_records')
    op.drop_table('lore_embeddings')
    op.drop_index('ix_conversations_owner_updated', table_name='conversations')
    op.drop_index(op.f('ix_conversations_model_slug'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_character_id'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_active_leaf_id'), table_name='conversations')
    op.drop_table('conversations')
    op.drop_index('ix_ai_model_snapshots_model_slug_id', table_name='ai_model_snapshots')
    op.drop_table('ai_model_snapshots')
    op.drop_index('ix_ai_model_costs_model_slug_effective_from', table_name='ai_model_costs')
    op.drop_table('ai_model_costs')
    op.drop_index('ix_scene_unlocks_owner_unlocked', table_name='scene_unlocks')
    op.drop_table('scene_unlocks')
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
    op.drop_table('characters')
    op.drop_index(op.f('ix_character_players_character_source'), table_name='character_players')
    op.drop_table('character_players')
    op.drop_table('ai_models')
