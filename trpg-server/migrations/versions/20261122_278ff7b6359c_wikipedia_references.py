"""wikipedia references

Revision ID: 278ff7b6359c
Revises: fbdb2bc58f5e
Create Date: 2026-11-22 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = '278ff7b6359c'
down_revision: str | Sequence[str] | None = 'fbdb2bc58f5e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 위키백과를 참고 자료로(#482 의 남은 줄).
#   - reference_entries.source 에 wikipedia, kind 에 topic(일반 지식)을 더한다
# 되돌리면 위키백과의 줄과 topic 의 줄을 지우고(벡터도 함께 지워진다) 옛 조건으로 돌린다


def upgrade() -> None:
    op.drop_constraint(op.f('ck_reference_entries_source_allowed'), 'reference_entries', type_='check')
    op.create_check_constraint(
        op.f('ck_reference_entries_source_allowed'), 'reference_entries', "source IN ('srd51', 'wikipedia')"
    )
    op.drop_constraint(op.f('ck_reference_entries_kind_allowed'), 'reference_entries', type_='check')
    op.create_check_constraint(
        op.f('ck_reference_entries_kind_allowed'), 'reference_entries', "kind IN ('monster', 'item', 'topic')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM reference_entries WHERE source = 'wikipedia' OR kind = 'topic'")
    op.drop_constraint(op.f('ck_reference_entries_kind_allowed'), 'reference_entries', type_='check')
    op.create_check_constraint(
        op.f('ck_reference_entries_kind_allowed'), 'reference_entries', "kind IN ('monster', 'item')"
    )
    op.drop_constraint(op.f('ck_reference_entries_source_allowed'), 'reference_entries', type_='check')
    op.create_check_constraint(op.f('ck_reference_entries_source_allowed'), 'reference_entries', "source IN ('srd51')")
