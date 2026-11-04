# shared/ai-core/src/ai_core/image_http.py

"""
그림 provider 들(ai_core/gemini_image.py, ai_core/comfyui.py)이 함께 쓰는 HTTP 의 일. 어느 공급자의 모양인지는 모른다.

글 모델은 흘려 받지만(ai_core/http_stream.py) 그림은 한 번에 받는다. 실패의 이름은 글 모델과 같다.
  - 연결이 안 됨: unreachable. 시간 초과: timeout. 상태 코드: status_코드(Retry-After 를 싣는다). JSON 이 아님: not_json
  - 응답의 본문은 오류에 싣지 않는다. 지시 글이 되돌아와 있을 수 있다
그림의 바이트를 받을 때는 크기의 상한(MAX_IMAGE_BYTES)을 지킨다.
"""

from typing import Any

import httpx

from ai_core.http_stream import retry_after_of
from ai_core.image_provider import MALFORMED, MAX_IMAGE_BYTES
from ai_core.provider import ProviderError


def checked(response: httpx.Response) -> httpx.Response:
    """200 이 아니면 ProviderError(status_코드). 200 이면 그대로."""
    if response.status_code != httpx.codes.OK:
        raise ProviderError(f'status_{response.status_code}', retry_after=retry_after_of(response.headers))
    return response


def json_of(response: httpx.Response) -> Any:
    """응답의 JSON. JSON 이 아니면 ProviderError(not_json)."""
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderError('not_json') from exc


async def send(client: httpx.AsyncClient, method: str, url: str, timeout: float, **kwargs: Any) -> httpx.Response:
    """요청을 보내고 200 인 응답을 받는다. 연결과 시간 초과, 상태 코드의 실패는 ProviderError 다."""
    try:
        response = await client.request(method, url, timeout=timeout, **kwargs)
    except httpx.TimeoutException as exc:
        raise ProviderError('timeout') from exc
    except httpx.HTTPError as exc:
        raise ProviderError('unreachable') from exc
    return checked(response)


async def post_json(
    client: httpx.AsyncClient, url: str, body: dict[str, Any], headers: dict[str, str], timeout: float
) -> Any:
    """JSON 을 보내고 JSON 을 받는다."""
    return json_of(await send(client, 'POST', url, timeout, json=body, headers=headers))


async def get_json(client: httpx.AsyncClient, url: str, timeout: float) -> Any:
    """JSON 을 받는다."""
    return json_of(await send(client, 'GET', url, timeout))


def limited(data: bytes) -> bytes:
    """그림의 바이트. 비었거나 상한을 넘으면 ProviderError(malformed)."""
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ProviderError(MALFORMED)
    return data


async def get_bytes(client: httpx.AsyncClient, url: str, params: dict[str, str], timeout: float) -> tuple[bytes, str]:
    """그림의 바이트와 형식(Content-Type, 없으면 image/png)."""
    response = await send(client, 'GET', url, timeout, params=params)
    mime_type = response.headers.get('content-type', 'image/png').split(';')[0].strip() or 'image/png'
    return limited(response.content), mime_type
