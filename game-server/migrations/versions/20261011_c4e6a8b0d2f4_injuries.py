"""injuries

Revision ID: c4e6a8b0d2f4
Revises: a1c3e5f7b9d2
Create Date: 2026-10-11 22:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c4e6a8b0d2f4'
down_revision: str | Sequence[str] | None = 'a1c3e5f7b9d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 이 마이그레이션 전에 만든 룰북의 규칙에 채워 넣는 값. 부상, 부상 표, 부상 표를 굴리는 때, 노려 치기다.
# 그때의 SRD5 템플릿(app/engine/templates.py)과 같은 값이다. 앱의 코드를 가져오지 않고 여기에 적어 둔다
INJURY_RULES = {
    'injuries': [
        {
            'key': 'stunned',
            'name': '기절',
            'fact': '정신이 아득해 몸을 가누지 못한다. 아무것도 하지 못한다.',
            'effects': [{'kind': 'no_actions', 'abilities': [], 'amount': 0}],
            'healing': 'rounds',
            'rounds': 1,
            'aftermath': None,
            'aimable': False,
        },
        {
            'key': 'poisoned',
            'name': '중독',
            'fact': '독이 돌아 몸이 무겁고 속이 뒤집힌다.',
            'effects': [{'kind': 'disadvantage', 'abilities': [], 'amount': 0}],
            'healing': 'rounds',
            'rounds': 3,
            'aftermath': None,
            'aimable': False,
        },
        {
            'key': 'blinded',
            'name': '실명',
            'fact': '눈에 피가 들어가 앞을 보지 못한다.',
            'effects': [{'kind': 'disadvantage', 'abilities': ['dex', 'wis'], 'amount': 0}],
            'healing': 'rounds',
            'rounds': 3,
            'aftermath': None,
            'aimable': False,
        },
        {
            'key': 'deafened',
            'name': '귀먹음',
            'fact': '귀가 멍해 소리를 듣지 못한다.',
            'effects': [],
            'healing': 'rounds',
            'rounds': 3,
            'aftermath': None,
            'aimable': False,
        },
        {
            'key': 'broken_arm',
            'name': '팔 골절',
            'fact': '한쪽 팔이 부러져 제대로 쓰지 못한다.',
            'effects': [{'kind': 'disadvantage', 'abilities': ['str'], 'amount': 0}],
            'healing': 'heals',
            'rounds': 30,
            'aftermath': {
                'sides': 20,
                'rows': [{'low': 1, 'high': 5, 'injury': 'crooked_arm'}, {'low': 6, 'high': 20, 'injury': None}],
            },
            'aimable': True,
        },
        {
            'key': 'leg_wound',
            'name': '다리 부상',
            'fact': '다리를 깊이 다쳐 절뚝거린다.',
            'effects': [{'kind': 'disadvantage', 'abilities': ['dex'], 'amount': 0}],
            'healing': 'heals',
            'rounds': 20,
            'aftermath': {
                'sides': 20,
                'rows': [{'low': 1, 'high': 3, 'injury': 'limp'}, {'low': 4, 'high': 20, 'injury': None}],
            },
            'aimable': True,
        },
        {
            'key': 'lost_left_hand',
            'name': '왼손 잃음',
            'fact': '왼손이 없다. 왼손을 쓸 수 없다.',
            'effects': [{'kind': 'disadvantage', 'abilities': ['dex'], 'amount': 0}],
            'healing': 'permanent',
            'rounds': None,
            'aftermath': None,
            'aimable': True,
        },
        {
            'key': 'lost_right_hand',
            'name': '오른손 잃음',
            'fact': '오른손이 없다. 오른손을 쓸 수 없다.',
            'effects': [{'kind': 'disadvantage', 'abilities': ['dex'], 'amount': 0}],
            'healing': 'permanent',
            'rounds': None,
            'aftermath': None,
            'aimable': True,
        },
        {
            'key': 'lost_eye',
            'name': '한쪽 눈 잃음',
            'fact': '한쪽 눈을 잃어 거리를 잘 가늠하지 못한다.',
            'effects': [{'kind': 'penalty', 'abilities': ['wis'], 'amount': 2}],
            'healing': 'permanent',
            'rounds': None,
            'aftermath': None,
            'aimable': True,
        },
        {
            'key': 'deep_scar',
            'name': '깊은 흉터',
            'fact': '얼굴에 깊은 흉터가 남았다.',
            'effects': [],
            'healing': 'permanent',
            'rounds': None,
            'aftermath': None,
            'aimable': False,
        },
        {
            'key': 'crooked_arm',
            'name': '굽은 팔',
            'fact': '부러졌던 팔이 굽은 채로 붙었다.',
            'effects': [{'kind': 'penalty', 'abilities': ['str'], 'amount': 1}],
            'healing': 'permanent',
            'rounds': None,
            'aftermath': None,
            'aimable': False,
        },
        {
            'key': 'limp',
            'name': '절뚝거림',
            'fact': '다친 다리를 전다.',
            'effects': [{'kind': 'penalty', 'abilities': ['dex'], 'amount': 1}],
            'healing': 'permanent',
            'rounds': None,
            'aftermath': None,
            'aimable': False,
        },
    ],
    'injury_table': {
        'sides': 20,
        'rows': [
            {'low': 1, 'high': 10, 'injury': None},
            {'low': 11, 'high': 12, 'injury': 'stunned'},
            {'low': 13, 'high': 13, 'injury': 'blinded'},
            {'low': 14, 'high': 14, 'injury': 'deafened'},
            {'low': 15, 'high': 16, 'injury': 'leg_wound'},
            {'low': 17, 'high': 18, 'injury': 'broken_arm'},
            {'low': 19, 'high': 19, 'injury': 'deep_scar'},
            {'low': 20, 'high': 20, 'injury': 'lost_eye'},
        ],
    },
    'injury_triggers': {'big_hit_percent': 50, 'downed': True, 'called_shot': True},
    'called_shot': {'mode': 'target_plus', 'amount': 5},
}


def upgrade() -> None:
    # 룰북의 rules 문서에 칸 넷을 더한다. 이미 칸이 있는 룰북은 건드리지 않는다. 두 번 돌려도 결과가 같다
    for field, value in INJURY_RULES.items():
        fill = sa.text(
            f"UPDATE rulebooks SET rules = rules || jsonb_build_object('{field}', CAST(:value AS JSONB)) "
            f"WHERE NOT jsonb_exists(rules, '{field}')"
        )
        op.execute(fill.bindparams(value=json.dumps(value, ensure_ascii=False)))

    # 자동 생성이 찾은 그대로다. CHECK 조건과 조건이 붙은 색인은 모델과 같은 것을 직접 적는다
    op.create_table(
        'table_injuries',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=False),
        sa.Column('sheet_id', sa.Uuid(), nullable=True),
        sa.Column('npc_entry_id', sa.Uuid(), nullable=True),
        sa.Column('injury', sa.String(length=20), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('ends_after_round', sa.Integer(), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('(sheet_id IS NULL) <> (npc_entry_id IS NULL)', name=op.f('ck_table_injuries_one_holder')),
        sa.CheckConstraint(
            "source IN ('injury_table', 'called_shot', 'aftermath')", name=op.f('ck_table_injuries_source_allowed')
        ),
        sa.CheckConstraint('round_number >= 1', name=op.f('ck_table_injuries_round_number_positive')),
        sa.CheckConstraint(
            'ends_after_round IS NULL OR ends_after_round > round_number',
            name=op.f('ck_table_injuries_ends_after_start'),
        ),
        sa.ForeignKeyConstraint(
            ['sheet_id'], ['table_sheets.id'], name=op.f('fk_table_injuries_sheet_id_table_sheets'), ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['table_id', 'npc_entry_id'],
            ['table_npcs.table_id', 'table_npcs.entry_id'],
            name=op.f('fk_table_injuries_table_id_table_npcs'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['table_id'], ['game_tables.id'], name=op.f('fk_table_injuries_table_id_game_tables'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_table_injuries')),
    )
    op.create_index(
        'ix_table_injuries_active',
        'table_injuries',
        ['table_id'],
        unique=False,
        postgresql_where=sa.text('ended_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('ix_table_injuries_active', table_name='table_injuries', postgresql_where=sa.text('ended_at IS NULL'))
    op.drop_table('table_injuries')
    for field in INJURY_RULES:
        op.execute(sa.text(f"UPDATE rulebooks SET rules = rules - '{field}'"))
