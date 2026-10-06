"""manual abilities

Revision ID: e3a9c1d5b7f2
Revises: c7d2e8a1f504
Create Date: 2026-10-06 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'e3a9c1d5b7f2'
down_revision: str | Sequence[str] | None = 'c7d2e8a1f504'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 방식의 목록을 가진 표 둘. 같은 조건이 양쪽에 걸려 있다
TABLES_WITH_MODES = ('scenarios', 'game_tables')

# 허용하는 캐릭터 방식. 값을 글자 그대로 적는다. 앱의 코드는 나중에 바뀔 수 있다
OLD_MODES = "cardinality(character_modes) >= 1 AND character_modes <@ ARRAY['pregen', 'custom']::varchar[]"
NEW_MODES = "cardinality(character_modes) >= 1 AND character_modes <@ ARRAY['pregen', 'custom', 'manual']::varchar[]"

# 기준값과 상한은 함께 있거나 함께 없다. 있으면 1 이상이고, 기준값이 상한을 넘지 않는다
PLAYER_MADE_HP = (
    '(hp_base IS NULL) = (hp_cap IS NULL) AND '
    '(hp_base IS NULL OR (hp_base >= 1 AND hp_base <= hp_cap AND hp_cap <= 999))'
)

# 직접 정한 능력치는 직접 만든 캐릭터에만 있다
ABILITIES_NEED_OWN_CHARACTER = 'abilities IS NULL OR (character_name IS NOT NULL AND pregen_index IS NULL)'


def replace_modes_check(condition: str) -> None:
    """방식의 조건을 두 표에서 바꿔 건다. CHECK 는 고칠 수 없어서 지우고 다시 만든다."""
    for table in TABLES_WITH_MODES:
        name = op.f(f'ck_{table}_character_modes_allowed')
        op.drop_constraint(name, table, type_='check')
        op.create_check_constraint(name, table, condition)


def upgrade() -> None:
    # 칸 셋은 자동 생성이 찾은 그대로다
    op.add_column('scenarios', sa.Column('hp_base', sa.SmallInteger(), nullable=True))
    op.add_column('scenarios', sa.Column('hp_cap', sa.SmallInteger(), nullable=True))
    op.add_column('table_members', sa.Column('abilities', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # 아래는 손으로 적었다. 자동 생성은 CHECK 가 생기거나 바뀐 것을 찾지 못한다
    op.create_check_constraint(op.f('ck_scenarios_player_made_hp'), 'scenarios', PLAYER_MADE_HP)
    op.create_check_constraint(
        op.f('ck_table_members_abilities_need_own_character'), 'table_members', ABILITIES_NEED_OWN_CHARACTER
    )
    replace_modes_check(NEW_MODES)


def downgrade() -> None:
    # 옛 조건은 manual 을 모른다. 조건을 되돌리기 전에 그 값을 목록에서 뺀다.
    # 그 값만 있던 목록은 비게 되므로 처음의 둘로 채운다
    for table in TABLES_WITH_MODES:
        op.execute(sa.text(f"UPDATE {table} SET character_modes = array_remove(character_modes, 'manual')"))
        op.execute(
            sa.text(f"UPDATE {table} SET character_modes = '{{pregen,custom}}' WHERE cardinality(character_modes) = 0")
        )
    replace_modes_check(OLD_MODES)

    # 칸을 지우면 그 칸에 걸린 CHECK 도 함께 사라진다
    op.drop_column('table_members', 'abilities')
    op.drop_column('scenarios', 'hp_cap')
    op.drop_column('scenarios', 'hp_base')
