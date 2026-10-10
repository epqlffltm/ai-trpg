# game-server/scripts/index_lore.py

"""
게시한 판들의 로어북 항목을 벡터로 만든다. 서버를 띄우지 않고 돈다.

쓰는 때.
  - 로어북 검색이 생기기 전에 게시한 판들. 그 판들에는 벡터가 없다.
  - 임베딩 모델을 바꾼 뒤. 새 모델의 벡터를 만든다(옛 모델의 것은 그대로 남는다).
  - 게시 직후의 색인이 실패했을 때(임베딩 모델이 꺼져 있었다).
없는 것만 만든다. 여러 번 돌려도 된다.

    uv run python -m scripts.index_lore
    uv run python -m scripts.index_lore --model qwen3-embedding:0.6b

game-server 폴더에서 -m 으로 돌린다. 설정(.env)의 DB 와 임베딩 주소, 모델을 쓴다.
EMBEDDER 설정과 상관없이 실제 임베딩 모델을 부른다. 가짜로 만든 벡터는 검색에 쓸 수 없다.
"""

import argparse
import asyncio

import httpx

from app.ai.openai_embedder import OpenAICompatEmbedder
from app.core.config import Settings, get_settings
from app.core.database import create_engine, create_session_factory
from app.lore import repository
from app.lore.indexing import index_version


def read_arguments() -> argparse.Namespace:
    """명령줄의 값을 읽는다."""
    parser = argparse.ArgumentParser(description='게시한 판들의 로어북 항목을 벡터로 만든다.')
    parser.add_argument('--model', help='임베딩 모델의 이름. 적지 않으면 설정의 EMBEDDING_MODEL')
    return parser.parse_args()


def make_embedder(settings: Settings, client: httpx.AsyncClient, model: str | None) -> OpenAICompatEmbedder:
    """설정의 주소로 임베딩 모델을 부르는 임베더를 만든다."""
    return OpenAICompatEmbedder(
        client=client,
        base_url=settings.embedding_url(),
        model=(model or settings.embedding_model).strip(),
        timeout=settings.embedding_timeout_seconds,
    )


async def run(model: str | None) -> None:
    """판마다 색인을 돌리고 만든 수를 찍는다. 실패한 판은 로그에 이유가 남고, 다음에 다시 돌리면 남은 것부터 만든다."""
    settings = get_settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        async with httpx.AsyncClient() as client:
            embedder = make_embedder(settings, client, model)
            async with session_factory() as session:
                version_ids = await repository.list_version_ids(session)
            total = 0
            for version_id in version_ids:
                added = await index_version(session_factory, embedder, version_id)
                print(f'{version_id}: {added}개', flush=True)
                total += added
            print(f'판 {len(version_ids)}개, 모델 {embedder.model}: 벡터 {total}개를 새로 만들었다')
    finally:
        await engine.dispose()


def main() -> None:
    """명령줄을 읽고 돌린다."""
    asyncio.run(run(read_arguments().model))


if __name__ == '__main__':
    main()
