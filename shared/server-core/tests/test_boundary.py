# shared/server-core/tests/test_boundary.py

"""
공용 코드의 경계를 지킨다(docs/architecture/shared-code.md 의 "재정의하는 법").

  - 공용 코드는 서버의 모듈(app.*)을 가져오지 않는다. 가져오면 쓰는 서버마다 뜻이 달라진다
  - 운영 코드는 테스트의 도구(server_core.testing)를 가져오지 않는다
  - 공용 코드는 다른 공용 패키지(ai_core 등)를 가져오지 않는다. AI 를 쓰지 않는 서버(알림, asset)가 그 의존을 끌고 온다

파일을 읽어 import 문만 본다. 불러오지 않으므로 순서나 조건부 import 에 상관없다.
"""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / 'src' / 'server_core'
# 가져오면 안 되는 이름의 앞부분
FORBIDDEN = ('app', 'tests', 'ai_core', 'conversation_core')
TESTING = 'server_core.testing'


def imported_modules(path: Path) -> list[str]:
    """그 파일이 가져오는 모듈의 이름들."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


def is_under(name: str, root: str) -> bool:
    return name == root or name.startswith(root + '.')


def source_files() -> list[Path]:
    return sorted(PACKAGE.rglob('*.py'))


def production_files() -> list[Path]:
    return [path for path in source_files() if 'testing' not in path.relative_to(PACKAGE).parts]


@pytest.mark.parametrize('path', source_files(), ids=lambda path: str(path.relative_to(PACKAGE)))
def test_does_not_import_a_server_or_another_shared_package(path: Path):
    found = [name for name in imported_modules(path) if any(is_under(name, root) for root in FORBIDDEN)]

    assert found == []


@pytest.mark.parametrize('path', production_files(), ids=lambda path: str(path.relative_to(PACKAGE)))
def test_production_code_does_not_import_the_test_tools(path: Path):
    assert [name for name in imported_modules(path) if is_under(name, TESTING)] == []


def test_the_files_are_found():
    # 경로가 틀려 아무것도 보지 않고 통과하는 일을 막는다
    assert len(production_files()) > 20
