# story-server/app/lore/setup.py

"""
설정을 보고 어느 임베더를 쓸지 고른다. 앱을 만들 때 한 번 부른다(app/main.py). chat 과 같다.
"""

import httpx
from ai_core.embedder import Embedder
from ai_core.fake import FakeEmbedder
from ai_core.openai_embedder import OpenAICompatEmbedder

from app.core.config import Settings


def build_embedder(settings: Settings, client: httpx.AsyncClient) -> Embedder | None:
    """
    off 면 None(뜻으로 찾지 않는다), fake 면 가짜(테스트), llm 이면 임베딩 모델을 부르는 임베더.
    만드는 것만으로는 모델을 부르지 않는다.
    """
    if settings.embedder == 'off':
        return None
    if settings.embedder == 'fake':
        return FakeEmbedder()
    return OpenAICompatEmbedder(
        client=client,
        base_url=settings.embedding_base_url.strip(),
        model=settings.embedding_model.strip(),
        timeout=settings.embedding_timeout_seconds,
        dimensions=settings.embedding_dimensions,
    )
