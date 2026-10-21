# .github/scripts/test_readme_scope.py

"""
서버마다의 워크플로와 README 의 줄을 보는 검사(readme_scope.py)의 규칙을 보고, 지금의 저장소에도 돌린다.

    사용: python3 -m unittest discover -s .github/scripts -p 'test_*.py'

지금의 저장소를 보는 시험이 함께 있어서, 서버를 더하고 README 를 잊은 PR 은 CI 의 repo-python 에서 실패한다.
"""

import tempfile
import unittest
from pathlib import Path

from readme_scope import REPO_ROOT, check, readme_marks, readme_problems, server_folders

FULL_README = """
[![a-server](https://example/actions/workflows/a-server.yml/badge.svg)](https://example)
| 서버 A | [`a-server/`](a-server/README.md) | 완료 |
| [a-server/README.md](a-server/README.md) | 설명 |
"""


def make_repo(root: Path, servers: list[str], readme: str, workflows: list[str]) -> None:
    """서버 폴더, 워크플로, README 만 있는 작은 저장소."""
    for server in servers:
        (root / server).mkdir()
    (root / 'docs').mkdir()
    (root / '.github' / 'workflows').mkdir(parents=True)
    for workflow in workflows:
        (root / '.github' / 'workflows' / f'{workflow}.yml').write_text('name: x\n', encoding='utf-8')
    (root / 'README.md').write_text(readme, encoding='utf-8')


class RulesTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def test_only_server_folders_count(self):
        make_repo(self.root, ['a-server', 'b-server'], FULL_README, [])
        (self.root / 'shared').mkdir()
        (self.root / 'web-server.md').write_text('', encoding='utf-8')

        self.assertEqual(server_folders(self.root), ['a-server', 'b-server'])

    def test_a_server_with_everything_passes(self):
        make_repo(self.root, ['a-server'], FULL_README, ['a-server'])

        self.assertEqual(check(self.root), [])

    def test_each_missing_mark_is_its_own_problem(self):
        for name, mark in readme_marks('a-server').items():
            with self.subTest(name=name):
                problems = readme_problems(FULL_README.replace(mark, ''), ['a-server'])

                self.assertEqual(len(problems), 1)
                self.assertIn(name, problems[0])

    def test_a_new_server_without_readme_lines_fails(self):
        make_repo(self.root, ['a-server', 'z-server'], FULL_README, ['a-server', 'z-server'])

        problems = check(self.root)

        self.assertEqual(len(problems), 3)
        self.assertTrue(all('z-server' in problem for problem in problems))

    def test_a_server_without_a_workflow_fails(self):
        make_repo(self.root, ['a-server'], FULL_README, [])

        self.assertEqual(check(self.root), ['a-server 의 워크플로(.github/workflows/a-server.yml)가 없다'])

    def test_a_similar_name_does_not_count(self):
        # chat-server 의 줄이 있어도 chat-server-old 의 줄이 있는 것은 아니다
        readme = FULL_README.replace('a-server', 'a-server-old')

        self.assertEqual(len(readme_problems(readme, ['a-server'])), 3)


class RepositoryTests(unittest.TestCase):
    def test_this_repository_lists_every_server(self):
        self.assertEqual(check(REPO_ROOT), [])

    def test_the_servers_are_found(self):
        # 폴더를 잘못 가리키면 아무것도 안 보고 통과한다
        self.assertIn('trpg-server', server_folders(REPO_ROOT))


if __name__ == '__main__':
    unittest.main()
