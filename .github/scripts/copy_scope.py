# .github/scripts/copy_scope.py

"""
서버와 공용 코드 사이에 복사해 둔 코드가 새로 생기지 않는지 본다
(docs/architecture/shared-code.md 의 "복사해 고쳐 쓰지 않는다").

두 가지를 본다.
  - 옮긴 파일(MOVED): 공용 코드로 옮겨 지운 서버의 파일이 다시 생기면 실패한다
  - 같은 정의: 서버(*-server/app)와 공용 코드(shared/<패키지>/src)의 맨 위 함수와 클래스를 견준다.
    docstring 과 정의의 이름을 뺀 모양(AST)이 같고 문장이 MIN_STATEMENTS 개 이상이면 같은 정의다.
    서로 다른 곳(서버나 공용 패키지) 둘 이상에 같은 정의가 있으면 "복제"다. 이름을 바꿔 붙여도 잡힌다

이미 있던 복제는 copy_scope_known.txt 에 적어 둔다(#1266 이 공용 코드로 옮기며 줄여 간다). 목록은 줄기만 한다.
  - 목록에 없는 복제(새로 복사했거나, 있던 복제에 한 곳을 더 붙였다)는 실패한다
  - 목록의 줄이 지금과 다르면(옮겨서 없어졌거나 줄었다) 실패한다. --prune 이 지금에 맞게 줄인다. 더하지는 않는다

    사용: python3 .github/scripts/copy_scope.py           # 검사
          python3 .github/scripts/copy_scope.py --prune   # 없어지거나 줄어든 복제를 목록에서 뺀다

한계: 클래스 안의 메서드는 따로 견주지 않는다(클래스째 같아야 잡힌다). 한 곳 안의 복제는 보지 않는다.
test_copy_scope.py 가 규칙과 지금의 저장소를 함께 본다(CI 의 repo-python). 표준 라이브러리만 쓴다.
"""

import ast
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
KNOWN_FILE = Path(__file__).resolve().parent / 'copy_scope_known.txt'

# 이만큼 문장이 있어야 견준다. 더 낮추면 짧은 도우미 함수와 예외 클래스까지 잡혀 시끄럽다
MIN_STATEMENTS = 5

# 공용 코드로 옮겨 지운 서버의 파일. 다시 생기면 실패한다. 옮기는 PR 이 여기에 더한다
MOVED = (
    # #1265: 상태 확인 API 를 server_core/health.py, server_core/readiness.py 로 옮겼다
    'asset-server/app/api/health.py',
    'asset-server/app/api/readiness.py',
    'board-server/app/api/health.py',
    'board-server/app/api/readiness.py',
    'chat-server/app/api/health.py',
    'chat-server/app/api/readiness.py',
    'notification-server/app/api/health.py',
    'notification-server/app/api/readiness.py',
    'story-server/app/api/health.py',
    'story-server/app/api/readiness.py',
    'trpg-server/app/api/health.py',
    # #1266: 결제 서버를 부르는 것을 server_core/billing/ 로 옮겼다
    'chat-server/app/billing/client.py',
    'chat-server/app/billing/free_billing.py',
    'chat-server/app/billing/http_billing.py',
    'chat-server/app/billing/metered.py',
    'chat-server/app/billing/metrics.py',
    'chat-server/app/billing/price_list.py',
    'chat-server/app/billing/setup.py',
    'story-server/app/billing/client.py',
    'story-server/app/billing/free_billing.py',
    'story-server/app/billing/http_billing.py',
    'story-server/app/billing/metered.py',
    'story-server/app/billing/metrics.py',
    'story-server/app/billing/price_list.py',
    'story-server/app/billing/setup.py',
    'trpg-server/app/billing/client.py',
    'trpg-server/app/billing/free_billing.py',
    'trpg-server/app/billing/http_billing.py',
    'trpg-server/app/billing/metered.py',
    'trpg-server/app/billing/price_list.py',
    'trpg-server/app/billing/setup.py',
    # #1266: 모델 목록의 거절 까닭, 찾기, 들여오기를 shared/catalog-core 로 옮겼다
    'chat-server/app/catalog/errors.py',
    'chat-server/app/catalog/lookup.py',
    'chat-server/app/catalog/sync.py',
    'story-server/app/catalog/errors.py',
    'story-server/app/catalog/lookup.py',
    'story-server/app/catalog/sync.py',
    'trpg-server/app/catalog/errors.py',
    'trpg-server/app/catalog/lookup.py',
    'trpg-server/app/catalog/sync.py',
    # #1266: 요청 수 제한의 세는 곳과 규칙, 응답을 server_core/limits/ 로 옮겼다
    'chat-server/app/limits/attempts.py',
    'chat-server/app/limits/counters.py',
    'chat-server/app/limits/redis_counter.py',
    'chat-server/app/limits/responses.py',
    'story-server/app/limits/attempts.py',
    'story-server/app/limits/counters.py',
    'story-server/app/limits/redis_counter.py',
    'story-server/app/limits/responses.py',
    'trpg-server/app/limits/attempts.py',
    'trpg-server/app/limits/counters.py',
    'trpg-server/app/limits/redis_counter.py',
    'trpg-server/app/limits/responses.py',
)


def source_files(root: Path) -> list[Path]:
    """견줄 파일들. 서버의 app 과 공용 패키지의 src 아래의 파이썬 파일이다."""
    servers = root.glob('*-server/app/**/*.py')
    shared = root.glob('shared/*/src/**/*.py')
    return sorted(path for path in [*servers, *shared] if '__pycache__' not in path.parts)


