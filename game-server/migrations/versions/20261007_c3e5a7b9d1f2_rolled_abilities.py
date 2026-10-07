"""rolled abilities

Revision ID: c3e5a7b9d1f2
Revises: b2d4f6a8c0e1
Create Date: 2026-10-07 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c3e5a7b9d1f2'
down_revision: str | Sequence[str] | None = 'b2d4f6a8c0e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 값을 글자 그대로 적는다. 앱의 코드는 나중에 바뀔 수 있다
OLD_MODES = "'pregen', 'custom', 'manual', 'point_buy'"
NEW_MODES = "'pregen', 'custom', 'manual', 'point_buy', 'rolled'"

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
    # 표 하나와 칸 하나는 자동 생성이 찾은 그대로다
    op.create_table(
        'table_rolls',
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('dice', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('scores', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('times_rolled', sa.SmallInteger(), nullable=False),
        sa.Column('reroll_granted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('rolled_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(dice) = 'array' AND jsonb_typeof(scores) = 'array'",
            name=op.f('ck_table_rolls_rolls_are_arrays'),
        ),
        sa.CheckConstraint('times_rolled >= 1', name=op.f('ck_table_rolls_times_rolled_positive')),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_rolls_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('table_id', 'user_id', name=op.f('pk_table_rolls')),
    )
    # 있던 시나리오는 다시 굴리게 해 줄 수 없는 것으로 채운다. 그 방식 자체가 없었다
    op.add_column(
        'scenarios', sa.Column('reroll_allowed', sa.Boolean(), server_default=sa.text('false'), nullable=False)
    )

    # 아래는 손으로 적었다. 자동 생성은 CHECK 가 바뀐 것을 찾지 못한다
    replace_checks(NEW_MODES)


def downgrade() -> None:
    # 옛 조건은 rolled 를 모른다. 조건을 되돌리기 전에 그 값을 없앤다.
    # 주사위로 만든 캐릭터는 지킨 제한이 더 많을 뿐 직접 적은 것과 모양이 같다. manual 로 바꿔 둔다
    op.execute(sa.text("UPDATE table_members SET character_mode = 'manual' WHERE character_mode = 'rolled'"))
    # 그 값만 있던 목록은 비게 되므로 처음의 둘로 채운다
    for table in TABLES_WITH_MODES:
        op.execute(sa.text(f"UPDATE {table} SET character_modes = array_remove(character_modes, 'rolled')"))
        op.execute(
            sa.text(f"UPDATE {table} SET character_modes = '{{pregen,custom}}' WHERE cardinality(character_modes) = 0")
        )
    replace_checks(OLD_MODES)

    op.drop_column('scenarios', 'reroll_allowed')
    op.drop_table('table_rolls')
