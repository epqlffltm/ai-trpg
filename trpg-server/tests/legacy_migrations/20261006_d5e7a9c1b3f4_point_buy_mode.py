"""point buy mode

Revision ID: d5e7a9c1b3f4
Revises: a8c4e2f6b193
Create Date: 2026-10-06 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd5e7a9c1b3f4'
down_revision: str | Sequence[str] | None = 'a8c4e2f6b193'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 값을 글자 그대로 적는다. 앱의 코드는 나중에 바뀔 수 있다
OLD_MODES = "'pregen', 'custom', 'manual'"
NEW_MODES = "'pregen', 'custom', 'manual', 'point_buy'"

# 허용하는 방식의 목록을 가진 표 둘. 같은 조건이 양쪽에 걸려 있다
TABLES_WITH_MODES = ('scenarios', 'game_tables')


def modes_allowed(modes: str) -> str:
    """허용하는 방식의 목록에 거는 조건. 하나 이상이고, 모두 아는 방식이다."""
    return f'cardinality(character_modes) >= 1 AND character_modes <@ ARRAY[{modes}]::varchar[]'


def mode_allowed(modes: str) -> str:
    """자리에 적힌 방식 하나에 거는 조건."""
    return f'character_mode IN ({modes})'


def replace_checks(modes: str) -> None:
    """방식의 값을 적어 둔 조건 셋을 바꿔 건다. CHECK 는 고칠 수 없어서 지우고 다시 만든다."""
    for table in TABLES_WITH_MODES:
        name = op.f(f'ck_{table}_character_modes_allowed')
        op.drop_constraint(name, table, type_='check')
        op.create_check_constraint(name, table, modes_allowed(modes))
    name = op.f('ck_table_members_character_mode_allowed')
    op.drop_constraint(name, 'table_members', type_='check')
    op.create_check_constraint(name, 'table_members', mode_allowed(modes))


def upgrade() -> None:
    # 표의 모양은 그대로다. 조건만 바뀐다. 자동 생성은 CHECK 가 바뀐 것을 찾지 못해서 아무것도 내놓지 않는다.
    # 능력치가 있어야 하는 방식인지를 보는 조건(abilities_need_player_made_mode)은 그대로 둔다.
    # "pregen 도 custom 도 아닌 방식"이라고 적어 둔 조건이라, 방식이 늘어도 바꿀 것이 없다
    replace_checks(NEW_MODES)


def downgrade() -> None:
    # 옛 조건은 point_buy 를 모른다. 조건을 되돌리기 전에 그 값을 없앤다.
    # 점수제로 만든 캐릭터는 지킨 제한이 더 많을 뿐 직접 적은 것과 모양이 같다. manual 로 바꿔 둔다
    op.execute(sa.text("UPDATE table_members SET character_mode = 'manual' WHERE character_mode = 'point_buy'"))
    # 그 값만 있던 목록은 비게 되므로 처음의 둘로 채운다
    for table in TABLES_WITH_MODES:
        op.execute(sa.text(f"UPDATE {table} SET character_modes = array_remove(character_modes, 'point_buy')"))
        op.execute(
            sa.text(f"UPDATE {table} SET character_modes = '{{pregen,custom}}' WHERE cardinality(character_modes) = 0")
        )
    replace_checks(OLD_MODES)
