# trpg-server/tests/test_query_embedder.py

"""
서술 전의 검색들이 함께 쓰는 임베더(app/lore/query_embedder.py)를 검증한다. DB 도 모델도 부르지 않는다.

  - 같은 글은 한 번만 바꾼다. 동시에 불러도 한 번이다
  - 여러 글을 한꺼번에 바꾸는 것(색인)은 기억하지 않는다
  - 실패한 것은 기억하지 않는다. 한 검색이 취소되어도 함께 기다린 검색은 벡터를 받는다
  - 최근의 것만 기억한다
"""

import asyncio
from dataclasses import dataclass, field

import pytest
from ai_core.fake import FAKE_MODEL, FakeEmbedder, word_vector
from ai_core.provider import ProviderError

from app.lore.query_embedder import QueryEmbedder

TEXT = '드워프가 금빛 리무진을 탄다'


@dataclass
class SlowEmbedder:
    """풀어 줄 때까지 기다렸다가 답하는 임베더. 받은 글의 목록이 쌓인다."""

    model: str = FAKE_MODEL
    calls: list[list[str]] = field(default_factory=list)
    release: asyncio.Event = field(default_factory=asyncio.Event)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        await self.release.wait()
        return [word_vector(text) for text in texts]


async def test_the_same_text_is_embedded_once():
    inner = FakeEmbedder()
    embedder = QueryEmbedder(inner)

    first = await embedder.embed([TEXT])
    second = await embedder.embed([TEXT])

    assert first == second == [word_vector(TEXT)]
    assert inner.calls == [[TEXT]]


async def test_the_same_text_asked_at_once_is_one_call():
    inner = SlowEmbedder()
    embedder = QueryEmbedder(inner)

    waiting = [asyncio.create_task(embedder.embed([TEXT])) for _ in range(3)]
    await asyncio.sleep(0)
    inner.release.set()

    assert [await task for task in waiting] == [[word_vector(TEXT)]] * 3
    assert inner.calls == [[TEXT]]


async def test_many_texts_at_once_are_not_remembered():
    inner = FakeEmbedder()
    embedder = QueryEmbedder(inner)

    await embedder.embed(['하나', '둘'])
    await embedder.embed(['하나', '둘'])

    assert inner.calls == [['하나', '둘'], ['하나', '둘']]


async def test_a_failure_is_not_remembered():
    inner = FakeEmbedder(error='unreachable')
    embedder = QueryEmbedder(inner)

    with pytest.raises(ProviderError):
        await embedder.embed([TEXT])
    inner.error = None

    # 다음 라운드에는 다시 해 본다
    assert await embedder.embed([TEXT]) == [word_vector(TEXT)]
    assert inner.calls == [[TEXT], [TEXT]]


async def test_a_cancelled_search_does_not_cancel_the_others():
    inner = SlowEmbedder()
    embedder = QueryEmbedder(inner)

    given_up = asyncio.create_task(embedder.embed([TEXT]))
    still_waiting = asyncio.create_task(embedder.embed([TEXT]))
    await asyncio.sleep(0)
    given_up.cancel()
    await asyncio.sleep(0)
    inner.release.set()

    # 시간이 다 된 검색 하나 때문에 함께 기다린 검색이 빈손이 되지 않는다
    assert await still_waiting == [word_vector(TEXT)]
    assert given_up.cancelled()
    assert inner.calls == [[TEXT]]


async def test_only_the_latest_texts_are_remembered():
    inner = FakeEmbedder()
    embedder = QueryEmbedder(inner, max_entries=1)

    await embedder.embed(['하나'])
    await embedder.embed(['둘'])
    await embedder.embed(['하나'])

    assert inner.calls == [['하나'], ['둘'], ['하나']]


async def test_a_vector_handed_out_cannot_change_the_remembered_one():
    embedder = QueryEmbedder(FakeEmbedder())

    (vector,) = await embedder.embed([TEXT])
    vector.clear()

    assert await embedder.embed([TEXT]) == [word_vector(TEXT)]


def test_the_model_is_the_inner_one():
    # 벡터를 견주는 쪽이 모델의 이름으로 벡터를 고른다. 감싼 것이 이름을 바꾸면 아무것도 찾지 못한다
    assert QueryEmbedder(FakeEmbedder(model='bge-m3')).model == 'bge-m3'
