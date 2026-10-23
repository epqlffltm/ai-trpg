"""event scenes and sprites

Revision ID: b0d2f4a6c8e9
Revises: a9c1e3f5b7d8
Create Date: 2026-10-23 02:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b0d2f4a6c8e9'
down_revision: str | Sequence[str] | None = 'a9c1e3f5b7d8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 그림은 셋이다(2026-10-23 유저 결정): 캐릭터 그림, 배경, 이벤트 씬.
#   - illustrations 는 이벤트 씬이었다. 칸의 이름을 event_scenes 로, 장면의 설명(scene)을 description 으로 바꾼다
#   - 캐릭터 그림(sprites, 표정과 차림마다)을 더한다. 있던 캐릭터는 빈 목록이다

# 이벤트 씬마다 키 하나를 바꾼다(from_key → to_key). 빈 목록은 그대로다
RENAME_KEY = """
UPDATE characters SET event_scenes = (
    SELECT jsonb_agg((scene - '{from_key}') || jsonb_build_object('{to_key}', scene -> '{from_key}'))
    FROM jsonb_array_elements(event_scenes) AS scene
) WHERE event_scenes <> '[]'::jsonb
"""


def upgrade() -> None:
    op.alter_column('characters', 'illustrations', new_column_name='event_scenes')
    op.execute(RENAME_KEY.format(from_key='scene', to_key='description'))
    op.add_column('characters', sa.Column('sprites', postgresql.JSONB(), server_default='[]', nullable=False))


def downgrade() -> None:
    op.drop_column('characters', 'sprites')
    op.execute(RENAME_KEY.format(from_key='description', to_key='scene'))
    op.alter_column('characters', 'event_scenes', new_column_name='illustrations')
