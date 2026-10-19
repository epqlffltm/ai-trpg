"""sheet per character

Revision ID: f6b8d0e2a4c5
Revises: e5a7c9d1f3b4
Create Date: 2026-10-08 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f6b8d0e2a4c5'
down_revision: str | Sequence[str] | None = 'e5a7c9d1f3b4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 있던 시트에 누구의 시트인지를 적는다. 지금까지는 한 사람에 시트가 하나였다. 자리의 캐릭터가 곧 그 시트의 캐릭터다.
# 시트는 시작할 때 주고, 시작하려면 모두가 캐릭터를 정해야 했다. 그래서 이름은 있다.
# COALESCE: 그래도 이름이 비어 있는 자리가 있으면 빈 글로 채운다. 한 행 때문에 마이그레이션이 멈추지 않게 한다
COPY_CHARACTERS = """
    UPDATE table_sheets AS sheets
    SET character_name = COALESCE(members.character_name, ''), pregen_index = members.pregen_index
    FROM table_members AS members
    WHERE members.table_id = sheets.table_id AND members.user_id = sheets.user_id
"""

# 되돌릴 때: 한 사람에 시트가 하나이던 때로 돌아가려면 지금 캐릭터의 것만 남겨야 한다. 떠난 캐릭터의 시트는 사라진다
DROP_FALLEN = """
    DELETE FROM table_sheets AS sheets
    WHERE sheets.number < (
        SELECT MAX(latest.number) FROM table_sheets AS latest
        WHERE latest.table_id = sheets.table_id AND latest.user_id = sheets.user_id
    )
"""


def upgrade() -> None:
    # 있던 시트는 그 사람의 첫 캐릭터의 것이고, 있던 굴림은 첫 캐릭터를 위해 굴린 것이다. 칸의 기본값(1)이 채운다
    op.add_column('table_sheets', sa.Column('number', sa.SmallInteger(), server_default=sa.text('1'), nullable=False))
    op.add_column(
        'table_rolls', sa.Column('character_number', sa.SmallInteger(), server_default=sa.text('1'), nullable=False)
    )
    op.add_column('table_sheets', sa.Column('pregen_index', sa.SmallInteger(), nullable=True))

    # 이름은 비어 있을 수 없는 칸이다. 비어 있어도 되는 칸으로 만들고, 있던 행을 채운 다음에, 비어 있을 수 없게 바꾼다.
    # 처음부터 비어 있을 수 없게 만들면 있던 행 때문에 DB 가 거부한다
    op.add_column('table_sheets', sa.Column('character_name', sa.String(length=50), nullable=True))
    op.execute(COPY_CHARACTERS)
    op.alter_column('table_sheets', 'character_name', nullable=False)

    # 한 사람에 시트가 하나라는 조건을 풀고, 같은 번호가 둘일 수 없다는 조건으로 바꾼다
    op.drop_constraint(op.f('uq_table_sheets_table_id'), 'table_sheets', type_='unique')
    op.create_unique_constraint('uq_table_sheets_number', 'table_sheets', ['table_id', 'user_id', 'number'])
    # 한 사람의 살아 있는 캐릭터는 하나뿐이다
    op.create_index(
        'uq_table_sheets_living',
        'table_sheets',
        ['table_id', 'user_id'],
        unique=True,
        postgresql_where='died_at IS NULL',
    )
    # 프리젠 하나는 한 테이블에서 한 번만 시트를 받는다
    op.create_unique_constraint('uq_table_sheets_pregen', 'table_sheets', ['table_id', 'pregen_index'])

    # 아래는 손으로 적었다. 자동 생성은 CHECK 가 생긴 것을 찾지 못한다
    op.create_check_constraint(op.f('ck_table_sheets_number_positive'), 'table_sheets', 'number >= 1')
    op.create_check_constraint(op.f('ck_table_rolls_character_number_positive'), 'table_rolls', 'character_number >= 1')


def downgrade() -> None:
    op.execute(DROP_FALLEN)
    op.drop_constraint('uq_table_sheets_pregen', 'table_sheets', type_='unique')
    op.drop_index('uq_table_sheets_living', table_name='table_sheets', postgresql_where='died_at IS NULL')
    op.drop_constraint('uq_table_sheets_number', 'table_sheets', type_='unique')
    op.create_unique_constraint(op.f('uq_table_sheets_table_id'), 'table_sheets', ['table_id', 'user_id'])
    # 칸을 지우면 그 칸에 걸린 CHECK 도 함께 사라진다
    op.drop_column('table_sheets', 'character_name')
    op.drop_column('table_sheets', 'pregen_index')
    op.drop_column('table_rolls', 'character_number')
    op.drop_column('table_sheets', 'number')
