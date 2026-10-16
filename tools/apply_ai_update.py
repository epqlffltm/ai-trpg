# tools/apply_ai_update.py

"""
AI 가 만든 패치 zip(ai-zip-patch-v1)을 지금 브랜치에 3-way 로 적용한다. 표준 라이브러리만 쓴다.

zip 의 모양:
  - 바꾼 파일만, 저장소 루트에서의 경로 그대로
  - 루트의 .ai-patch.json: {"format": "ai-zip-patch-v1", "base_commit": "<전체 커밋 ID>", "delete_paths": [...]}

하는 일:
  1. 작업 폴더가 깨끗한지 본다. 바뀐 파일이 있으면 아무것도 하지 않고 멈춘다.
  2. base_commit 을 별도 작업 폴더(git worktree)로 꺼내 zip 의 파일을 덮고 지운 파일을 지워 패치 커밋을 하나 만든다.
     이 커밋은 refs/ai-patch/last 에 남는다. 원래 작업 폴더는 건드리지 않는다.
  3. 지금 브랜치에 그 커밋을 cherry-pick --no-commit 한다. base_commit 과 지금 사이에 다른 PR 이 같은 파일을
     고쳤어도 3-way 로 합쳐진다. 통째로 덮어쓰지 않는다.
  4. 커밋과 푸시는 하지 않는다. 바뀐 파일과 충돌한 파일을 보여 주고 끝난다.

충돌하면 충돌한 파일에 표시(<<<<<<<)가 남는다. 되돌리려면: git cherry-pick --abort

쓰는 법(저장소 안 어디서든):
  python tools/apply_ai_update.py <zip 경로>
"""

import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

PATCH_FILE = '.ai-patch.json'
PATCH_FORMAT = 'ai-zip-patch-v1'
LAST_REF = 'refs/ai-patch/last'


class PatchError(Exception):
    """적용하지 않고 멈춰야 하는 까닭."""


def git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    """git 을 부른다. 출력은 글자로 받는다."""
    result = subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, encoding='utf-8')
    if check and result.returncode != 0:
        raise PatchError(f'git {" ".join(args)} 실패:\n{result.stderr.strip()}')
    return result


def repo_root(start: Path) -> Path:
    """저장소의 루트."""
    return Path(git('rev-parse', '--show-toplevel', cwd=start).stdout.strip())


def require_clean(root: Path) -> None:
    """
    작업 폴더에 커밋하지 않은 변경이 있으면 멈춘다. 남의 변경을 섞지 않는다.

    추적하지 않는 파일(이 적용기 자신, 받은 zip 등)은 보지 않는다.
    """
    if git('status', '--porcelain', '--untracked-files=no', cwd=root).stdout.strip():
        raise PatchError('작업 폴더에 커밋하지 않은 변경이 있다. 커밋하거나 치운 뒤에 다시 하라(git status).')


def read_manifest(archive: zipfile.ZipFile) -> dict:
    """zip 의 .ai-patch.json 을 읽고 모양을 본다."""
    if PATCH_FILE not in archive.namelist():
        raise PatchError(f'zip 에 {PATCH_FILE} 가 없다.')
    manifest = json.loads(archive.read(PATCH_FILE).decode('utf-8'))
    if manifest.get('format') != PATCH_FORMAT:
        raise PatchError(f'모르는 형식이다: {manifest.get("format")}')
    if not manifest.get('base_commit'):
        raise PatchError('base_commit 이 비어 있다.')
    return manifest


def safe_path(name: str) -> PurePosixPath:
    """zip 안의 경로가 저장소 밖을 가리키지 않는지 본다."""
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts:
        raise PatchError(f'저장소 밖을 가리키는 경로다: {name}')
    return path


def ensure_commit(root: Path, commit: str) -> None:
    """base_commit 이 없으면 원격에서 받아 온다."""
    if git('cat-file', '-e', f'{commit}^{{commit}}', cwd=root, check=False).returncode == 0:
        return
    git('fetch', 'origin', cwd=root)
    if git('cat-file', '-e', f'{commit}^{{commit}}', cwd=root, check=False).returncode != 0:
        raise PatchError(f'base_commit 을 찾을 수 없다: {commit}')


def write_files(archive: zipfile.ZipFile, target: Path) -> list[str]:
    """zip 의 파일들을 그 경로 그대로 쓴다. 쓴 경로들을 돌려준다."""
    written = []
    for name in archive.namelist():
        if name == PATCH_FILE or name.endswith('/'):
            continue
        path = target / safe_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(archive.read(name))
        written.append(name)
    return written


def delete_files(paths: list[str], target: Path) -> None:
    """지울 파일들을 지운다. 이미 없으면 넘어간다."""
    for name in paths:
        path = target / safe_path(name)
        if path.exists():
            path.unlink()


def make_patch_commit(root: Path, archive: zipfile.ZipFile, manifest: dict) -> str:
    """base_commit 을 별도 작업 폴더로 꺼내 패치를 커밋하고 그 커밋 ID 를 돌려준다. 작업 폴더는 지운다."""
    workdir = Path(tempfile.mkdtemp(prefix='ai-patch-'))
    git('worktree', 'add', '--detach', str(workdir), manifest['base_commit'], cwd=root)
    try:
        write_files(archive, workdir)
        delete_files(manifest.get('delete_paths', []), workdir)
        git('add', '-A', cwd=workdir)
        if not git('status', '--porcelain', cwd=workdir).stdout.strip():
            raise PatchError('base_commit 과 다른 것이 없다. 이미 들어간 패치일 수 있다.')
        git('commit', '-q', '-m', 'ai patch', cwd=workdir)
        commit = git('rev-parse', 'HEAD', cwd=workdir).stdout.strip()
        git('update-ref', LAST_REF, commit, cwd=root)
        return commit
    finally:
        git('worktree', 'remove', '--force', str(workdir), cwd=root, check=False)
        shutil.rmtree(workdir, ignore_errors=True)


def apply_to_branch(root: Path, commit: str) -> bool:
    """지금 브랜치에 패치 커밋을 3-way 로 적용한다(커밋하지 않는다). 충돌 없이 됐으면 True."""
    result = git('cherry-pick', '--no-commit', commit, cwd=root, check=False)
    return result.returncode == 0


def report(root: Path, clean: bool) -> None:
    """바뀐 파일과 충돌한 파일을 보여 준다."""
    print(git('status', '--short', cwd=root).stdout.rstrip())
    if clean:
        print('\n적용했다. 충돌 없음. 검사한 뒤 직접 커밋하라.')
        return
    conflicted = git('diff', '--name-only', '--diff-filter=U', cwd=root).stdout.split()
    print('\n충돌한 파일:')
    for name in conflicted:
        print(f'  {name}')
    print('\n충돌한 곳을 고친 뒤 git add 하라. 되돌리려면: git cherry-pick --abort')
    print(f'패치만 보려면: git show {LAST_REF}')


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print('쓰는 법: python tools/apply_ai_update.py <zip 경로>')
        return 2
    zip_path = Path(argv[1]).expanduser().resolve()
    try:
        if not zip_path.is_file():
            raise PatchError(f'zip 이 없다: {zip_path}')
        root = repo_root(Path.cwd())
        require_clean(root)
        with zipfile.ZipFile(zip_path) as archive:
            manifest = read_manifest(archive)
            ensure_commit(root, manifest['base_commit'])
            commit = make_patch_commit(root, archive, manifest)
        report(root, apply_to_branch(root, commit))
    except PatchError as error:
        print(f'멈춤: {error}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
