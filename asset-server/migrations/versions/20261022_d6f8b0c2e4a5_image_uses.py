"""image_uses

Revision ID: d6f8b0c2e4a5
Revises: c5e7a9b1d3f4
Create Date: 2026-10-22 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd6f8b0c2e4a5'
down_revision: str | Sequence[str] | None = 'c5e7a9b1d3f4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 그림이 쓰인 판(image_uses)과, 페르소나와 캐릭터의 그림을 그림의 행에 묶는 외래 키(#566, app/images/models.py).
# 이미 있는 판은 문서의 대표 그림과 소개 글의 img 에서 쓰인 그림을 채운다. 없는 그림을 가리키는 것은 버린다.
# 페르소나와 캐릭터의 image_id 가 없는 그림을 가리키면 비운 뒤 외래 키를 건다(그림이 생기기 전에는 적어 두기만 했다)

# 소개 글의 img 에서 그림의 id 를 꺼낸다(app/content/html.py 의 IMAGE 와 같은 주소다)
BACKFILL_USES = r"""
INSERT INTO image_uses (version_id, image_id)
SELECT DISTINCT used.version_id, used.image_id
FROM (
    SELECT v.id AS version_id, (v.document->>'image_id')::uuid AS image_id
    FROM character_versions v
    WHERE v.document->>'image_id' IS NOT NULL
    UNION
    SELECT v.id, found[1]::uuid
    FROM character_versions v,
        regexp_matches(
            v.document->>'intro_html',
            '<img[^>]*src="/api/v1/asset/images/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"',
            'g'
        ) AS found
) AS used
JOIN images ON images.id = used.image_id
"""


def upgrade() -> None:
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
    op.execute(BACKFILL_USES)

    for table in ('characters', 'personas'):
        op.execute(
            f'UPDATE {table} SET image_id = NULL WHERE image_id IS NOT NULL '
            'AND NOT EXISTS (SELECT 1 FROM images WHERE images.id = image_id)'
        )
        op.create_index(op.f(f'ix_{table}_image_id'), table, ['image_id'], unique=False)
        op.create_foreign_key(
            op.f(f'fk_{table}_image_id_images'), table, 'images', ['image_id'], ['id'], ondelete='SET NULL'
        )


def downgrade() -> None:
    for table in ('personas', 'characters'):
        op.drop_constraint(op.f(f'fk_{table}_image_id_images'), table, type_='foreignkey')
        op.drop_index(op.f(f'ix_{table}_image_id'), table_name=table)
    op.drop_index(op.f('ix_image_uses_image_id'), table_name='image_uses')
    op.drop_table('image_uses')
