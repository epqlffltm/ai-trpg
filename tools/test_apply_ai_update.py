# tools/test_apply_ai_update.py

"""
패치 zip 을 적용하는 도구(apply_ai_update.py)를 임시 저장소에서 본다. 특히 끝 코드다.

    사용: python3 -m unittest discover -s tools -p 'test_apply_ai_update.py'

충돌했는데 끝 코드가 0 이면, 뒤에 이은 git add 와 commit 이 충돌 표시(<<<<<<<)를 그대로 커밋한다.
그래서 충돌은 0 이 아닌 3 이어야 한다.
"""

import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import apply_ai_update
from apply_ai_update import APPLIED, CONFLICTED, PATCH_FILE, PATCH_FORMAT, STOPPED, USAGE, PatchError

# 임시 저장소의 커밋에 쓰는 이름. CI 의 러너에는 git 의 사용자 설정이 없을 수 있다
IDENTITY = {
    'GIT_AUTHOR_NAME': 'test',
    'GIT_AUTHOR_EMAIL': 'test@example.com',
    'GIT_COMMITTER_NAME': 'test',
    'GIT_COMMITTER_EMAIL': 'test@example.com',
}


def run_git(root: Path, *args: str) -> str:
    """임시 저장소에서 git 을 부르고 출력을 돌려준다. 실패하면 예외다."""
    result = subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def commit_file(root: Path, name: str, text: str) -> str:
    """파일 하나를 쓰고 커밋한다. 커밋 ID 를 돌려준다."""
    (root / name).write_text(text, encoding='utf-8')
    run_git(root, 'add', name)
    run_git(root, 'commit', '-q', '-m', f'write {name}')
    return run_git(root, 'rev-parse', 'HEAD')


def make_zip(folder: Path, base: str, files: dict[str, str]) -> Path:
    """그 기준 커밋에서 만든 패치 zip."""
    path = folder / 'patch.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr(PATCH_FILE, json.dumps({'format': PATCH_FORMAT, 'base_commit': base, 'delete_paths': []}))
        for name, text in files.items():
            archive.writestr(name, text)
    return path


class ApplyTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.root = self.folder / 'repo'
        self.root.mkdir()
        environment = mock.patch.dict(os.environ, IDENTITY)
        environment.start()
        self.addCleanup(environment.stop)
        run_git(self.root, 'init', '-q')
        self.base = commit_file(self.root, 'story.txt', 'first\nsecond\n')
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)

    def apply(self, files: dict[str, str]) -> int:
        """패치를 적용하고 끝 코드를 돌려준다. 도구가 찍는 글은 버린다."""
        with mock.patch('builtins.print'):
            return apply_ai_update.main(['apply_ai_update.py', str(make_zip(self.folder, self.base, files))])

    def test_a_clean_patch_is_applied_and_ends_with_zero(self):
        code = self.apply({'story.txt': 'first\nchanged\n'})

        self.assertEqual(code, APPLIED)
        self.assertEqual((self.root / 'story.txt').read_text(encoding='utf-8'), 'first\nchanged\n')
        self.assertEqual(run_git(self.root, 'diff', '--name-only', '--diff-filter=U'), '')

    def test_a_patch_on_a_moved_branch_is_merged_three_way(self):
        commit_file(self.root, 'other.txt', 'someone else\n')

        code = self.apply({'story.txt': 'first\nchanged\n'})

        self.assertEqual(code, APPLIED)
        self.assertEqual((self.root / 'other.txt').read_text(encoding='utf-8'), 'someone else\n')

    def test_a_conflict_does_not_end_with_zero(self):
        # 기준 커밋 뒤에 같은 줄을 다르게 고쳤다
        commit_file(self.root, 'story.txt', 'first\nmerged elsewhere\n')

        code = self.apply({'story.txt': 'first\nchanged\n'})

        self.assertEqual(code, CONFLICTED)
        self.assertEqual(run_git(self.root, 'diff', '--name-only', '--diff-filter=U'), 'story.txt')
        self.assertIn('<<<<<<<', (self.root / 'story.txt').read_text(encoding='utf-8'))

    def test_a_dirty_folder_stops_without_applying(self):
        (self.root / 'story.txt').write_text('not committed\n', encoding='utf-8')

        code = self.apply({'story.txt': 'first\nchanged\n'})

        self.assertEqual(code, STOPPED)
        self.assertEqual((self.root / 'story.txt').read_text(encoding='utf-8'), 'not committed\n')

    def test_a_wrong_call_ends_with_usage(self):
        with mock.patch('builtins.print'):
            self.assertEqual(apply_ai_update.main(['apply_ai_update.py']), USAGE)

    def test_a_failed_cherry_pick_without_conflicts_stops(self):
        failed = subprocess.CompletedProcess(['git'], returncode=1, stdout='', stderr='fatal: bad object')
        no_conflicts = subprocess.CompletedProcess(['git'], returncode=0, stdout='', stderr='')
        with (
            mock.patch.object(apply_ai_update, 'git', side_effect=[failed, no_conflicts]),
            self.assertRaises(PatchError),
        ):
            apply_ai_update.apply_to_branch(self.root, self.base)


if __name__ == '__main__':
    unittest.main()
