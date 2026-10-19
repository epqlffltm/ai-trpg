# game-server/tests/test_ai_boundary.py

"""
AI 를 부르는 코드(app/ai)가 app.ai 밖의 app.* 를 가져오지 않는 것을 지킨다(#498, docs/architecture/shared-code.md).

app/ai 는 나중에 공용 코드(shared/ai-core)로 옮길 후보다. 옮길 때 다른 폴더를 끌고 가지 않도록 경계를 지금 지킨다.
모델 목록의 계약(app/ai/catalog_contract.py, #496)과 호출 기록의 표(app/ai_log, #497)를 나눈 뒤의 경계다.

  - app/ai 의 모든 .py 를 ast 로 읽는다. 실행하지 않는다. import 문을 모두 본다(TYPE_CHECKING 안의 것도).
  - app.ai 와 app.ai.* 는 된다. 그 밖의 app 과 app.* 는 안 된다. 표준 라이브러리와 바깥 패키지는 보지 않는다.
  - 상대 import 는 app/ai 안에서 풀어 본다. app/ai 밖으로 나가면 안 된다.
  - 예외를 두지 않는다. 필요하면 경계를 다시 의논한다(문서의 "주도권").
맨 아래에는 판별 함수 자체의 테스트가 있다.
"""

import ast
import pathlib

import pytest

# 지키는 폴더와 그 패키지 이름
AI_DIR = pathlib.Path(__file__).parent.parent / 'app' / 'ai'
AI_PACKAGE = 'app.ai'
APP_PACKAGE = 'app'


def package_of(path: pathlib.Path) -> str:
    """파일이 속한 패키지의 이름. app/ai/x.py 는 app.ai, app/ai/__init__.py 도 app.ai 다."""
    relative = path.relative_to(AI_DIR.parent.parent).with_suffix('')
    parts = list(relative.parts)
    return '.'.join(parts[:-1])


def resolve(node: ast.ImportFrom, package: str) -> str:
    """from 문이 가리키는 모듈의 이름. 상대 import(level 이 1 이상)는 그 파일의 패키지에서 풀어 본다."""
    if node.level == 0:
        return node.module or ''
    base = package.split('.')
    anchor = base[: len(base) - (node.level - 1)] if node.level - 1 <= len(base) else []
    return '.'.join([*anchor, *([node.module] if node.module else [])])


def imported_modules(source: str, package: str) -> list[str]:
    """파일이 가져오는 모듈의 이름들. import 문과 from 문을 모두 본다."""
    names = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(resolve(node, package))
    return names


def crosses(module: str) -> bool:
    """app.ai 밖의 app 모듈인가. app 자체와 app.ai 가 아닌 app.* 가 그렇다."""
    inside_app = module == APP_PACKAGE or module.startswith(f'{APP_PACKAGE}.')
    inside_ai = module == AI_PACKAGE or module.startswith(f'{AI_PACKAGE}.')
    return inside_app and not inside_ai


def crossings(path: pathlib.Path) -> list[str]:
    """그 파일이 넘는 import 들. 없으면 빈 목록이다."""
    return [module for module in imported_modules(path.read_text(), package_of(path)) if crosses(module)]


def ai_files() -> list[pathlib.Path]:
    """app/ai 의 모든 파이썬 파일. 하위 폴더도 든다."""
    return sorted(AI_DIR.rglob('*.py'))


def test_there_are_files_to_check():
    # 폴더를 잘못 가리키면 아무것도 안 보고 통과한다
    assert any(path.name == 'routing.py' for path in ai_files())


@pytest.mark.parametrize('path', ai_files(), ids=lambda path: str(path.relative_to(AI_DIR)))
def test_app_ai_imports_nothing_outside_itself(path: pathlib.Path):
    assert crossings(path) == []


# --- 판별 함수 ---


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        ('import app.ai.provider', []),
        ('from app.ai.catalog_contract import Provider', []),
        ('from app.ai import routing', []),
        ('import httpx\nfrom decimal import Decimal', []),
        ('from app.catalog.models import Grade', ['app.catalog.models']),
        ('import app.core.database', ['app.core.database']),
        ('import app', ['app']),
        ('from app import main', ['app']),
        # 이름이 app.ai 로 시작해도 다른 패키지면 넘는다
        ('from app.ai_log.models import AiInvocation', ['app.ai_log.models']),
        # TYPE_CHECKING 안의 것도 본다
        ('from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from app.rounds import cast', ['app.rounds']),
        # 상대 import 는 app/ai 안이면 된다
        ('from . import provider', []),
        ('from .provider import Reasoning', []),
        # app/ai 밖으로 나가는 상대 import 는 넘는다
        ('from .. import catalog', ['app']),
        ('from ..catalog import models', ['app.catalog']),
    ],
)
def test_crossings_are_found(source: str, expected: list[str]):
    found = [module for module in imported_modules(source, AI_PACKAGE) if crosses(module)]

    assert found == expected
