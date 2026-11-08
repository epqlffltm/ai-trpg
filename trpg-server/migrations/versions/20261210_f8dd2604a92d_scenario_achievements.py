"""scenario achievements

Revision ID: f8dd2604a92d
Revises: fc73676e9587
Create Date: 2026-12-10 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'f8dd2604a92d'
down_revision: str | Sequence[str] | None = 'fc73676e9587'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 시나리오의 업적. 제작자가 작품에 다는 것이다(스팀의 업적과 같다). 인증 서버의 활동 배지와는 다른 것이다.
#   - scenarios.achievements: {id, name, description, hidden, image_id, when, match} 의 목록.
#     있던 시나리오는 빈 목록이다.
#     굳힌 판은 고치지 않는다. 판의 achievements 는 비워도 되는 칸이라 없으면 빈 목록이다
#   - player_achievements: 계정마다, 시나리오마다 받은 업적. 한 번이다
#   - scenario_players: 시나리오를 플레이한 계정. 달성률의 분모다. 있던 테이블의 플레이는 세지 않는다(이제부터 센다)
# 업적을 주는 엔진(라운드가 닫힐 때)은 따로 더한다. 그때까지 기록은 비어 있다
# 되돌리면 업적과 받은 기록을 모두 잃는다


def upgrade() -> None:
    op.add_column(
        'scenarios',
        sa.Column(
            'achievements',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f('ck_scenarios_achievements_count'), 'scenarios', 'jsonb_array_length(achievements) <= 50'
    )
    op.create_table(
        'player_achievements',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('scenario_id', sa.Uuid(), nullable=False),
        sa.Column('achievement_id', sa.String(length=40), nullable=False),
        sa.Column('table_id', sa.Uuid(), nullable=True),
        sa.Column('earned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['scenario_id'],
            ['scenarios.asset_id'],
            name=op.f('fk_player_achievements_scenario_id_scenarios'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['table_id'],
            ['game_tables.id'],
            name=op.f('fk_player_achievements_table_id_game_tables'),
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('user_id', 'scenario_id', 'achievement_id', name=op.f('pk_player_achievements')),
    )
    op.create_index(
        'ix_player_achievements_scenario_achievement',
        'player_achievements',
        ['scenario_id', 'achievement_id'],
        unique=False,
    )
    op.create_table(
        'scenario_players',
        sa.Column('scenario_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('first_played_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['scenario_id'],
            ['scenarios.asset_id'],
            name=op.f('fk_scenario_players_scenario_id_scenarios'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('scenario_id', 'user_id', name=op.f('pk_scenario_players')),
    )
    op.create_index(op.f('ix_scenario_players_user_id'), 'scenario_players', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_scenario_players_user_id'), table_name='scenario_players')
    op.drop_table('scenario_players')
    op.drop_index('ix_player_achievements_scenario_achievement', table_name='player_achievements')
    op.drop_table('player_achievements')
    op.drop_constraint(op.f('ck_scenarios_achievements_count'), 'scenarios', type_='check')
    op.drop_column('scenarios', 'achievements')
