"""monster xp

Revision ID: a4b6c8d0e2f4
Revises: f3a5b7c9d1e2
Create Date: 2026-11-23 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a4b6c8d0e2f4'
down_revision: str | Sequence[str] | None = 'f3a5b7c9d1e2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 몬스터와 판의 사건이 주는 경험치(#286 ②). 시나리오에 받는 사람들이 나누는 법(xp_split, 기본 share)을,
# 테이블의 마리에 경험치를 이미 줬는지(xp_given)를 둔다.
# 이미 쓰러지거나 죽은 마리는 준 것으로 채운다. 이 단계가 오기 전에 쓰러뜨린 마리가 다음 닫힘에 경험치를 주지 않게 한다.
# 시나리오의 몬스터 시트의 경험치(xp)와 사건의 경험치 주기(give_xp)는 비워도 되는 칸이라 올릴 때 고치지 않는다.
# 되돌리면 두 칸을 지우고, 몬스터 시트에서 경험치를, 사건에서 경험치 주기를 뺀다(효과가 남지 않는 사건은 지운다.
# 그때의 모양은 효과가 하나 이상이어야 한다). 앱의 코드를 가져오지 않는다


def sheet_without_xp(sheet: dict) -> dict:
    """되돌릴 때. 몬스터 시트 하나에서 경험치를 뺀다."""
    return {key: value for key, value in sheet.items() if key != 'xp'}


def happenings_without_xp(rules: list[dict]) -> list[dict]:
    """되돌릴 때. 사건마다 경험치 주기를 빼고, 효과가 남지 않은 사건은 지운다."""
    kept = [{**rule, 'effects': [one for one in rule['effects'] if one.get('kind') != 'give_xp']} for rule in rules]
    return [rule for rule in kept if rule['effects']]


def rewrite_scenarios(connection: sa.Connection) -> None:
    """되돌릴 때. 모든 시나리오의 몬스터 시트와 사건을 고쳐 쓴다. 바뀐 것만 적는다."""
    rows = connection.execute(sa.text('SELECT asset_id, monster_sheets, happenings FROM scenarios')).all()
    for scenario_id, sheets, happenings in rows:
        changed_sheets = [sheet_without_xp(sheet) for sheet in sheets or []]
        changed_happenings = happenings_without_xp(happenings or [])
        if changed_sheets != (sheets or []) or changed_happenings != (happenings or []):
            connection.execute(
                sa.text(
                    'UPDATE scenarios SET monster_sheets = CAST(:sheets AS JSONB), '
                    'happenings = CAST(:happenings AS JSONB) WHERE asset_id = :id'
                ),
                {'sheets': json.dumps(changed_sheets), 'happenings': json.dumps(changed_happenings), 'id': scenario_id},
            )


def upgrade() -> None:
    op.add_column(
        'scenarios', sa.Column('xp_split', sa.String(length=10), server_default=sa.text("'share'"), nullable=False)
    )
    op.create_check_constraint(op.f('ck_scenarios_xp_split_allowed'), 'scenarios', "xp_split IN ('each', 'share')")
    op.add_column(
        'table_monsters', sa.Column('xp_given', sa.Boolean(), server_default=sa.text('false'), nullable=False)
    )
    op.execute("UPDATE table_monsters SET xp_given = true WHERE status <> 'alive'")


def downgrade() -> None:
    op.drop_column('table_monsters', 'xp_given')
    op.drop_constraint(op.f('ck_scenarios_xp_split_allowed'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'xp_split')
    rewrite_scenarios(op.get_bind())
