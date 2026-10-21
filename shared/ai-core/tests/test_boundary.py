# shared/ai-core/tests/test_boundary.py

"""
AI 를 부르는 공용 코드(ai_core)의 경계를 지킨다(docs/architecture/shared-code.md 의 "AI 호출", #498).

  - 서버의 모듈(app.*)을 가져오지 않는다. 모델 목록의 표나 호출 기록의 표는 쓰는 서버의 몫이다
  - 다른 공용 패키지(server_core, conversation_core)를 가져오지 않는다
  - 관측의 코드(opentelemetry)를 가져오지 않는다. 모델을 부르는 클라이언트는 서버가 넘기므로
    그 클라이언트가 span 을 건다. 메트릭은 서버가 기록장과 결제를 부르는 것을 밖에서 감싸 센다

파일을 읽어 import 문만 본다(TYPE_CHECKING 안의 것도). 상대 import 는 그 파일의 패키지에서 풀어 본다.
예외를 두지 않는다. 필요하면 경계를 다시 의논한다(문서의 "주도권").
맨 아래에는 판별 함수 자체의 테스트가 있다.
"""

import ast
from pathlib import Path

import pytest

PACKAGE_DIR = Path(__file__).resolve().parent.parent / 'src' / 'ai_core'
PACKAGE = 'ai_core'
# 가져오면 안 되는 이름의 앞부분
FORBIDDEN = ('app', 'tests', 'server_core', 'conversation_core', 'opentelemetry')


def package_of(path: Path) -> str:
    """파일이 속한 패키지의 이름. ai_core/x.py 도 ai_core/__init__.py 도 ai_core 다."""
    relative = path.relative_to(PACKAGE_DIR.parent).with_suffix('')
    return '.'.join(relative.parts[:-1])


def resolve(node: ast.ImportFrom, package: str) -> str:
    """from 문이 가리키는 모듈의 이름. 상대 import(level 이 1 이상)는 그 파일의 패키지에서 풀어 본다."""
    if node.level == 0:
        return node.module or ''
    base = package.split('.')
    anchor = base[: len(base) - (node.level - 1)] if node.level - 1 <= len(base) else []
    return '.'.join([*anchor, *([node.module] if node.module else [])])


def imported_modules(source: str, package: str) -> list[tuple[str, bool]]:
    """파일이 가져오는 모듈의 이름과 상대 import 였는지. import 문과 from 문을 모두 본다."""
    names = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend((alias.name, False) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append((resolve(node, package), node.level > 0))
    return names


def is_under(name: str, root: str) -> bool:
    return name == root or name.startswith(root + '.')


def crosses(module: str, relative: bool) -> bool:
    """가져오면 안 되는 모듈인가. 상대 import 는 ai_core 밖으로 나가면 안 된다."""
    if relative and not is_under(module, PACKAGE):
        return True
    return any(is_under(module, root) for root in FORBIDDEN)


def found_in(source: str, package: str) -> list[str]:
    """그 글이 넘는 import 들. 없으면 빈 목록이다."""
    return [module for module, relative in imported_modules(source, package) if crosses(module, relative)]


def crossings(path: Path) -> list[str]:
    """그 파일이 넘는 import 들."""
    return found_in(path.read_text(encoding='utf-8'), package_of(path))


def source_files() -> list[Path]:
    return sorted(PACKAGE_DIR.rglob('*.py'))


def test_the_files_are_found():
    # 폴더를 잘못 가리키면 아무것도 안 보고 통과한다
    assert any(path.name == 'routing.py' for path in source_files())


@pytest.mark.parametrize('path', source_files(), ids=lambda path: str(path.relative_to(PACKAGE_DIR)))
def test_imports_no_server_no_other_shared_package_and_no_telemetry(path: Path):
    assert crossings(path) == []


# --- 판별 함수 ---


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        ('import ai_core.provider', []),
        ('from ai_core.catalog_contract import Provider', []),
        ('import httpx\nfrom decimal import Decimal', []),
        ('from app.catalog.models import Grade', ['app.catalog.models']),
        ('import app', ['app']),
        ('from server_core.observability.spans import job_span', ['server_core.observability.spans']),
        ('from opentelemetry import trace', ['opentelemetry']),
        # 이름이 같은 말로 시작해도 다른 패키지면 넘지 않는다
        ('import apprise', []),
        # TYPE_CHECKING 안의 것도 본다
        ('from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from app.rounds import cast', ['app.rounds']),
        # 상대 import 는 ai_core 안이면 된다
        ('from . import provider', []),
        ('from .provider import Reasoning', []),
        # ai_core 밖으로 나가는 상대 import 는 넘는다
        ('from .. import catalog', ['']),
        ('from ..catalog import models', ['catalog']),
    ],
)
def test_crossings_are_found(source: str, expected: list[str]):
    assert found_in(source, PACKAGE) == expected
