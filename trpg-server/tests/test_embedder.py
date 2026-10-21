# trpg-server/tests/test_embedder.py

"""
설정으로 임베더를 고르는 규칙(app/lore/setup.py)을 검증한다.

임베더 자체(OpenAI 모양, 가짜)는 공용 코드의 테스트(shared/ai-core/tests/test_embedder.py)가 본다.
"""

import httpx
from ai_core.fake import FakeEmbedder
from ai_core.openai_embedder import OpenAICompatEmbedder

from app.lore.setup import build_embedder
from tests.conftest import make_test_settings

BASE_URL = 'http://127.0.0.1:11434/v1'
# --- 고르는 규칙 ---


async def test_the_fake_is_chosen_by_default():
    async with httpx.AsyncClient() as client:
        assert isinstance(build_embedder(make_test_settings(), client), FakeEmbedder)


async def test_the_model_is_chosen_for_llm():
    settings = make_test_settings(embedder='llm', embedding_model=' bge-m3 ', llm_base_url=BASE_URL)

    async with httpx.AsyncClient() as client:
        embedder = build_embedder(settings, client)

    assert isinstance(embedder, OpenAICompatEmbedder)
    assert (embedder.base_url, embedder.model, embedder.timeout) == (BASE_URL, 'bge-m3', 30.0)


async def test_the_set_length_reaches_the_embedder():
    settings = make_test_settings(embedder='llm', embedding_dimensions=1024)

    async with httpx.AsyncClient() as client:
        embedder = build_embedder(settings, client)

    assert embedder.dimensions == 1024
