"""genre required

Revision ID: 41cb12e2ff59
Revises: 6c46b1cd4f34
Create Date: 2026-11-01 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '41cb12e2ff59'
down_revision: str | Sequence[str] | None = '6c46b1cd4f34'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 캐릭터와 세계관의 장르를 반드시 하나로 한다(비워 둘 수 없다, NOT NULL). 장르마다 화면의 테마가 있다.
# 장르가 비어 있던 초안은 판타지(FILL)로 채운다(2026-10-31 유저 결정, 시나리오와 같다).
# 만든 사람이 고쳐서 다시 게시하면 바뀐다.
# 이미 게시한 판의 문서에 장르가 없으면 그 캐릭터·세계관의 장르를 적는다(장르 없는 판이 남지 않게).
# 되돌리면 칸을 다시 비울 수 있게만 한다. 채운 장르와 판의 문서에 적은 장르는 그대로 둔다

FILL = 'fantasy'
TABLES = (('characters', 'character_versions', 'character_id'), ('worlds', 'world_versions', 'world_id'))


def upgrade() -> None:
    for table, versions, key in TABLES:
        op.execute(sa.text(f'UPDATE {table} SET genre = :fill WHERE genre IS NULL').bindparams(fill=FILL))
        op.alter_column(table, 'genre', existing_type=sa.String(length=30), nullable=False)
        op.execute(
            f"""
            UPDATE {versions} SET document = jsonb_set(document, '{{genre}}', to_jsonb(owner.genre))
            FROM {table} AS owner
            WHERE owner.id = {versions}.{key}
              AND (NOT (document ? 'genre') OR document -> 'genre' = 'null'::jsonb)
            """
        )


def downgrade() -> None:
    for table, _versions, _key in TABLES:
        op.alter_column(table, 'genre', existing_type=sa.String(length=30), nullable=True)
