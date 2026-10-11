# game-server/app/ai/openai_embedder.py

"""
OpenAI 와 같은 모양의 임베딩 주소(/embeddings)를 부르는 임베더. app/ai/embedder.py 의 모양을 따른다.

Ollama, LM Studio, vLLM, 그리고 같은 모양을 받는 클라우드 API 를 이 하나로 부른다.
서술의 provider(app/ai/openai_compat.py)와 같은 httpx 클라이언트를 쓴다. SDK 를 쓰지 않는다.

글 여러 개를 한 번에 보낸다(input 에 목록). 답의 data 는 index 로 차례를 맞춘다. 서버가 차례를 섞어 보내도 된다.
실패는 모두 ProviderError 다. 응답의 본문은 오류에 싣지 않는다.
보낸 글(로어북 항목, AI 만 보는 글)이 되돌아와 있을 수 있다.

받은 답은 믿지 않고 검사한다(read_vectors). 벡터는 저장되어 오래 남고, 어느 글의 벡터인지는 차례로만 안다.
  - index 는 0 부터 보낸 글의 수 - 1 까지가 한 번씩이어야 한다. 겹치거나 빠지면 글과 벡터의 짝이 어긋난다.
    개수만 맞는다고 받으면 남의 벡터가 붙은 채로 저장된다.
  - 숫자는 모두 유한해야 한다(NaN, Infinity 가 아님). 모두 0 인 벡터도 받지 않는다. 코사인 거리를 잴 수 없다.
  - 길이(차원)는 벡터마다 같아야 하고, 설정에 차원을 적었으면(EMBEDDING_DIMENSIONS) 그것과 같아야 한다.
    벡터의 칸(vector)은 차원을 정해 두지 않아서, 차원이 다른 벡터도 저장은 된다. 거리를 잴 때에야 DB 가 오류를 낸다.
틀린 답은 고쳐서 쓰지 않는다. ProviderError('malformed') 로 버리고, 부른 쪽이 임베딩 모델의 실패로 다룬다.
"""

import asyncio
import math
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


def is_index(value: Any) -> bool:
    """차례를 가리키는 정수인가. True/False 는 정수로 치지 않는다(파이썬에서는 True == 1 이다)."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_finite_number(value: Any) -> bool:
    """
    벡터에 넣을 수 있는 숫자인가. 유한한 정수나 실수다. True/False 는 숫자로 치지 않는다.

    NaN 과 Infinity 는 JSON 에 없는 값이지만 파이썬은 읽어 준다. 실수로 바꿀 수 없을 만큼 큰 정수도 받지 않는다.
    """
    if not isinstance(value, int | float) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def is_vector(value: Any) -> bool:
    """
    유한한 숫자들의 목록인가. 비어 있거나 모두 0 이면 벡터가 아니다.

    모두 0 인 벡터는 방향이 없어 코사인 거리를 잴 수 없다. 저장되면 그 글은 뜻으로 찾아지지 않는다.
    """
    return (
        isinstance(value, list)
        and len(value) > 0
        and all(is_finite_number(number) for number in value)
        and any(number != 0 for number in value)
    )


def in_the_order_sent(items: Any, count: int) -> list[Any]:
    """
    답의 항목들을 보낸 글의 차례대로 놓는다. 서버가 차례를 섞어 보냈어도 index 로 맞춘다.

    index 가 0 부터 count - 1 까지를 한 번씩 가리키지 않으면 ProviderError('malformed').
    개수가 다르거나, 겹치거나, 빠졌거나, 범위 밖이거나, 정수가 아닌 경우다. 어느 글의 벡터인지 알 수 없다.
    """
    try:
        indices = [item['index'] for item in items]
    except (KeyError, TypeError) as exc:
        raise ProviderError('malformed') from exc
    if not all(is_index(index) for index in indices) or sorted(indices) != list(range(count)):
        raise ProviderError('malformed')
    return sorted(items, key=lambda item: item['index'])


def read_vectors(data: Any, count: int, dimensions: int | None = None) -> list[list[float]]:
    """
    받은 JSON 에서 벡터들을 꺼내 보낸 차례대로 돌려준다. 모양이 다르면 ProviderError('malformed').

    count 는 보낸 글의 수다. 받지 않는 것: 차례(index)가 보낸 글과 하나씩 맞지 않는 답, 벡터가 아닌 것(is_vector),
    벡터마다 길이가 다른 답, dimensions 를 줬는데 길이가 그것과 다른 답.
    """
    try:
        items = in_the_order_sent(data['data'], count)
        vectors = [item['embedding'] for item in items]
    except (KeyError, TypeError) as exc:
        raise ProviderError('malformed') from exc
    if not all(is_vector(vector) for vector in vectors):
        raise ProviderError('malformed')
    lengths = {len(vector) for vector in vectors}
    if len(lengths) > 1 or (dimensions is not None and lengths != {dimensions}):
        raise ProviderError('malformed')
    return [[float(number) for number in vector] for vector in vectors]


@dataclass(frozen=True)
class OpenAICompatEmbedder:
    """
    OpenAI 와 같은 모양의 주소를 부르는 임베더.

    client 는 앱이 들고 있는 httpx 클라이언트다. 닫는 것은 앱이 한다.
    base_url 은 /embeddings 앞까지다(Ollama 면 http://127.0.0.1:11434/v1).
    dimensions 는 벡터의 길이다. 적으면 길이가 다른 답을 받지 않는다. 적지 않으면(None) 길이를 보지 않는다.
    """

    kind: ClassVar[str] = 'openai_compat'

    client: httpx.AsyncClient
    base_url: str
    model: str
    timeout: float = 30.0
    dimensions: int | None = None

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
        return read_vectors(data, len(texts), self.dimensions)
