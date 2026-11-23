# trpg-server/scripts/references.py

"""
참고 자료의 관리 명령. 서버를 띄우지 않고 돈다. 운영자가 쓴다.

    uv run python -m scripts.references load            # 공용 패키지에 실린 데이터 파일을 모두 DB 에 맞춘다
    uv run python -m scripts.references load <파일>     # 그 데이터 파일 하나만
    uv run python -m scripts.references index           # 벡터가 없는 줄의 벡터를 만든다
    uv run python -m scripts.references index --model bge-m3:567m-fp16

명령의 몸통은 공용 코드(reference_core/commands.py)에 있다. chat, story 의 같은 명령과 같다.
여기는 이 서버의 설정으로 DB 와 임베더를 만들고 이 서버의 표에 묶는다.
데이터 파일은 공용 패키지(reference_core/data/)에 실린다. chat, story 와 같은 파일이다.
차례는 load 다음 index 다. 둘을 함께 돌리지 않는다(넣기가 지운 줄의 벡터를 색인이 넣으려 하면 실패한다).
둘 다 여러 번 돌려도 된다. 바뀐 것만 고치고, 없는 벡터만 만든다.
trpg-server 폴더에서 -m 으로 돌린다. 설정(.env)의 DB 와 임베딩 주소, 모델을 쓴다.
index 는 EMBEDDER 설정과 상관없이 실제 임베딩 모델을 부른다. 가짜로 만든 벡터는 검색에 쓸 수 없다.
"""

import argparse
import asyncio
from functools import partial

import httpx
from reference_core import commands
from reference_core.commands import build_parser, files_to_load
from server_core.database import NO_LIMITS, create_session_factory

from app.core.config import get_settings
from app.core.database import create_engine
from app.references.models import TABLES
from scripts.index_lore import make_embedder

# 공용 명령을 이 서버의 표에 묶는다
load_files = partial(commands.load_files, TABLES)
index = partial(commands.index, TABLES)


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