def place_of(location: str) -> str:
    """
    정의가 있는 곳(서버 폴더나 공용 패키지).

    'chat-server/app/x.py::f' 는 chat-server, 'shared/ai-core/src/...' 는 shared/ai-core 다.
    """
    parts = location.split('/')
    return '/'.join(parts[:2]) if parts[0] == 'shared' else parts[0]


def without_docstrings(node: ast.AST) -> ast.AST:
    """정의와 그 안의 정의에서 docstring 을 뺀다. 받은 노드를 고친다(파일마다 새로 읽은 트리라 괜찮다)."""
    for inner in ast.walk(node):
        body = getattr(inner, 'body', None)
        if not isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) or not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            inner.body = body[1:] or [ast.Pass()]
    return node


def statement_count(node: ast.AST) -> int:
    """정의 안의 문장 수. 정의 자신은 세지 않는다."""
    return sum(isinstance(inner, ast.stmt) for inner in ast.walk(node)) - 1


def fingerprint(shape: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> str:
    """docstring 을 뺀 정의의 모양. 정의의 이름과 줄 번호도 뺀다. 같으면 같은 글자다. 받은 노드는 고치지 않는다."""
    return ast.dump(shape, include_attributes=False).replace(f"name='{shape.name}'", "name='_'", 1)


def definitions(root: Path, path: Path) -> list[tuple[str, str]]:
    """파일 하나의 맨 위 함수와 클래스 가운데 견줄 만큼 긴 것. (자리, 모양) 의 목록이다."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    relative = path.relative_to(root).as_posix()
    kinds = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    shapes = [without_docstrings(node) for node in tree.body if isinstance(node, kinds)]
    return [
        (f'{relative}::{shape.name}', fingerprint(shape))
        for shape in shapes
        if statement_count(shape) >= MIN_STATEMENTS
    ]


def copy_groups(root: Path) -> list[frozenset[str]]:
    """같은 정의가 서로 다른 곳 둘 이상에 있는 묶음들. 묶음은 정의의 자리들이다."""
    by_shape: dict[str, set[str]] = defaultdict(set)
    for path in source_files(root):
        for location, shape in definitions(root, path):
            by_shape[shape].add(location)
    groups = [frozenset(locations) for locations in by_shape.values()]
    return sorted((group for group in groups if len({place_of(item) for item in group}) > 1), key=sorted)


def read_known(path: Path) -> list[frozenset[str]]:
    """알고 있는 복제의 목록. 한 줄이 한 묶음이고 자리를 빈칸으로 가른다. # 뒤는 설명이다."""
    if not path.is_file():
        return []
    lines = (line.split('#', 1)[0].split() for line in path.read_text(encoding='utf-8').splitlines())
    return [frozenset(items) for items in lines if items]


def format_group(group: frozenset[str]) -> str:
    """묶음 하나를 목록의 한 줄로."""
    return ' '.join(sorted(group))


def moved_problems(root: Path) -> list[str]:
    """옮긴 파일이 다시 생겼으면 그 줄들."""
    return [f'공용 코드로 옮긴 파일이 다시 생겼다: {path}' for path in MOVED if (root / path).exists()]


def new_copy_problems(found: list[frozenset[str]], known: list[frozenset[str]]) -> list[str]:
    """목록의 어느 줄에도 들지 않는 복제들."""
    return [
        f'새 복제다. 공용 코드를 가져다 쓴다: {format_group(group)}'
        for group in found
        if not any(group <= entry for entry in known)
    ]


def stale_entry_problems(found: list[frozenset[str]], known: list[frozenset[str]]) -> list[str]:
    """지금과 다른 목록의 줄들(복제가 없어졌거나 줄었다). 목록이 줄기만 하게 한다."""
    return [
        f'목록의 줄이 지금과 다르다(--prune 으로 줄인다): {format_group(entry)}'
        for entry in known
        if entry not in found
    ]


def check(root: Path, known_file: Path = KNOWN_FILE) -> list[str]:
    """저장소 하나의 문제들. 없으면 빈 목록이다."""
    found = copy_groups(root)
    known = read_known(known_file)
    return moved_problems(root) + new_copy_problems(found, known) + stale_entry_problems(found, known)


def pruned(found: list[frozenset[str]], known: list[frozenset[str]]) -> list[frozenset[str]]:
    """목록을 지금에 맞게 줄인 것. 목록의 줄 안에 드는 복제만 남긴다. 새 복제는 더하지 않는다."""
    return [group for group in found if any(group <= entry for entry in known)]


def write_known(path: Path, groups: list[frozenset[str]]) -> None:
    """목록을 쓴다. 맨 위의 설명은 남긴다."""
    lines = path.read_text(encoding='utf-8').splitlines() if path.is_file() else []
    header = [line for line in lines if line.startswith('#')]
    body = sorted(format_group(group) for group in groups)
    path.write_text('\n'.join([*header, *body]) + '\n', encoding='utf-8')


def main(argv: list[str]) -> int:
    if '--prune' in argv:
        write_known(KNOWN_FILE, pruned(copy_groups(REPO_ROOT), read_known(KNOWN_FILE)))
    problems = check(REPO_ROOT)
    for problem in problems:
        print(problem, file=sys.stderr)
    if not problems:
        print('새 복제가 없고, 알고 있는 복제의 목록이 지금과 같다')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
