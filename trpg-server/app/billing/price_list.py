# trpg-server/app/billing/price_list.py

"""
결제 서버의 가격 목록을 받아 두고 1분쯤마다 버전으로 다시 묻는 것.

결제 서버가 정한 방법(billing-server/README.md 의 "가격 목록")을 따른다.
  - 홀드와 같은 서명으로 GET /api/v1/billing/service/prices 를 부른다(본문은 비어 있다).
  - 응답의 ETag 를 적어 두고, 다시 물을 때 If-None-Match 에 싣는다. 바뀐 것이 없으면 본문 없이 304 다.
  - ETag 는 본문의 해시라 예약한 값이 적용 시각을 지날 때도 바뀐다. 결제 서버가 게임 서버를 부르지 않는다.

받아 두는 까닭: 방장이 모델을 고르는 화면을 열 때마다 결제 서버를 부르지 않는다. 1분쯤 늦어도 괜찮다.
목록은 보여 주는 값이고, 실제로 빠지는 값은 홀드를 걸 때 결제 서버가 정한다.

받지 못하면(결제 서버가 내려갔다, 서명이 틀렸다) 마지막에 받은 목록을 그대로 쓰고 경고를 남긴다.
고를 수 있는 모델이 갑자기 사라지지 않게 하려는 것이다. 다음 물을 때(REFRESH_SECONDS 뒤)까지 다시 두드리지 않는다.
한 번도 받지 못했으면 PriceListUnavailable 이고, 다음 요청에서 다시 묻는다.

결제 서버 없이 도는 서버(BILLING_URL 이 비었다)는 FreePriceList 다. 값이 없는 목록(FREE_BOOK)을 돌려준다.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import httpx
from pydantic import SecretStr, ValidationError
from server_core.observability.context import outgoing_headers
from server_core.service_auth.signing import SIGNATURE_HEADER, sign

from app.billing.prices import FREE_BOOK, PriceBook, parse_price_list

logger = logging.getLogger(__name__)

PRICES_PATH = '/api/v1/billing/service/prices'
# 받아 둔 목록을 다시 묻기까지의 시간(초). 결제 서버의 README 가 권한 값이다
REFRESH_SECONDS = 60.0


class PriceListUnavailable(Exception):
    """가격 목록을 받지 못했고 받아 둔 것도 없다. reason 은 까닭(unreachable, timeout, status_503, malformed)이다."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class PriceList(Protocol):
    """가격 목록을 주는 것의 모양."""

    async def book(self) -> PriceBook:
        """지금의 가격 목록. 받지 못했고 받아 둔 것도 없으면 PriceListUnavailable."""
        ...


@dataclass(frozen=True)
class FreePriceList:
    """결제 서버 없이 도는 서버의 가격 목록. 늘 값이 없는 목록이다."""

    async def book(self) -> PriceBook:
        """값이 없는 목록."""
        return FREE_BOOK


# 결제 서버 없이 도는 서버의 가격 목록. 값을 알리지 않는 곳(테스트, 가격을 몰라도 되는 길)의 기본값이다
FREE_PRICES = FreePriceList()


@dataclass(frozen=True)
class Cached:
    """받아 둔 목록. etag 는 그 목록의 버전, checked_at 은 마지막으로 물어본 때(time.monotonic)다."""

    book: PriceBook
    etag: str | None
    checked_at: float


def request_headers(secret: SecretStr, sent_at: int, etag: str | None) -> dict[str, str]:
    """보낼 머리말. 서명(GET, 빈 본문), 추적, 그리고 받아 둔 버전이 있으면 If-None-Match."""
    headers = {
        SIGNATURE_HEADER: sign(secret.get_secret_value(), sent_at, 'GET', PRICES_PATH, b''),
        **outgoing_headers(),
    }
    if etag is not None:
        headers['If-None-Match'] = etag
    return headers


def read_response(response: httpx.Response) -> PriceBook | None:
    """
    답을 목록으로. 304 면 바뀐 것이 없다는 뜻이라 None.

    200 이 아니거나 본문의 모양이 틀리면 PriceListUnavailable(status_코드, malformed).
    """
    if response.status_code == httpx.codes.NOT_MODIFIED:
        return None
    if response.status_code != httpx.codes.OK:
        raise PriceListUnavailable(f'status_{response.status_code}')
    try:
        return parse_price_list(response.content)
    except ValidationError as error:
        raise PriceListUnavailable('malformed') from error


@dataclass
class HttpPriceList:
    """
    결제 서버의 가격 목록을 받아 두는 것. 앱에 하나만 두고 함께 쓴다(app.state.price_list).

    client 는 앱이 함께 쓰는 httpx 클라이언트다. clock 은 서명에 적는 지금 시각(초), monotonic 은
    다시 물을 때를 재는 시계다. 테스트가 둘을 정해 꽂는다.
    여럿이 함께 물어도 결제 서버에는 한 번만 묻는다(lock).
    """

    client: httpx.AsyncClient
    base_url: str
    secret: SecretStr
    timeout: float
    clock: Callable[[], float] = time.time
    monotonic: Callable[[], float] = time.monotonic
    refresh_seconds: float = REFRESH_SECONDS
    cached: Cached | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def is_fresh(self) -> bool:
        """받아 둔 목록을 다시 묻지 않고 써도 되나."""
        return self.cached is not None and self.monotonic() - self.cached.checked_at < self.refresh_seconds

    async def fetch(self, etag: str | None) -> httpx.Response:
        """결제 서버에 묻는다. 답을 받지 못하면 PriceListUnavailable(timeout, unreachable)."""
        url = self.base_url.rstrip('/') + PRICES_PATH
        headers = request_headers(self.secret, int(self.clock()), etag)
        try:
            return await self.client.get(url, headers=headers, timeout=self.timeout)
        except httpx.TimeoutException as error:
            raise PriceListUnavailable('timeout') from error
        except httpx.HTTPError as error:
            raise PriceListUnavailable('unreachable') from error

    async def refresh(self) -> None:
        """다시 물어 받아 둔 것을 고친다. 304 면 목록은 그대로 두고 물어본 때만 고친다."""
        etag = self.cached.etag if self.cached else None
        response = await self.fetch(etag)
        fresh = read_response(response)
        now = self.monotonic()
        if fresh is None and self.cached is not None:
            self.cached = Cached(self.cached.book, self.cached.etag, now)
            return
        if fresh is None:
            raise PriceListUnavailable('malformed')
        self.cached = Cached(fresh, response.headers.get('ETag'), now)

    def keep_last(self, error: PriceListUnavailable) -> None:
        """받지 못했을 때. 받아 둔 것이 있으면 그것을 쓰고 다음 물을 때까지 기다린다. 없으면 그대로 올린다."""
        if self.cached is None:
            raise error
        logger.warning('결제 서버의 가격 목록을 새로 받지 못했다. 마지막 목록을 쓴다', extra={'reason': error.reason})
        self.cached = Cached(self.cached.book, self.cached.etag, self.monotonic())

    async def book(self) -> PriceBook:
        """지금의 가격 목록. 받아 둔 지 refresh_seconds 가 지났으면 다시 묻는다."""
        if not self.is_fresh():
            async with self.lock:
                if not self.is_fresh():
                    try:
                        await self.refresh()
                    except PriceListUnavailable as error:
                        self.keep_last(error)
        if self.cached is None:
            raise PriceListUnavailable('unreachable')
        return self.cached.book
