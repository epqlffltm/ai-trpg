"""member character mode

Revision ID: a8c4e2f6b193
Revises: f1b6d3e8a920
Create Date: 2026-10-06 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a8c4e2f6b193'
down_revision: str | Sequence[str] | None = 'f1b6d3e8a920'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 값을 글자 그대로 적는다. 앱의 코드는 나중에 바뀔 수 있다

# 능력치를 지운 자리에 JSON 의 null 이라는 값이 남아 있을 수 있다. DB 의 NULL 로 바꾼다.
# 능력치를 적었다가 다른 방식으로 바꾸면 그렇게 적혔다. 그 값은 IS NULL 이 아니어서 아래의 조건들이 능력치가 있다고 본다
CLEAR_JSON_NULLS = "UPDATE table_members SET abilities = NULL WHERE jsonb_typeof(abilities) = 'null'"

# 이미 캐릭터를 만든 자리에 채워 넣는 방식. 그때 있던 방식은 셋이고, 자리에 적힌 것으로 어느 것인지 알 수 있다.
# 프리젠을 차지했으면 pregen, 능력치를 적었으면 manual, 둘 다 아니면 custom 이다
BACKFILL = """
    UPDATE table_members
    SET character_mode = CASE
        WHEN pregen_index IS NOT NULL THEN 'pregen'
        WHEN abilities IS NOT NULL THEN 'manual'
        ELSE 'custom'
    END
    WHERE character_name IS NOT NULL
"""

MODE_ALLOWED = "character_mode IN ('pregen', 'custom', 'manual')"
# 방식은 캐릭터가 있을 때만, 그리고 반드시 있다
MODE_NEEDS_CHARACTER = '(character_mode IS NULL) = (character_name IS NULL)'
# 프리젠을 차지한 자리는 프리젠 방식이고, 프리젠 방식인 자리는 프리젠을 차지하고 있다
PREGEN_NEEDS_PREGEN_MODE = "(pregen_index IS NOT NULL) = (character_mode IS NOT DISTINCT FROM 'pregen')"
# 플레이어가 정한 능력치는 그런 방식(pregen 도 custom 도 아닌 방식)의 캐릭터에만, 그리고 반드시 있다
ABILITIES_NEED_PLAYER_MADE_MODE = (
    "(abilities IS NOT NULL) = (character_mode IS NOT NULL AND character_mode NOT IN ('pregen', 'custom'))"
)
# 능력치는 이름표에서 점수로 가는 묶음이다
ABILITIES_IS_OBJECT = "abilities IS NULL OR jsonb_typeof(abilities) = 'object'"
# 이 마이그레이션이 없애는 옛 조건. 새 조건들이 같은 것을 더 좁게 막는다
ABILITIES_NEED_OWN_CHARACTER = 'abilities IS NULL OR (character_name IS NOT NULL AND pregen_index IS NULL)'


def upgrade() -> None:
    # 칸 하나는 자동 생성이 찾은 그대로다
    op.add_column('table_members', sa.Column('character_mode', sa.String(length=20), nullable=True))

    # 아래는 손으로 적었다. 자동 생성은 데이터를 채우지 않고, CHECK 가 생기거나 없어진 것을 찾지 못한다.
    # 먼저 고치고 채운 다음에 조건을 건다. 순서를 바꾸면 이미 캐릭터를 만든 자리가 조건에 걸린다
    op.execute(sa.text(CLEAR_JSON_NULLS))
    op.execute(sa.text(BACKFILL))
    op.create_check_constraint(op.f('ck_table_members_character_mode_allowed'), 'table_members', MODE_ALLOWED)
    op.create_check_constraint(
        op.f('ck_table_members_character_mode_needs_character'), 'table_members', MODE_NEEDS_CHARACTER
    )
    op.create_check_constraint(
        op.f('ck_table_members_pregen_needs_pregen_mode'), 'table_members', PREGEN_NEEDS_PREGEN_MODE
    )
    op.create_check_constraint(
        op.f('ck_table_members_abilities_need_player_made_mode'), 'table_members', ABILITIES_NEED_PLAYER_MADE_MODE
    )
    op.create_check_constraint(op.f('ck_table_members_abilities_is_object'), 'table_members', ABILITIES_IS_OBJECT)
    op.drop_constraint(op.f('ck_table_members_abilities_need_own_character'), 'table_members', type_='check')


def downgrade() -> None:
    op.create_check_constraint(
        op.f('ck_table_members_abilities_need_own_character'), 'table_members', ABILITIES_NEED_OWN_CHARACTER
    )
    op.drop_constraint(op.f('ck_table_members_abilities_is_object'), 'table_members', type_='check')
    # 칸을 지우면 그 칸에 걸린 CHECK 넷도 함께 사라진다
    op.drop_column('table_members', 'character_mode')
