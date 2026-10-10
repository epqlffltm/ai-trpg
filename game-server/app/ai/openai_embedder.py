# game-server/app/ai/openai_embedder.py

"""
OpenAI 와 같은 모양의 임베딩 주소(/embeddings)를 부르는 임베더. app/ai/embedder.py 의 모양을 따른다.

Ollama, LM Studio, vLLM, 그리고 같은 모양을 받는 클라우드 API 를 이 하나로 부른다.
서술의 provider(app/ai/openai_compat.py)와 같은 httpx 클라이언트를 쓴다. SDK 를 쓰지 않는다.

글 여러 개를 한 번에 보낸다(input 에 목록). 답의 data 는 index 로 차례를 맞춘다. 서버가 차례를 섞어 보내도 된다.
실패는 모두 ProviderError 다. 응답의 본문은 오류에 싣지 않는다.
보낸 글(로어북 항목, AI 만 보는 글)이 되돌아와 있을 수 있다.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, ClassVar

import httpx

from app.ai.provider import ProviderError


def embeddings_url(base_url: str) -> str:
    """임베딩을 부르는 주소. 설정한 주소의 끝에 / 가 있든 없든 같다."""
    return f'{base_url.rstrip("/")}/embeddings'


def build_body(model: str, texts: list[str]) -> dict[str, Any]:
    """보낼 요청의 본문."""
    return {'model': model, 'input': texts}


async def post_embeddings(client: httpx.AsyncClient, url: str, body: dict[str, Any], timeout: float) -> Any:
    """요청을 보내고 받은 JSON 을 돌려준다. 연결, 시간 초과, 상태 코드, 형식의 실패는 ProviderError 다."""
    try:
        response = await client.post(url, json=body, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise ProviderError('timeout') from exc
    except httpx.HTTPError as exc:
        raise ProviderError('unreachable') from exc
    if response.status_code != httpx.codes.OK:
        raise ProviderError(f'status_{response.status_code}')
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderError('not_json') from exc


def is_vector(value: Any) -> bool:
    """숫자들의 목록인가. 비어 있으면 벡터가 아니다. True/False 는 숫자로 치지 않는다."""
    return (
        isinstance(value, list)
        and len(value) > 0
        and all(isinstance(number, int | float) and not isinstance(number, bool) for number in value)
    )


def read_vectors(data: Any, count: int) -> list[list[float]]:
    """
    받은 JSON 에서 벡터들을 꺼내 보낸 차례대로 돌려준다. 모양이 다르면 ProviderError('malformed').

    보낸 글의 수와 받은 벡터의 수가 다르거나, 벡터마다 길이가 다르면 받지 않는다.
    """
    try:
        items = sorted(data['data'], key=lambda item: item['index'])
        vectors = [item['embedding'] for item in items]
    except (KeyError, TypeError) as exc:
        raise ProviderError('malformed') from exc
    if len(vectors) != count or not all(is_vector(vector) for vector in vectors):
        raise ProviderError('malformed')
    if len({len(vector) for vector in vectors}) > 1:
        raise ProviderError('malformed')
    return [[float(number) for number in vector] for vector in vectors]


@dataclass(frozen=True)
class OpenAICompatEmbedder:
    """
    OpenAI 와 같은 모양의 주소를 부르는 임베더.

    client 는 앱이 들고 있는 httpx 클라이언트다. 닫는 것은 앱이 한다.
    base_url 은 /embeddings 앞까지다(Ollama 면 http://127.0.0.1:11434/v1).
    """

    kind: ClassVar[str] = 'openai_compat'

    client: httpx.AsyncClient
    base_url: str
    model: str
    timeout: float = 30.0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """글들을 벡터들로 바꾼다. 빈 목록이면 부르지 않는다. 호출 전체가 timeout 초를 넘으면 끊는다."""
        if not texts:
            return []
        body = build_body(self.model, texts)
        try:
            async with asyncio.timeout(self.timeout):
                data = await post_embeddings(self.client, embeddings_url(self.base_url), body, self.timeout)
        except TimeoutError as exc:
            raise ProviderError('timeout') from exc
        return read_vectors(data, len(texts))
