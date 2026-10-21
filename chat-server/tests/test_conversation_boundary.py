# chat-server/tests/test_conversation_boundary.py

"""
대화의 핵심(app/conversation)이 앱의 다른 코드를 가져오지 않는지 본다(#590).

app/conversation 은 story-server 를 만들 때 파일째 shared/conversation-core 로 옮긴다.
chat 만의 폴더(캐릭터, 호감도, 그림)나 앱의 설정(app.core)을 가져오면 옮길 때 끊어진다.
그래서 자기 폴더(app.conversation) 말고는 앱의 코드를 모른다. 공용 코드(server_core)와 바깥 라이브러리는 쓴다.
"""

import ast
from pathlib import Path

CONVERSATION = Path(__file__).resolve().parents[1] / 'app' / 'conversation'


def imported_modules(path: Path) -> list[str]:
    """파일이 가져오는 모듈의 이름들. 상대 경로는 점의 수를 앞에 붙인다."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append('.' * node.level + (node.module or ''))
    return names


def leaks(path: Path) -> list[str]:
    """
    가져오면 안 되는 것들. app.conversation 밖의 app.* 와, 폴더 밖으로 나가는 상대 경로(..)다.

    한 점(.)은 같은 폴더라 괜찮다.
    """
    return [
        name
        for name in imported_modules(path)
        if ((name == 'app' or name.startswith('app.')) and not name.startswith('app.conversation'))
        or name.startswith('..')
    ]


def test_the_conversation_core_imports_nothing_else_from_the_app():
    files = sorted(CONVERSATION.rglob('*.py'))

    assert files
    assert {path.name: leaks(path) for path in files if leaks(path)} == {}


def test_leaks_are_caught(tmp_path: Path):
    path = tmp_path / 'leak.py'
    path.write_text(
        'import app\nfrom app.core import config\nfrom app.characters import cards\nfrom ..core import x\n'
        'from app.conversation import tree\nfrom . import summary\n'
        'from server_core.database import NAMING_CONVENTION\n',
        encoding='utf-8',
    )

    assert leaks(path) == ['app', 'app.core', 'app.characters', '..core']
