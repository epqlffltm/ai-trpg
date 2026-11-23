# shared/reference-core/src/reference_core/commands.py

"""
서버의 관리 명령(scripts/references.py)의 몸통. 서버를 띄우지 않고 운영자가 돌린다.

    load [파일...]   데이터 파일을 DB 에 맞춘다. 주지 않으면 이 패키지에 실린 것 모두(reference_core/data.py)
    index           벡터가 없는 줄의 벡터를 만든다

차례는 load 다음 index 다. 둘을 함께 돌리지 않는다(넣기가 지운 줄의 벡터를 색인이 넣으려 하면 실패한다).
둘 다 여러 번 돌려도 된다. 바뀐 것만 고치고, 없는 벡터만 만든다.
서버는 명령줄을 읽고, 제 설정으로 DB 와 임베더를 만들어 이것을 부른다. 표는 서버의 것을 넘긴다.
"""

import argparse
from collections.abc import Sequence
from pathlib import Path

from ai_core.embedder import Embedder
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reference_core.data import DATA_FILES
from reference_core.indexing import IndexResult, index_references
from reference_core.loading import SyncPlan, load_document
from reference_core.records import read_document
from reference_core.tables import ReferenceTables

# 끝낼 번호. 다 했으면 0, 벡터가 남았으면(임베딩 모델의 실패) 1 이다
DONE = 0
UNFINISHED = 1


def build_parser() -> argparse.ArgumentParser:
    """명령줄의 모양. 서버마다 같다."""
    parser = argparse.ArgumentParser(description='참고 자료를 넣고 벡터를 만든다.')
    commands = parser.add_subparsers(dest='command', required=True)
    load = commands.add_parser('load', help='데이터 파일을 DB 에 맞춘다')
    load.add_argument(
        'paths', type=Path, nargs='*', help='데이터 파일들. 주지 않으면 공용 패키지에 실린 것 모두(DATA_FILES)'
    )
    index = commands.add_parser('index', help='벡터가 없는 줄의 벡터를 만든다')
    index.add_argument('--model', help='임베딩 모델의 이름. 적지 않으면 설정의 EMBEDDING_MODEL')
    return parser


def describe_plan(source: str, plan: SyncPlan) -> str:
    """넣기의 결과를 한 줄로."""
    if not plan.changed:
        return f'{source}: 바뀐 것이 없다'
    return (
        f'{source}: 더함 {len(plan.added)}, 고침 {len(plan.updated)}(벡터를 다시 만들 것 {len(plan.reworded)}), '
        f'지움 {len(plan.removed)}'
    )


def describe_index(model: str, result: IndexResult) -> str:
    """색인의 결과를 한 줄로."""
    line = f'모델 {model}: 벡터 {result.added}개를 새로 만들었다'
    if result.left:
        line += f'. {result.left}개가 남았다(임베딩 모델의 로그를 본다). 다시 돌리면 남은 것부터 만든다'
    return line


def files_to_load(paths: Sequence[Path]) -> list[Path]:
    """넣을 데이터 파일들. 주지 않았으면 이 패키지에 실린 것 모두다."""
    return list(paths) or list(DATA_FILES)


async def load_file(tables: ReferenceTables, session_factory: async_sessionmaker[AsyncSession], path: Path) -> str:
    """데이터 파일 하나를 DB 에 맞춘다. 찍을 한 줄을 돌려준다."""
    document = read_document(path)
    async with session_factory() as session:
        plan = await load_document(tables, session, document)
    return describe_plan(document.source, plan)


async def load_files(
    tables: ReferenceTables, session_factory: async_sessionmaker[AsyncSession], paths: Sequence[Path]
) -> tuple[int, list[str]]:
    """데이터 파일들을 차례로 DB 에 맞춘다. 끝낼 번호와, 파일마다 찍을 한 줄."""
    return DONE, [await load_file(tables, session_factory, path) for path in paths]


async def index(
    tables: ReferenceTables, session_factory: async_sessionmaker[AsyncSession], embedder: Embedder
) -> tuple[int, list[str]]:
    """벡터가 없는 줄의 벡터를 만든다. 끝낼 번호와 찍을 줄들."""
    result = await index_references(tables, session_factory, embedder)
    return (UNFINISHED if result.left else DONE), [describe_index(embedder.model, result)]
