# .github/scripts/test_copy_scope.py

"""
복사해 둔 코드를 보는 검사(copy_scope.py)의 규칙을 보고, 지금의 저장소에도 돌린다.

    사용: python3 -m unittest discover -s .github/scripts -p 'test_*.py'

지금의 저장소를 보는 시험이 함께 있어서, 서버에 공용 코드나 다른 서버의 코드를 복사해 넣은 PR 은
서버만 고쳤어도 CI 의 repo-python 에서 실패한다.
"""

import tempfile
import textwrap
import unittest
from pathlib import Path

from copy_scope import KNOWN_FILE, MOVED, REPO_ROOT, check, copy_groups, pruned, read_known, write_known

# 문장이 다섯 개인 함수. 견줄 만큼 길다
LONG = '''
def settle(amount, rate):
    """값을 정한다."""
    total = amount * rate
    if total < 0:
        total = 0
    rounded = round(total)
    return rounded
'''

# 문장이 둘인 함수. 짧아서 견주지 않는다
SHORT = """
def double(value):
    result = value * 2
    return result
"""


def write(root: Path, relative: str, source: str) -> None:
    """작은 저장소에 파일 하나를 쓴다."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source), encoding='utf-8')


class RulesTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.known = self.root / 'known.txt'

    def known_lines(self, *lines: str) -> None:
        self.known.write_text('# 설명\n' + ''.join(f'{line}\n' for line in lines), encoding='utf-8')

    def test_the_same_function_in_two_servers_is_a_new_copy(self):
        write(self.root, 'chat-server/app/billing.py', LONG)
        write(self.root, 'story-server/app/billing.py', LONG)

        problems = check(self.root, self.known)

        self.assertEqual(len(problems), 1)
        self.assertIn('새 복제다', problems[0])
        self.assertIn('chat-server/app/billing.py::settle story-server/app/billing.py::settle', problems[0])

    def test_a_copy_of_shared_code_in_a_server_is_found(self):
        write(self.root, 'shared/server-core/src/server_core/billing.py', LONG)
        write(self.root, 'trpg-server/app/billing/setup.py', LONG)

        self.assertEqual(len(check(self.root, self.known)), 1)

    def test_a_renamed_copy_with_another_docstring_is_still_a_copy(self):
        write(self.root, 'chat-server/app/billing.py', LONG)
        renamed = LONG.replace('def settle', 'def charge').replace('값을 정한다.', '다른 설명.')
        write(self.root, 'story-server/app/money.py', renamed)

        self.assertEqual(
            copy_groups(self.root),
            [
                frozenset({'chat-server/app/billing.py::settle', 'story-server/app/money.py::charge'}),
            ],
        )

    def test_a_changed_body_is_not_a_copy(self):
        write(self.root, 'chat-server/app/billing.py', LONG)
        write(self.root, 'story-server/app/billing.py', LONG.replace('total = 0', 'total = 1'))

        self.assertEqual(copy_groups(self.root), [])

    def test_short_definitions_are_not_compared(self):
        write(self.root, 'chat-server/app/a.py', SHORT)
        write(self.root, 'story-server/app/a.py', SHORT)

        self.assertEqual(copy_groups(self.root), [])

    def test_copies_inside_one_place_are_not_compared(self):
        write(self.root, 'chat-server/app/a.py', LONG)
        write(self.root, 'chat-server/app/b.py', LONG)

        self.assertEqual(copy_groups(self.root), [])

    def test_files_outside_app_and_src_are_not_compared(self):
        write(self.root, 'chat-server/tests/test_a.py', LONG)
        write(self.root, 'story-server/scripts/a.py', LONG)
        write(self.root, 'shared/server-core/tests/test_a.py', LONG)

        self.assertEqual(copy_groups(self.root), [])

    def test_a_known_copy_passes(self):
        write(self.root, 'chat-server/app/billing.py', LONG)
        write(self.root, 'story-server/app/billing.py', LONG)
        self.known_lines('chat-server/app/billing.py::settle story-server/app/billing.py::settle  # 설명')

        self.assertEqual(check(self.root, self.known), [])

    def test_a_third_place_added_to_a_known_copy_fails(self):
        write(self.root, 'chat-server/app/billing.py', LONG)
        write(self.root, 'story-server/app/billing.py', LONG)
        write(self.root, 'trpg-server/app/billing.py', LONG)
        self.known_lines('chat-server/app/billing.py::settle story-server/app/billing.py::settle')

        problems = check(self.root, self.known)

        self.assertEqual(len(problems), 2)
        self.assertIn('새 복제다', problems[0])
        self.assertIn('목록의 줄이 지금과 다르다', problems[1])

    def test_a_known_copy_that_is_gone_must_leave_the_list(self):
        write(self.root, 'chat-server/app/billing.py', LONG)
        self.known_lines('chat-server/app/billing.py::settle story-server/app/billing.py::settle')

        problems = check(self.root, self.known)

        self.assertEqual(len(problems), 1)
        self.assertIn('목록의 줄이 지금과 다르다', problems[0])

    def test_prune_shrinks_the_list_and_never_adds(self):
        for server in ('chat-server', 'story-server', 'trpg-server'):
            write(self.root, f'{server}/app/billing.py', LONG)
        write(self.root, 'chat-server/app/other.py', LONG.replace('total = 0', 'total = 2'))
        write(self.root, 'story-server/app/other.py', LONG.replace('total = 0', 'total = 2'))
        servers = ('chat-server', 'story-server', 'trpg-server')
        three = ' '.join(f'{server}/app/billing.py::settle' for server in servers)
        self.known_lines(three, 'asset-server/app/gone.py::f board-server/app/gone.py::f')
        # trpg 의 것을 공용 코드로 옮겼다. chat 과 story 의 것은 남았다
        (self.root / 'trpg-server/app/billing.py').unlink()

        write_known(self.known, pruned(copy_groups(self.root), read_known(self.known)))

        self.assertEqual(
            read_known(self.known),
            [
                frozenset({'chat-server/app/billing.py::settle', 'story-server/app/billing.py::settle'}),
            ],
        )
        self.assertTrue(self.known.read_text(encoding='utf-8').startswith('# 설명\n'))
        # 목록에 없던 other.py 의 복제는 더하지 않았으므로 여전히 실패한다
        self.assertEqual(len(check(self.root, self.known)), 1)

    def test_a_moved_file_that_comes_back_fails(self):
        write(self.root, MOVED[0], 'X = 1\n')

        self.assertEqual(check(self.root, self.known), [f'공용 코드로 옮긴 파일이 다시 생겼다: {MOVED[0]}'])


class RepositoryTests(unittest.TestCase):
    def test_this_repository_has_no_new_copies(self):
        self.assertEqual(check(REPO_ROOT), [])

    def test_the_files_are_found(self):
        # 경로가 틀려 아무것도 보지 않고 통과하는 일을 막는다
        self.assertGreater(len(copy_groups(REPO_ROOT)), 50)
        self.assertTrue(KNOWN_FILE.is_file())


if __name__ == '__main__':
    unittest.main()
