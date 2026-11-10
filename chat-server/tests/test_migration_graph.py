# chat-server/tests/test_migration_graph.py

"""
마이그레이션의 사슬이 뿌리 하나(기준선, #1273)에서 시작하는지 본다. DB 없이 마이그레이션 폴더만 읽는다.

끝(head)은 여럿이어도 된다. 함께 일하는 PR 들이 각자 마이그레이션을 더하고, 적용은 upgrade heads 로 모두 한다.
뿌리가 둘이 되는 것은 실수뿐이다(부모를 적지 않은 새 마이그레이션). 그래도 upgrade heads 는 지나가므로 여기서 잡는다.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

SERVER_ROOT = Path(__file__).resolve().parents[1]


def scripts() -> ScriptDirectory:
    """이 서버의 마이그레이션 폴더. alembic.ini 의 설정 그대로 읽는다."""
    return ScriptDirectory.from_config(Config(str(SERVER_ROOT / 'alembic.ini')))


def test_the_chain_has_one_root():
    assert len(scripts().get_bases()) == 1
