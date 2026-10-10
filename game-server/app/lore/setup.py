# game-server/app/lore/setup.py

"""
설정을 보고 어느 임베더를 쓸지 고른다. 앱을 만들 때 한 번 부른다(app/main.py).

고르는 규칙만 따로 테스트할 수 있게 앱을 만드는 함수에서 떼어 둔다(서술자의 app/rounds/narrator_setup.py 와 같다).
"""

import httpx

from app.ai.embedder import Embedder
from app.ai.fake import FakeEmbedder
from app.ai.openai_embedder import OpenAICompatEmbedder
from app.core.config import Settings


def build_embedder(settings: Settings, client: httpx.AsyncClient) -> Embedder:
    """설정이 llm 이면 임베딩 모델을 부르는 임베더, 아니면 가짜 임베더. 만드는 것만으로는 모델을 부르지 않는다."""
    if settings.embedder != 'llm':
        return FakeEmbedder()
    return OpenAICompatEmbedder(
        client=client,
        base_url=settings.embedding_url(),
        model=settings.embedding_model.strip(),
        timeout=settings.embedding_timeout_seconds,
    )
