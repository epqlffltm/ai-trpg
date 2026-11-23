# trpg-server/scripts/references.py

"""
참고 자료의 관리 명령. 서버를 띄우지 않고 돈다. 운영자가 쓴다.

    uv run python -m scripts.references load            # 공용 패키지에 실린 데이터 파일을 모두 DB 에 맞춘다
    uv run python -m scripts.references load <파일>     # 그 데이터 파일 하나만
    uv run python -m scripts.references index           # 벡터가 없는 줄의 벡터를 만든다
    uv run python -m scripts.references index --model bge-m3:567m-fp16

데이터 파일은 공용 패키지(reference_core/data/)에 실린다. chat, story 와 같은 파일이다.
차례는 load 다음 index 다. 둘을 함께 돌리지 않는다(넣기가 지운 줄의 벡터를 색인이 넣으려 하면 실패한다).
둘 다 여러 번 돌려도 된다. 바뀐 것만 고치고, 없는 벡터만 만든다.
trpg-server 폴더에서 -m 으로 돌린다. 설정(.env)의 DB 와 임베딩 주소, 모델을 쓴다.
index 는 EMBEDDER 설정과 상관없이 실제 임베딩 모델을 부른다. 가짜로 만든 벡터는 검색에 쓸 수 없다.
"""

import argparse
import asyncio
from collections.abc import Sequence
from pathlib import Path

import httpx
from ai_core.embedder import Embedder
from reference_core.data import DATA_FILES
from reference_core.indexing import IndexResult
from reference_core.loading import SyncPlan
from reference_core.records import read_document
from server_core.database import NO_LIMITS, create_session_factory
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.database import create_engine
from app.references.indexing import index_references
from app.references.loading import load_document
from scripts.index_lore import make_embedder

# 끝낼 번호. 다 했으면 0, 벡터가 남았으면(임베딩 모델의 실패) 1 이다
DONE = 0
UNFINISHED = 1


def build_parser() -> argparse.ArgumentParser:
    """명령줄의 모양."""
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
    """넣을 데이터 파일들. 주지 않았으면 공용 패키지에 실린 것 모두다."""
    return list(paths) or list(DATA_FILES)


async def load(session_factory: async_sessionmaker[AsyncSession], path: Path) -> tuple[int, list[str]]:
    """데이터 파일 하나를 DB 에 맞춘다. 끝낼 번호와 찍을 줄들."""
    document = read_document(path)
    async with session_factory() as session:
        plan = await load_document(session, document)
    return DONE, [describe_plan(document.source, plan)]


async def load_files(session_factory: async_sessionmaker[AsyncSession], paths: Sequence[Path]) -> tuple[int, list[str]]:
    """데이터 파일들을 차례로 DB 에 맞춘다. 파일마다 한 줄을 찍는다."""
    lines: list[str] = []
    for path in paths:
        _, done = await load(session_factory, path)
        lines.extend(done)
    return DONE, lines


async def index(session_factory: async_sessionmaker[AsyncSession], embedder: Embedder) -> tuple[int, list[str]]:
    """벡터가 없는 줄의 벡터를 만든다. 끝낼 번호와 찍을 줄들."""
    result = await index_references(session_factory, embedder)
    return (UNFINISHED if result.left else DONE), [describe_index(embedder.model, result)]


async def run(args: argparse.Namespace) -> int:
    """설정의 DB 로 명령을 돌리고 결과를 찍는다. 끝낼 번호를 돌려준다."""
    settings = get_settings()
    # 한꺼번에 많이 넣고 고치는 일이다. 서버의 시간 한도를 걸지 않는다(#1260)
    engine = create_engine(settings, limits=NO_LIMITS)
    session_factory = create_session_factory(engine)
    try:
        if args.command == 'load':
            code, lines = await load_files(session_factory, files_to_load(args.paths))
        else:
            async with httpx.AsyncClient() as client:
                code, lines = await index(session_factory, make_embedder(settings, client, args.model))
    finally:
        await engine.dispose()
    for line in lines:
        print(line)
    return code


def main() -> None:
    """명령줄을 읽고 돌린다."""
    raise SystemExit(asyncio.run(run(build_parser().parse_args())))


if __name__ == '__main__':
    main()
