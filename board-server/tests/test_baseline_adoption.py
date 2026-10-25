# board-server/tests/test_baseline_adoption.py

"""
기준선 마이그레이션이 TypeORM 이 만든 스키마를 넘겨받는 규칙(migrations/versions/..._board_baseline.py)을 검증한다.
DB 없이 SQL 의 목록만 본다. 실제 DB 에서 넘겨받는 것은 CI 가 아니라 TypeORM 의 스키마가 남은 PC 에서만 일어난다.

보는 것.
  - 마지막 마이그레이션까지 적용됐으면 더 할 것이 없다
  - 뒤의 둘(DropOperators, AllowWithdrawnAuthors)이 빠졌으면 그 SQL 을 차례대로 마저 한다
  - 그보다 앞의 것이 빠졌거나 기록이 없으면 넘겨받지 않고 멈춘다
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

VERSIONS = Path(__file__).resolve().parents[1] / 'migrations' / 'versions'


def load_baseline() -> ModuleType:
    """기준선 마이그레이션 파일을 모듈로 읽는다. 파일 이름이 숫자로 시작해 import 문으로는 읽지 못한다."""
    path = next(VERSIONS.glob('*_board_baseline.py'))
    spec = importlib.util.spec_from_file_location('board_baseline', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASELINE = load_baseline()
ALL = set(BASELINE.TYPEORM_MIGRATIONS)


def test_a_schema_at_the_last_migration_needs_nothing():
    assert BASELINE.catch_up_statements(ALL) == []


def test_the_last_migration_is_caught_up():
    statements = BASELINE.catch_up_statements(ALL - {'AllowWithdrawnAuthors1792600000000'})

    assert statements == [
        'ALTER TABLE "posts" ALTER COLUMN "author_id" DROP NOT NULL',
        'ALTER TABLE "comments" ALTER COLUMN "author_id" DROP NOT NULL',
        'ALTER TABLE "reports" ALTER COLUMN "reporter_id" DROP NOT NULL',
    ]


def test_the_last_two_are_caught_up_in_order():
    statements = BASELINE.catch_up_statements(
        ALL - {'DropOperators1792430000000', 'AllowWithdrawnAuthors1792600000000'}
    )

    assert statements[0] == 'DROP TABLE IF EXISTS "operators"'
    assert len(statements) == 4


@pytest.mark.parametrize('applied', [set(), ALL - {'AddOutgoingNotifications1792340930107'}])
def test_an_older_gap_stops_the_adoption(applied: set[str]):
    with pytest.raises(BASELINE.IncompleteTypeormSchema, match='넘겨받지 않습니다'):
        BASELINE.catch_up_statements(applied)
