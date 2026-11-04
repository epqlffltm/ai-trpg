"""hearts

캐릭터와 세계관의 관심(하트, #989). 한 사람이 작품 하나에 한 번 둔다. 작품에 관심의 수를 적어 둔다.

Revision ID: be46a6face87
Revises: b4d6f8a0c2e5
Create Date: 2026-11-30 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'be46a6face87'
down_revision: str | Sequence[str] | None = 'b4d6f8a0c2e5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'character_hearts',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('character_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['character_id'],
            ['characters.id'],
            name=op.f('fk_character_hearts_character_id_characters'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('user_id', 'character_id', name=op.f('pk_character_hearts')),
    )
    op.create_index(op.f('ix_character_hearts_character_id'), 'character_hearts', ['character_id'], unique=False)
    op.create_index('ix_character_hearts_user_created', 'character_hearts', ['user_id', 'created_at'], unique=False)
    op.create_table(
        'world_hearts',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('world_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['world_id'], ['worlds.id'], name=op.f('fk_world_hearts_world_id_worlds'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('user_id', 'world_id', name=op.f('pk_world_hearts')),
    )
    op.create_index('ix_world_hearts_user_created', 'world_hearts', ['user_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_world_hearts_world_id'), 'world_hearts', ['world_id'], unique=False)
    op.add_column('characters', sa.Column('heart_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('worlds', sa.Column('heart_count', sa.Integer(), server_default='0', nullable=False))
    op.create_check_constraint(op.f('ck_characters_heart_count_not_negative'), 'characters', 'heart_count >= 0')
    op.create_check_constraint(op.f('ck_worlds_heart_count_not_negative'), 'worlds', 'heart_count >= 0')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_worlds_heart_count_not_negative'), 'worlds', type_='check')
    op.drop_constraint(op.f('ck_characters_heart_count_not_negative'), 'characters', type_='check')
    op.drop_column('worlds', 'heart_count')
    op.drop_column('characters', 'heart_count')
    op.drop_index(op.f('ix_world_hearts_world_id'), table_name='world_hearts')
    op.drop_index('ix_world_hearts_user_created', table_name='world_hearts')
    op.drop_table('world_hearts')
    op.drop_index('ix_character_hearts_user_created', table_name='character_hearts')
    op.drop_index(op.f('ix_character_hearts_character_id'), table_name='character_hearts')
    op.drop_table('character_hearts')
