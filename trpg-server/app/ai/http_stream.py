# trpg-server/app/ai/http_stream.py

"""
모델의 API 에 요청을 보내고 흘러오는 답(SSE)을 받는 HTTP 의 일. 어느 회사의 모양인지는 모른다.

provider 들(app/ai/openai_compat.py, app/ai/anthropic.py)이 함께 쓴다.
본문을 만드는 것과 흘러온 줄을 읽는 것은 provider 가 한다.
여기는 보내고, 실패를 ProviderError 의 이름으로 바꾸고, 시간의 상한을 지키는 것만 한다.

실패의 이름.
  - 연결이 안 됨: unreachable. 받는 도중에 끊김: interrupted. 둘을 나눈다. 서버가 꺼진 것과 한 번 끊긴 것은 다르다.
  - 시간 초과: timeout. 상태 코드: status_코드.
  - 응답의 본문은 오류에 싣지 않는다. 본문에 프롬프트(GM 메모 포함)가 되돌아와 있을 수 있다.
  - 상태 코드로 실패하면 "이만큼 뒤에 다시 하라"는 머리(retry-after-ms, Retry-After)를 읽어 오류에 싣는다(retry_after).
    다시 부를지, 얼마나 기다릴지는 다시 시도하는 쪽(app/rounds/retrying_narrator.py)이 정한다.

시간의 상한.
  httpx 의 timeout 은 "다음 바이트가 올 때까지"의 상한이다. 흘려 받으면 조각이 계속 오는 한 끝없이 길어질 수 있다.
  그래서 호출 전체에 따로 상한(timeout)을 건다. 다시 시도하는 쪽이 "한 번 부르는 데 이만큼"을 믿고 남은 시간을 센다.

키는 Authorization 머리에만 싣는다(bearer_headers). 비밀값(SecretStr)으로 받아 머리를 만들 때만 꺼낸다.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from pydantic import SecretStr

from app.ai.provider import Completion, ProviderError

# 흘러온 줄들을 끝까지 읽어 답을 만드는 것. provider 가 자기 모양에 맞게 넘긴다
StreamReader = Callable[[AsyncIterator[str]], Awaitable[Completion]]


def bearer_headers(api_key: SecretStr | None) -> dict[str, str]:
    """키가 있으면 Authorization 머리. 없으면(서버 곁의 모델) 빈 것."""
    if api_key is None or not api_key.get_secret_value():
        return {}
    return {'Authorization': f'Bearer {api_key.get_secret_value()}'}


def parse_retry_after(value: str, now: datetime) -> float | None:
    """Retry-After 의 값을 초로. 초의 수이거나 HTTP 날짜다. 읽을 수 없으면 None. 지난 때면 0."""
    try:
        return max(float(value), 0.0)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max((when - now).total_seconds(), 0.0)


def retry_after_of(headers: httpx.Headers, now: datetime | None = None) -> float | None:
    """
    응답의 머리에서 다시 하기까지 기다릴 초. 알려 주지 않았으면 None.

    OpenAI 는 밀리초로 주는 retry-after-ms 도 보낸다. 더 잘다라서 먼저 본다.
    """
    milliseconds = headers.get('retry-after-ms')
    if milliseconds:
        try:
            return max(float(milliseconds) / 1000, 0.0)
        except ValueError:
            pass
    value = headers.get('retry-after')
    if not value:
        return None
    return parse_retry_after(value.strip(), now or datetime.now(UTC))


async def lines_of(response: httpx.Response) -> AsyncIterator[str]:
    """받는 중인 응답의 줄들. 받는 도중의 시간 초과와 끊김을 ProviderError 로 바꾼다."""
    try:
        async for line in response.aiter_lines():
            yield line
    except httpx.TimeoutException as exc:
        raise ProviderError('timeout') from exc
    except httpx.HTTPError as exc:
        raise ProviderError('interrupted') from exc


async def post_stream(
    client: httpx.AsyncClient,
    url: str,
    body: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
    read: StreamReader,
) -> Completion:
    """
    요청을 보내고 흘러오는 답을 read 로 끝까지 읽는다.

    답이 오기 시작하기 전의 실패(연결, 시간 초과, 상태 코드)를 여기서 ProviderError 로 바꾼다.
    받는 도중의 실패는 lines_of 가 바꾼다.
    """
    try:
        async with client.stream('POST', url, json=body, headers=headers, timeout=timeout) as response:
            if response.status_code != httpx.codes.OK:
                raise ProviderError(f'status_{response.status_code}', retry_after=retry_after_of(response.headers))
            return await read(lines_of(response))
    except httpx.TimeoutException as exc:
        raise ProviderError('timeout') from exc
    except httpx.HTTPError as exc:
        raise ProviderError('unreachable') from exc


async def stream_completion(
    client: httpx.AsyncClient,
    url: str,
    body: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
    read: StreamReader,
) -> Completion:
    """post_stream 에 호출 전체의 상한을 건다. 조각이 계속 와도 timeout 초가 지나면 끊는다."""
    try:
        async with asyncio.timeout(timeout):
            return await post_stream(client, url, body, headers, timeout, read)
    except TimeoutError as exc:
        raise ProviderError('timeout') from exc
