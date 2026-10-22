# trpg-server/app/lore/query_embedder.py

"""
서술 전의 검색들이 함께 쓰는 임베더. 같은 글은 한 번만 벡터로 바꾼다.

로어북, 지난 일, 참고 자료의 검색은 모두 같은 찾는 글(app/lore/retrieval.py 의 query_text)을 벡터로 바꾼다.
셋이 따로 부르면 라운드마다 같은 글을 세 번 임베딩한다. 이것을 셋에 꽂으면 한 번이다.

  - 글 하나를 바꿀 때만 기억한다. 여러 글을 한꺼번에 바꾸는 색인(app/*/indexing.py)은 이것을 쓰지 않는다
  - 같은 글을 동시에 부르면 하나의 호출을 함께 기다린다. 검색들이 함께 돌기 때문이다
    (app/rounds/closing.py 의 gather_context)
  - 한 검색의 시간이 다 되어 취소되어도 함께 기다리는 다른 검색의 호출은 끊지 않는다
  - 실패한 것은 기억하지 않는다. 다음에 부르면 다시 해 본다
  - 최근의 것 MAX_ENTRIES 개만 기억한다. 같은 모델이면 같은 글의 벡터는 늘 같아서 오래 두어도 틀리지 않는다
"""

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import ClassVar

from ai_core.embedder import Embedder

# 진행 중이거나 끝난 호출. 끝난 것은 벡터를 들고 있다
type Call = asyncio.Task[list[list[float]]]

# 기억하는 글의 수. 벡터 하나가 수천 개의 숫자라(bge-m3 는 1024) 수백 개면 몇 MB 다
MAX_ENTRIES = 256


@dataclass
class QueryEmbedder:
    """
    안의 임베더(inner)를 감싸 글 하나의 벡터를 기억한다. 임베더의 모양(ai_core/embedder.py)을 따른다.

    model 은 안의 임베더의 것이다. 벡터를 견주는 쪽이 모델의 이름으로 벡터를 고르므로 바꾸지 않는다.
    """

    inner: Embedder
    max_entries: int = MAX_ENTRIES
    kind: ClassVar[str] = 'query'
    _calls: OrderedDict[str, Call] = field(default_factory=OrderedDict, init=False, repr=False)

    @property
    def model(self) -> str:
        """안의 임베더의 모델 이름."""
        return self.inner.model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """글들을 벡터로 바꾼다. 글이 하나면 기억한 것을 쓰고, 여럿이면 그대로 안의 임베더에 넘긴다."""
        if len(texts) != 1:
            return await self.inner.embed(texts)
        (vector,) = await asyncio.shield(self.call_for(texts[0]))
        return [list(vector)]

    def call_for(self, text: str) -> Call:
        """그 글을 바꾸는 호출. 기억한 것이 있으면 그것을, 없으면 새로 시작해 기억한다."""
        call = self._calls.get(text)
        if call is not None:
            self._calls.move_to_end(text)
            return call
        call = asyncio.ensure_future(self.inner.embed([text]))
        call.add_done_callback(lambda finished: self.forget_failure(text, finished))
        self._calls[text] = call
        while len(self._calls) > self.max_entries:
            self._calls.popitem(last=False)
        return call

    def forget_failure(self, text: str, call: Call) -> None:
        """실패하거나 취소된 호출은 지운다. 실패를 받아 두어 "받지 않은 예외"로 남지 않게 한다."""
        failed = call.cancelled() or call.exception() is not None
        if failed and self._calls.get(text) is call:
            del self._calls[text]
