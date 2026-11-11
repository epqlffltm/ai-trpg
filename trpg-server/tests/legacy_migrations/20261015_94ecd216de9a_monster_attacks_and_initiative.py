"""monster attacks and initiative

Revision ID: 94ecd216de9a
Revises: 4cf01d0802ce
Create Date: 2026-10-15 08:15:23.623112

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '94ecd216de9a'
down_revision: str | Sequence[str] | None = '4cf01d0802ce'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 이 마이그레이션 전에 만든 룰북의 규칙에 채워 넣는 차례의 능력치. 그때의 SRD5 템플릿(app/engine/templates.py)과
# 같은 값이다. 앱의 코드를 가져오지 않고 여기에 적어 둔다. 그 능력치가 없는 규칙은 null(능력치로 정하지 않음)이다
INITIATIVE_ABILITY = 'dex'


def upgrade() -> None:
    # 있던 몬스터는 일반 몹이다
    op.add_column('monsters', sa.Column('unique', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    # 있던 테이블의 몬스터는 아직 아무도 만나지 않았다.
    # 조건은 손으로 적었다. 자동 생성은 있던 표에 더한 CHECK 를 찾지 못한다
    op.add_column('table_monsters', sa.Column('engaged_round', sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f('ck_table_monsters_engaged_round_positive'),
        'table_monsters',
        'engaged_round IS NULL OR engaged_round >= 1',
    )
    # 표의 모양은 그대로다. rules 문서 안에 칸 하나를 더한다. 이미 그 칸이 있는 룰북은 건드리지 않는다.
    # 능력치에 dex 가 있으면 dex, 없으면 null 이다
    fill = sa.text(
        'UPDATE rulebooks SET rules = rules || jsonb_build_object('
        "'initiative_ability', "
        "CASE WHEN EXISTS (SELECT 1 FROM jsonb_array_elements(rules -> 'abilities') AS ability "
        "WHERE ability ->> 'key' = CAST(:key AS TEXT)) THEN to_jsonb(CAST(:key AS TEXT)) ELSE 'null'::jsonb END) "
        "WHERE NOT jsonb_exists(rules, 'initiative_ability')"
    )
    op.execute(fill.bindparams(key=INITIATIVE_ABILITY))


def downgrade() -> None:
    op.execute(sa.text("UPDATE rulebooks SET rules = rules - 'initiative_ability'"))
    op.drop_constraint(op.f('ck_table_monsters_engaged_round_positive'), 'table_monsters', type_='check')
    op.drop_column('table_monsters', 'engaged_round')
    op.drop_column('monsters', 'unique')
