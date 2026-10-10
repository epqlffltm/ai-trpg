"""lore embeddings

Revision ID: c5e7a9b1d3f5
Revises: b4d6f8a0c2e3
Create Date: 2026-10-10 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = 'c5e7a9b1d3f5'
down_revision: str | Sequence[str] | None = 'b4d6f8a0c2e3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def require_vector() -> None:
    """
    pgvector 가 켜져 있지 않으면 알아볼 수 있는 말로 멈춘다.

    게임 계정은 확장을 켤 수 없다(슈퍼유저만 된다). 그래서 여기서 켜지 않고, 켜져 있는지만 본다.
    켜져 있지 않으면 아래의 vector 타입이 "없는 타입"이라는 알기 어려운 오류로 실패한다.
    """
    found = op.get_bind().scalar(sa.text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
    if found is None:
        raise RuntimeError(
            'pgvector 가 켜져 있지 않습니다. docker/postgres/init/03-extensions.sql 을 슈퍼유저로 실행하세요'
            '(game-server/README.md 의 "로어북 검색")'
        )


def upgrade() -> None:
    require_vector()
    # 자동 생성이 찾은 그대로다. 벡터의 타입만 이름을 바꿔 불러온다(자동 생성은 pgvector 를 import 하지 않는다)
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


def downgrade() -> None:
    op.drop_table('lore_embeddings')
