# asset-server/tests/test_content_boundary.py

"""
app/content 가 app.* 를 가져오지 않는지 본다(2026-10-21 결정).

소개 글의 거르기는 두 번째로 쓰는 곳이 생기면 파일째 shared/ 로 옮긴다. 그때 import 만 바꾸면 되게,
이 폴더는 자기 폴더(app.content) 말고는 앱의 코드를 모른다. 바깥 라이브러리(nh3)와 표준 라이브러리만 쓴다.
"""

import ast
from pathlib import Path

CONTENT = Path(__file__).resolve().parents[1] / 'app' / 'content'


def imported_modules(path: Path) -> list[str]:
    """파일이 가져오는 모듈의 이름들."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append('.' * node.level + (node.module or ''))
    return names


def test_content_imports_nothing_else_from_the_app():
    files = sorted(CONTENT.glob('*.py'))
    leaks = {
        path.name: [
            name for name in imported_modules(path) if name.startswith('app') and not name.startswith('app.content')
        ]
        for path in files
    }

    assert files
    assert {name: found for name, found in leaks.items() if found} == {}


def test_relative_imports_outside_the_folder_are_caught(tmp_path: Path):
    path = tmp_path / 'leak.py'
    path.write_text('from app.core import config\nfrom ..auth import tokens\nimport nh3\n', encoding='utf-8')

    assert imported_modules(path) == ['app.core', '..auth', 'nh3']
