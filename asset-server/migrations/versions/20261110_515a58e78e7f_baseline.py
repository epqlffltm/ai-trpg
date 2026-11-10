"""baseline

Revision ID: 515a58e78e7f
Revises:
Create Date: 2026-11-10 19:36:12.757122

첫 배포 전에 쌓인 마이그레이션 28개를 하나로 합친 기준선(#1273). 빈 스키마에 지금의 표를 한 번에 만든다.
모델에서 자동으로 만든 뒤, 모델이 모르는 것(운영자 기록을 고치지 못하게 하는 함수와 트리거)을 손으로 더했다.
옛 사슬로 만든 스키마와 같은지는 tools/compare_schemas.py 로 견주었다.
옛 마이그레이션이 하던 데이터 옮기기(그림을 쓰는 곳 채우기 등)는 빈 DB 에서 할 일이 없어 넣지 않았다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '515a58e78e7f'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def require_trgm() -> None:
    """
    pg_trgm 이 켜져 있지 않거나 asset 계정이 쓸 수 없으면 알아볼 수 있는 말로 멈춘다.

    asset 계정은 확장을 켤 수 없다(슈퍼유저만 된다). 그래서 여기서 켜지 않고, 쓸 수 있는지만 본다.
    아니면 아래의 gin_trgm_ops 가 "없는 연산자 묶음"이나 "권한 없음"이라는 알기 어려운 오류로 실패한다.
    """
    usable = op.get_bind().scalar(
        sa.text("SELECT has_schema_privilege('extensions', 'USAGE') FROM pg_extension WHERE extname = 'pg_trgm'")
    )
    if not usable:
        raise RuntimeError(
            'pg_trgm 이 켜져 있지 않거나 asset 계정이 extensions 스키마를 쓸 수 없습니다. '
            'docker/postgres/init/03-extensions.sql 과 asset 계정의 extensions 스키마 읽기 권한을 슈퍼유저로 실행하세요'
            '(asset-server/README.md 의 "준비")'
        )


def upgrade() -> None:
    require_trgm()
    op.create_table(
        'images',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('kept_by', sa.String(length=32), nullable=True),
        sa.Column('format', sa.String(length=10), nullable=False),
        sa.Column('byte_size', sa.Integer(), nullable=False),
        sa.Column('width', sa.Integer(), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("format IN ('png', 'jpeg', 'webp')", name=op.f('ck_images_format_allowed')),
        sa.CheckConstraint('byte_size > 0 AND width > 0 AND height > 0', name=op.f('ck_images_size_positive')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_images')),
    )
    op.create_index(op.f('ix_images_owner_id'), 'images', ['owner_id'], unique=False)
    op.create_table(
        'lorebooks',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column('entries', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('latest_version', sa.Integer(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            '(latest_version IS NULL) = (published_at IS NULL)', name=op.f('ck_lorebooks_published_paired')
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_lorebooks')),
    )
    op.create_index(op.f('ix_lorebooks_owner_id'), 'lorebooks', ['owner_id'], unique=False)
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
            "action IN ('character_hide', 'character_unhide', 'reports_dismiss', 'world_hide', 'world_unhide')",
            name=op.f('ck_operator_actions_action_allowed'),
        ),
        sa.CheckConstraint("btrim(reason) <> ''", name=op.f('ck_operator_actions_reason_not_blank')),
        sa.CheckConstraint('char_length(reason) <= 200', name=op.f('ck_operator_actions_reason_length')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_operator_actions')),
        info={'append_only': True},
    )
    op.create_index('ix_operator_actions_operator', 'operator_actions', ['operator_id', 'acted_at'], unique=False)
    op.create_index('ix_operator_actions_target', 'operator_actions', ['target_id', 'acted_at'], unique=False)
    # 운영자의 기록은 덧붙이기만 한다. 고치거나 지우면 DB 가 막는다(docs/architecture/operators.md)
    op.execute(
        """
        CREATE FUNCTION operator_actions_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'operator_actions 는 덧붙이기만 한다(%)', TG_OP;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER operator_actions_no_rewrite
        BEFORE UPDATE OR DELETE ON operator_actions
        FOR EACH ROW EXECUTE FUNCTION operator_actions_append_only()
        """
    )
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
        'user_shortcuts',
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('items', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('owner_id', name=op.f('pk_user_shortcuts')),
    )
    op.create_table(
        'work_starts',
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('work_id', sa.Uuid(), nullable=False),
        sa.Column('total', sa.Integer(), nullable=False),
        sa.Column('recent', sa.Integer(), nullable=False),
        sa.Column('recent_days', sa.Integer(), nullable=False),
        sa.Column('refreshed_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('character', 'world')", name=op.f('ck_work_starts_kind_allowed')),
        sa.CheckConstraint('total >= recent AND recent >= 0', name=op.f('ck_work_starts_counts_ordered')),
        sa.PrimaryKeyConstraint('kind', 'work_id', name=op.f('pk_work_starts')),
    )
    op.create_table(
        'characters',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('intro_html', sa.Text(), server_default='', nullable=False),
        sa.Column('greeting', sa.Text(), server_default='', nullable=False),
        sa.Column('speech_examples', sa.Text(), server_default='', nullable=False),
        sa.Column('age', sa.String(length=20), server_default='', nullable=False),
        sa.Column('gender', sa.String(length=20), server_default='', nullable=False),
        sa.Column('tags', postgresql.ARRAY(sa.String(length=20)), server_default='{}', nullable=False),
        sa.Column('genre', sa.String(length=30), nullable=False),
        sa.Column('starts', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('image_id', sa.Uuid(), nullable=True),
        sa.Column('places', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('paths', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('start_place', sa.String(length=40), nullable=True),
        sa.Column('items', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('start_items', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('affection', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('event_scenes', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('sprites', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('lorebooks', postgresql.ARRAY(sa.Uuid()), server_default='{}', nullable=False),
        sa.Column('shortcuts', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('achievements', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('rating', sa.String(length=10), server_default='all', nullable=False),
        sa.Column('visibility', sa.String(length=10), server_default='private', nullable=False),
        sa.Column('latest_version', sa.Integer(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('hidden_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('heart_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('start_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("rating IN ('all', 'adult')", name=op.f('ck_characters_rating_allowed')),
        sa.CheckConstraint(
            "visibility IN ('private', 'public', 'unlisted')", name=op.f('ck_characters_visibility_allowed')
        ),
        sa.CheckConstraint(
            '(latest_version IS NULL) = (published_at IS NULL)', name=op.f('ck_characters_published_paired')
        ),
        sa.CheckConstraint('cardinality(tags) <= 10', name=op.f('ck_characters_tags_count')),
        sa.CheckConstraint('heart_count >= 0', name=op.f('ck_characters_heart_count_not_negative')),
        sa.ForeignKeyConstraint(
            ['image_id'], ['images.id'], name=op.f('fk_characters_image_id_images'), ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_characters')),
    )
    op.create_index(op.f('ix_characters_image_id'), 'characters', ['image_id'], unique=False)
    op.create_index(op.f('ix_characters_owner_id'), 'characters', ['owner_id'], unique=False)
    op.create_table(
        'lorebook_versions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('lorebook_id', sa.Uuid(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('note', sa.String(length=500), server_default='', nullable=False),
        sa.Column('document', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('number >= 1', name=op.f('ck_lorebook_versions_number_positive')),
        sa.ForeignKeyConstraint(
            ['lorebook_id'],
            ['lorebooks.id'],
            name=op.f('fk_lorebook_versions_lorebook_id_lorebooks'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_lorebook_versions')),
        sa.UniqueConstraint('lorebook_id', 'number', name='uq_lorebook_versions_number'),
    )
    op.create_index(op.f('ix_lorebook_versions_lorebook_id'), 'lorebook_versions', ['lorebook_id'], unique=False)
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
        sa.ForeignKeyConstraint(
            ['image_id'], ['images.id'], name=op.f('fk_personas_image_id_images'), ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_personas')),
    )
    op.create_index(op.f('ix_personas_image_id'), 'personas', ['image_id'], unique=False)
    op.create_index(op.f('ix_personas_owner_id'), 'personas', ['owner_id'], unique=False)
    op.create_index(
        'uq_personas_default_per_owner', 'personas', ['owner_id'], unique=True, postgresql_where=sa.text('is_default')
    )
    op.create_table(
        'worlds',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('intro_html', sa.Text(), server_default='', nullable=False),
        sa.Column('tags', postgresql.ARRAY(sa.String(length=20)), server_default='{}', nullable=False),
        sa.Column('genre', sa.String(length=30), nullable=False),
        sa.Column('image_id', sa.Uuid(), nullable=True),
        sa.Column('slots', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('start_slot', sa.String(length=40), nullable=True),
        sa.Column('deadline_days', sa.Integer(), nullable=True),
        sa.Column('after_ending', sa.String(length=10), server_default='end', nullable=False),
        sa.Column('show', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('places', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('paths', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('start_place', sa.String(length=40), nullable=True),
        sa.Column('items', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('start_items', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('cast', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('events', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('endings', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('chapters', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('lorebooks', postgresql.ARRAY(sa.Uuid()), server_default='{}', nullable=False),
        sa.Column('shortcuts', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('achievements', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('rating', sa.String(length=10), server_default='all', nullable=False),
        sa.Column('visibility', sa.String(length=10), server_default='private', nullable=False),
        sa.Column('latest_version', sa.Integer(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('hidden_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('heart_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('start_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("after_ending IN ('end', 'epilogue')", name=op.f('ck_worlds_after_allowed')),
        sa.CheckConstraint("rating IN ('all', 'adult')", name=op.f('ck_worlds_rating_allowed')),
        sa.CheckConstraint(
            "visibility IN ('private', 'public', 'unlisted')", name=op.f('ck_worlds_visibility_allowed')
        ),
        sa.CheckConstraint(
            '(latest_version IS NULL) = (published_at IS NULL)', name=op.f('ck_worlds_published_paired')
        ),
        sa.CheckConstraint('cardinality(tags) <= 10', name=op.f('ck_worlds_tags_count')),
        sa.CheckConstraint(
            'deadline_days IS NULL OR deadline_days BETWEEN 1 AND 365', name=op.f('ck_worlds_deadline_range')
        ),
        sa.CheckConstraint('heart_count >= 0', name=op.f('ck_worlds_heart_count_not_negative')),
        sa.ForeignKeyConstraint(
            ['image_id'], ['images.id'], name=op.f('fk_worlds_image_id_images'), ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_worlds')),
    )
    op.create_index(op.f('ix_worlds_image_id'), 'worlds', ['image_id'], unique=False)
    op.create_index(op.f('ix_worlds_owner_id'), 'worlds', ['owner_id'], unique=False)
    op.create_table(
        'banners',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('character_id', sa.Uuid(), nullable=True),
        sa.Column('world_id', sa.Uuid(), nullable=True),
        sa.Column('position', sa.SmallInteger(), nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('ends_at IS NULL OR starts_at < ends_at', name=op.f('ck_banners_period_order')),
        sa.CheckConstraint('num_nonnulls(character_id, world_id) = 1', name=op.f('ck_banners_one_target')),
        sa.CheckConstraint('position >= 0 AND position <= 999', name=op.f('ck_banners_position_range')),
        sa.ForeignKeyConstraint(
            ['character_id'], ['characters.id'], name=op.f('fk_banners_character_id_characters'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['world_id'], ['worlds.id'], name=op.f('fk_banners_world_id_worlds'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_banners')),
    )
    op.create_index(op.f('ix_banners_character_id'), 'banners', ['character_id'], unique=False)
    op.create_index(op.f('ix_banners_world_id'), 'banners', ['world_id'], unique=False)
    op.create_table(
        'character_hearts',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('character_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['character_id'],
            ['characters.id'],
            name=op.f('fk_character_hearts_character_id_characters'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('user_id', 'character_id', name=op.f('pk_character_hearts')),
    )
    op.create_index(op.f('ix_character_hearts_character_id'), 'character_hearts', ['character_id'], unique=False)
    op.create_index('ix_character_hearts_user_created', 'character_hearts', ['user_id', 'created_at'], unique=False)
    op.create_table(
        'character_reports',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('character_id', sa.Uuid(), nullable=False),
        sa.Column('reporter_id', sa.Uuid(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=20), nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('handled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('handled_by', sa.Uuid(), nullable=True),
        sa.Column('outcome', sa.String(length=20), nullable=True),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('actioned', 'dismissed')", name=op.f('ck_character_reports_outcome_allowed')
        ),
        sa.CheckConstraint(
            "reason IN ('spam', 'abuse', 'sexual', 'minor', 'illegal', 'other')",
            name=op.f('ck_character_reports_reason_allowed'),
        ),
        sa.CheckConstraint(
            '(handled_at IS NULL) = (handled_by IS NULL) AND (handled_at IS NULL) = (outcome IS NULL)',
            name=op.f('ck_character_reports_handled_together'),
        ),
        sa.ForeignKeyConstraint(
            ['character_id'],
            ['characters.id'],
            name=op.f('fk_character_reports_character_id_characters'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_character_reports')),
        sa.UniqueConstraint('reporter_id', 'character_id', name='uq_character_reports_reporter_character'),
    )
    op.create_index(
        'ix_character_reports_open',
        'character_reports',
        ['character_id'],
        unique=False,
        postgresql_where='handled_at IS NULL',
    )
    op.create_table(
        'character_versions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('character_id', sa.Uuid(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('note', sa.String(length=500), server_default='', nullable=False),
        sa.Column('rating', sa.String(length=10), nullable=False),
        sa.Column('document', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("rating IN ('all', 'adult')", name=op.f('ck_character_versions_rating_allowed')),
        sa.CheckConstraint('number >= 1', name=op.f('ck_character_versions_number_positive')),
        sa.ForeignKeyConstraint(
            ['character_id'],
            ['characters.id'],
            name=op.f('fk_character_versions_character_id_characters'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_character_versions')),
        sa.UniqueConstraint('character_id', 'number', name='uq_character_versions_number'),
    )
    op.create_index(op.f('ix_character_versions_character_id'), 'character_versions', ['character_id'], unique=False)
    op.create_index(
        'ix_character_versions_name_trgm',
        'character_versions',
        [sa.literal_column("(document ->> 'name')").label('name')],
        unique=False,
        postgresql_using='gin',
        postgresql_ops={'name': 'extensions.gin_trgm_ops'},
    )
    op.create_table(
        'world_hearts',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('world_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['world_id'], ['worlds.id'], name=op.f('fk_world_hearts_world_id_worlds'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('user_id', 'world_id', name=op.f('pk_world_hearts')),
    )
    op.create_index('ix_world_hearts_user_created', 'world_hearts', ['user_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_world_hearts_world_id'), 'world_hearts', ['world_id'], unique=False)
    op.create_table(
        'world_versions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('world_id', sa.Uuid(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('note', sa.String(length=500), server_default='', nullable=False),
        sa.Column('rating', sa.String(length=10), nullable=False),
        sa.Column('document', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("rating IN ('all', 'adult')", name=op.f('ck_world_versions_rating_allowed')),
        sa.CheckConstraint('number >= 1', name=op.f('ck_world_versions_number_positive')),
        sa.ForeignKeyConstraint(
            ['world_id'], ['worlds.id'], name=op.f('fk_world_versions_world_id_worlds'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_world_versions')),
        sa.UniqueConstraint('world_id', 'number', name='uq_world_versions_number'),
    )
    op.create_index(
        'ix_world_versions_name_trgm',
        'world_versions',
        [sa.literal_column("(document ->> 'name')").label('name')],
        unique=False,
        postgresql_using='gin',
        postgresql_ops={'name': 'extensions.gin_trgm_ops'},
    )
    op.create_index(op.f('ix_world_versions_world_id'), 'world_versions', ['world_id'], unique=False)
    op.create_table(
        'image_uses',
        sa.Column('version_id', sa.Uuid(), nullable=False),
        sa.Column('image_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ['image_id'], ['images.id'], name=op.f('fk_image_uses_image_id_images'), ondelete='RESTRICT'
        ),
        sa.ForeignKeyConstraint(
            ['version_id'],
            ['character_versions.id'],
            name=op.f('fk_image_uses_version_id_character_versions'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('version_id', 'image_id', name=op.f('pk_image_uses')),
    )
    op.create_index(op.f('ix_image_uses_image_id'), 'image_uses', ['image_id'], unique=False)
    op.create_table(
        'world_image_uses',
        sa.Column('version_id', sa.Uuid(), nullable=False),
        sa.Column('image_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ['image_id'], ['images.id'], name=op.f('fk_world_image_uses_image_id_images'), ondelete='RESTRICT'
        ),
        sa.ForeignKeyConstraint(
            ['version_id'],
            ['world_versions.id'],
            name=op.f('fk_world_image_uses_version_id_world_versions'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('version_id', 'image_id', name=op.f('pk_world_image_uses')),
    )
    op.create_index(op.f('ix_world_image_uses_image_id'), 'world_image_uses', ['image_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_world_image_uses_image_id'), table_name='world_image_uses')
    op.drop_table('world_image_uses')
    op.drop_index(op.f('ix_image_uses_image_id'), table_name='image_uses')
    op.drop_table('image_uses')
    op.drop_index(op.f('ix_world_versions_world_id'), table_name='world_versions')
    op.drop_index(
        'ix_world_versions_name_trgm',
        table_name='world_versions',
        postgresql_using='gin',
        postgresql_ops={'name': 'extensions.gin_trgm_ops'},
    )
    op.drop_table('world_versions')
    op.drop_index(op.f('ix_world_hearts_world_id'), table_name='world_hearts')
    op.drop_index('ix_world_hearts_user_created', table_name='world_hearts')
    op.drop_table('world_hearts')
    op.drop_index(
        'ix_character_versions_name_trgm',
        table_name='character_versions',
        postgresql_using='gin',
        postgresql_ops={'name': 'extensions.gin_trgm_ops'},
    )
    op.drop_index(op.f('ix_character_versions_character_id'), table_name='character_versions')
    op.drop_table('character_versions')
    op.drop_index('ix_character_reports_open', table_name='character_reports', postgresql_where='handled_at IS NULL')
    op.drop_table('character_reports')
    op.drop_index('ix_character_hearts_user_created', table_name='character_hearts')
    op.drop_index(op.f('ix_character_hearts_character_id'), table_name='character_hearts')
    op.drop_table('character_hearts')
    op.drop_index(op.f('ix_banners_world_id'), table_name='banners')
    op.drop_index(op.f('ix_banners_character_id'), table_name='banners')
    op.drop_table('banners')
    op.drop_index(op.f('ix_worlds_owner_id'), table_name='worlds')
    op.drop_index(op.f('ix_worlds_image_id'), table_name='worlds')
    op.drop_table('worlds')
    op.drop_index('uq_personas_default_per_owner', table_name='personas', postgresql_where=sa.text('is_default'))
    op.drop_index(op.f('ix_personas_owner_id'), table_name='personas')
    op.drop_index(op.f('ix_personas_image_id'), table_name='personas')
    op.drop_table('personas')
    op.drop_index(op.f('ix_lorebook_versions_lorebook_id'), table_name='lorebook_versions')
    op.drop_table('lorebook_versions')
    op.drop_index(op.f('ix_characters_owner_id'), table_name='characters')
    op.drop_index(op.f('ix_characters_image_id'), table_name='characters')
    op.drop_table('characters')
    op.drop_table('work_starts')
    op.drop_table('user_shortcuts')
    op.drop_index(
        'ix_outgoing_notifications_due',
        table_name='outgoing_notifications',
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_table('outgoing_notifications')
    op.execute('DROP TRIGGER operator_actions_no_rewrite ON operator_actions')
    op.execute('DROP FUNCTION operator_actions_append_only()')
    op.drop_index('ix_operator_actions_target', table_name='operator_actions')
    op.drop_index('ix_operator_actions_operator', table_name='operator_actions')
    op.drop_table('operator_actions')
    op.drop_index(op.f('ix_lorebooks_owner_id'), table_name='lorebooks')
    op.drop_table('lorebooks')
    op.drop_index(op.f('ix_images_owner_id'), table_name='images')
    op.drop_table('images')
