# .github/scripts/readme_scope.py

"""
서버마다 빠지기 쉬운 셋이 있는지 본다. 서버를 더하는 PR 이 잊으면 실패한다
(docs/architecture/services.md 의 "서비스를 더할 때 고칠 곳").

  - 서버는 저장소 루트의 *-server 폴더다
  - 서버마다 CI 의 워크플로(.github/workflows/<서버>.yml)가 있다
  - 루트 README 에 그 서버의 CI 배지, "현재 상태" 표의 줄, "문서" 표의 줄이 있다

    사용: python3 .github/scripts/readme_scope.py

test_readme_scope.py 가 규칙과 지금의 저장소를 함께 본다(CI 의 repo-python). 표준 라이브러리만 쓴다.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_SUFFIX = '-server'


def server_folders(root: Path) -> list[str]:
    """저장소 루트의 서버 폴더 이름들. 이름의 차례로."""
    return sorted(path.name for path in root.iterdir() if path.is_dir() and path.name.endswith(SERVER_SUFFIX))


def readme_marks(server: str) -> dict[str, str]:
    """README 에 있어야 하는 글과 그 이름. 글은 README 의 링크의 모양 그대로다."""
    return {
        'CI 배지': f'actions/workflows/{server}.yml/badge.svg',
        '"현재 상태" 표의 줄': f'[`{server}/`]({server}/README.md)',
        '"문서" 표의 줄': f'[{server}/README.md]({server}/README.md)',
    }


def readme_problems(readme: str, servers: list[str]) -> list[str]:
    """README 에서 빠진 것들. 서버와 무엇이 빠졌는지를 한 줄씩."""
    return [
        f'README.md 에 없다: {server} 의 {name}({mark})'
        for server in servers
        for name, mark in readme_marks(server).items()
        if mark not in readme
    ]


def workflow_problems(root: Path, servers: list[str]) -> list[str]:
    """CI 의 워크플로가 없는 서버들."""
    return [
        f'{server} 의 워크플로(.github/workflows/{server}.yml)가 없다'
        for server in servers
        if not (root / '.github' / 'workflows' / f'{server}.yml').is_file()
    ]


def check(root: Path) -> list[str]:
    """저장소 하나의 문제들. 없으면 빈 목록이다."""
    servers = server_folders(root)
    readme = (root / 'README.md').read_text(encoding='utf-8')
    return workflow_problems(root, servers) + readme_problems(readme, servers)


def main() -> int:
    problems = check(REPO_ROOT)
    for problem in problems:
        print(problem, file=sys.stderr)
    if not problems:
        print('서버마다 워크플로와 README 의 배지, 상태, 문서의 줄이 있다')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
