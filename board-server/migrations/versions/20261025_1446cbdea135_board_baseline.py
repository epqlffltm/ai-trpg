"""board baseline

Revision ID: 1446cbdea135
Revises:
Create Date: 2026-10-25 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '1446cbdea135'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 게시판 서버를 FastAPI 로 다시 쓰며 잡은 기준선(#785).
# NestJS(TypeORM)의 마지막 마이그레이션(AllowWithdrawnAuthors)과 같은 모양이다.
# 표와 칸, 제약의 이름이 그때와 같다. 발송함의 CHECK 이름만 공용 코드의 것으로 바뀌었다(뜻은 같다).
#
# 이미 TypeORM 이 표를 만든 DB(개발용 board 스키마)는 표를 다시 만들지 않고 넘겨받는다.
# 그 DB 의 TypeORM 기록 표(migrations)는 더 쓰지 않으므로 지운다. 데이터는 그대로다

# TypeORM 이 남긴 적용 기록의 표
TYPEORM_HISTORY = 'migrations'

# 처음 넣는 게시판. 차례(position)대로 목록에 보인다
BOARDS = [
    ('notice', '공지사항', '운영자가 알리는 소식입니다.', 'operator', 1),
    ('event', '이벤트', '진행 중인 이벤트와 그 결과를 알립니다.', 'operator', 2),
    ('free', '자유 게시판', '자유롭게 이야기를 나누는 곳입니다.', 'member', 3),
    ('scenario', '시나리오 이야기', '시나리오에 대한 감상과 이야기를 나누는 곳입니다.', 'member', 4),
]


def made_by_typeorm() -> bool:
    """TypeORM 이 이미 표를 만든 스키마인가. 지금 스키마(search_path 의 첫째)에 posts 가 있으면 그렇다."""
    return bool(op.get_bind().execute(sa.text("SELECT to_regclass('posts') IS NOT NULL")).scalar())


def adopt_typeorm_schema() -> None:
    """TypeORM 이 만든 표를 그대로 쓴다. 적용 기록만 지운다."""
    op.execute(sa.text(f'DROP TABLE IF EXISTS "{TYPEORM_HISTORY}"'))


def seed_boards() -> None:
    """게시판 넷을 넣는다."""
    boards = sa.table(
        'boards',
        sa.column('slug', sa.String),
        sa.column('name', sa.String),
        sa.column('description', sa.String),
        sa.column('write_policy', sa.String),
        sa.column('position', sa.Integer),
    )
    op.bulk_insert(
        boards,
        [
            {'slug': slug, 'name': name, 'description': description, 'write_policy': policy, 'position': position}
            for slug, name, description, policy, position in BOARDS
        ],
    )


def upgrade() -> None:
    if made_by_typeorm():
        adopt_typeorm_schema()
        return
    create_tables()
    seed_boards()


def create_tables() -> None:
    """게시판 서버의 표를 모두 만든다."""
    op.create_table(
        'authors',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('nickname', sa.String(length=50), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('user_id', name=op.f('pk_authors')),
    )
    op.create_table(
        'boards',
        sa.Column('id', sa.Integer(), sa.Identity(always=True), nullable=False),
        sa.Column('slug', sa.String(length=30), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=200), nullable=False),
        sa.Column('write_policy', sa.String(length=20), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("write_policy IN ('member', 'operator')", name=op.f('ck_boards_write_policy')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_boards')),
        sa.UniqueConstraint('slug', name=op.f('uq_boards_slug')),
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
        'posts',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column('board_id', sa.Integer(), nullable=False),
        sa.Column('author_id', sa.Uuid(), nullable=True),
        sa.Column('title', sa.String(length=100), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pinned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pinned_until', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('(pinned_at IS NULL) = (pinned_until IS NULL)', name=op.f('ck_posts_pin_pair')),
        sa.ForeignKeyConstraint(['board_id'], ['boards.id'], name=op.f('fk_posts_board'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_posts')),
    )
    op.create_index(op.f('ix_posts_author_id_created_at'), 'posts', ['author_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_posts_board_id_id'), 'posts', ['board_id', 'id'], unique=False)
    op.create_index(
        op.f('ix_posts_board_id_pinned_until'),
        'posts',
        ['board_id', 'pinned_until'],
        unique=False,
        postgresql_where=sa.text('pinned_until IS NOT NULL'),
    )
    op.create_table(
        'comments',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column('post_id', sa.BigInteger(), nullable=False),
        sa.Column('parent_id', sa.BigInteger(), nullable=True),
        sa.Column('author_id', sa.Uuid(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['parent_id'], ['comments.id'], name=op.f('fk_comments_parent'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['post_id'], ['posts.id'], name=op.f('fk_comments_post'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_comments')),
    )
    op.create_index(op.f('ix_comments_author_id_created_at'), 'comments', ['author_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_comments_post_id_parent_id_id'), 'comments', ['post_id', 'parent_id', 'id'], unique=False)
    op.create_table(
        'reports',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column('post_id', sa.BigInteger(), nullable=True),
        sa.Column('comment_id', sa.BigInteger(), nullable=True),
        sa.Column('reporter_id', sa.Uuid(), nullable=True),
        sa.Column('reason', sa.String(length=20), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('handled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('handled_by', sa.Uuid(), nullable=True),
        sa.Column('outcome', sa.String(length=20), nullable=True),
        sa.CheckConstraint("outcome IS NULL OR outcome IN ('actioned', 'dismissed')", name=op.f('ck_reports_outcome')),
        sa.CheckConstraint("reason IN ('spam', 'abuse', 'sexual', 'illegal', 'other')", name=op.f('ck_reports_reason')),
        sa.CheckConstraint(
            '(handled_at IS NULL) = (handled_by IS NULL) AND (handled_at IS NULL) = (outcome IS NULL)',
            name=op.f('ck_reports_handled_together'),
        ),
        sa.CheckConstraint('(post_id IS NULL) <> (comment_id IS NULL)', name=op.f('ck_reports_one_target')),
        sa.ForeignKeyConstraint(['comment_id'], ['comments.id'], name=op.f('fk_reports_comment'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['post_id'], ['posts.id'], name=op.f('fk_reports_post'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_reports')),
        sa.UniqueConstraint('reporter_id', 'comment_id', name=op.f('uq_reports_reporter_id_comment_id')),
        sa.UniqueConstraint('reporter_id', 'post_id', name=op.f('uq_reports_reporter_id_post_id')),
    )
    op.create_index(
        op.f('ix_reports_comment_id'),
        'reports',
        ['comment_id'],
        unique=False,
        postgresql_where=sa.text('comment_id IS NOT NULL'),
    )
    op.create_index(
        op.f('ix_reports_open'), 'reports', ['created_at'], unique=False, postgresql_where=sa.text('handled_at IS NULL')
    )
    op.create_index(
        op.f('ix_reports_post_id'),
        'reports',
        ['post_id'],
        unique=False,
        postgresql_where=sa.text('post_id IS NOT NULL'),
    )
    op.create_index(op.f('ix_reports_reporter_id_created_at'), 'reports', ['reporter_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_reports_reporter_id_created_at'), table_name='reports')
    op.drop_index(op.f('ix_reports_post_id'), table_name='reports', postgresql_where=sa.text('post_id IS NOT NULL'))
    op.drop_index(op.f('ix_reports_open'), table_name='reports', postgresql_where=sa.text('handled_at IS NULL'))
    op.drop_index(
        op.f('ix_reports_comment_id'), table_name='reports', postgresql_where=sa.text('comment_id IS NOT NULL')
    )
    op.drop_table('reports')
    op.drop_index(op.f('ix_comments_post_id_parent_id_id'), table_name='comments')
    op.drop_index(op.f('ix_comments_author_id_created_at'), table_name='comments')
    op.drop_table('comments')
    op.drop_index(
        op.f('ix_posts_board_id_pinned_until'), table_name='posts', postgresql_where=sa.text('pinned_until IS NOT NULL')
    )
    op.drop_index(op.f('ix_posts_board_id_id'), table_name='posts')
    op.drop_index(op.f('ix_posts_author_id_created_at'), table_name='posts')
    op.drop_table('posts')
    op.drop_index(
        'ix_outgoing_notifications_due',
        table_name='outgoing_notifications',
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_table('outgoing_notifications')
    op.drop_table('boards')
    op.drop_table('authors')
