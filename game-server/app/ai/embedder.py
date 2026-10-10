# game-server/app/ai/embedder.py

"""
글을 벡터로 바꾸는 것(임베딩 모델)의 모양.

벡터는 글의 뜻을 숫자 목록으로 옮긴 것이다. 뜻이 가까운 글은 벡터도 가깝다.
로어북 항목을 미리 벡터로 바꿔 두고, 라운드의 글과 가까운 항목을 찾는 데 쓴다(app/lore/).

서술하는 모델(app/ai/provider.py)과 모양을 따로 둔다. 하는 일이 다르고, 모델도 다르다.
게임 서버의 다른 코드는 이 모양만 안다. 로컬 Ollama 에서 클라우드 API 로 바꿀 때 구현만 바꿔 끼운다.
실패는 provider 와 같은 ProviderError 다. 다시 시도할지, 무엇을 할지는 부르는 쪽이 정한다.
"""

from typing import ClassVar, Protocol


class Embedder(Protocol):
    """
    임베딩 모델을 부르는 것의 모양. 이 메서드와 두 이름이 있으면 임베더다.

    kind 는 종류(openai_compat, fake), model 은 모델의 이름이다.
    벡터를 저장할 때 모델의 이름을 함께 적는다. 모델이 다르면 벡터의 공간이 달라 서로 견줄 수 없다.
    """

    kind: ClassVar[str]
    model: str

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """글들을 벡터들로 바꾼다. 차례는 받은 글의 차례와 같다. 실패하면 ProviderError."""
        ...
