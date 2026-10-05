"""rulebook rules

Revision ID: 2f9f8f975f20
Revises: 32b4fdda6209
Create Date: 2026-10-05 19:32:24.805211

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '2f9f8f975f20'
down_revision: str | Sequence[str] | None = '32b4fdda6209'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 이 마이그레이션 전에 만든 룰북에 채워 넣는 규칙. 그때의 SRD5 템플릿(app/engine/templates.py)과 같은 값이다.
# 앱의 코드를 가져오지 않고 값을 여기에 적어 둔다. 마이그레이션은 그때의 DB 를 그때의 값으로 고친 기록이고,
# 앱의 코드는 나중에 바뀔 수 있다
RULES = {
    'template': 'srd5',
    'abilities': [
        {'key': 'str', 'name': '근력'},
        {'key': 'dex', 'name': '민첩'},
        {'key': 'con', 'name': '건강'},
        {'key': 'int', 'name': '지능'},
        {'key': 'wis', 'name': '지혜'},
        {'key': 'cha', 'name': '매력'},
    ],
    'score_min': 1,
    'score_max': 20,
    'modifier': {'base': 10, 'step': 2},
    'die': 20,
    'difficulties': [
        {'key': 'very_easy', 'name': '매우 쉬움', 'target': 5},
        {'key': 'easy', 'name': '쉬움', 'target': 10},
        {'key': 'medium', 'name': '보통', 'target': 15},
        {'key': 'hard', 'name': '어려움', 'target': 20},
        {'key': 'very_hard', 'name': '매우 어려움', 'target': 25},
    ],
    'default_difficulty': 'medium',
}


def upgrade() -> None:
    # 자동 생성은 "비울 수 없는 칸을 더한다" 한 줄만 만든다. 이미 룰북이 있으면 그 줄은 실패한다.
    # 그래서 셋으로 나눈다. 비울 수 있는 칸으로 더하고, 있던 행을 채우고, 비울 수 없게 바꾼다
    op.add_column('rulebooks', sa.Column('rules', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    fill = sa.text('UPDATE rulebooks SET rules = CAST(:rules AS JSONB)')
    op.execute(fill.bindparams(rules=json.dumps(RULES, ensure_ascii=False)))
    op.alter_column('rulebooks', 'rules', nullable=False)


def downgrade() -> None:
    op.drop_column('rulebooks', 'rules')
