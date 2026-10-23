# trpg-server/tests/test_price_list.py

"""
결제 서버의 가격 목록을 받아 두는 것(app/billing/price_list.py)을 검증한다.

실제 결제 서버를 부르지 않는다. httpx 의 가짜 전송이 결제 서버인 척 답한다.
서명(GET, 빈 본문), 받아 둔 동안 다시 묻지 않는 것, 버전(ETag)으로 묻고 304 를 받는 것,
받지 못하면 마지막 목록을 쓰는 것, 여럿이 함께 물어도 한 번만 묻는 것을 본다.
"""

import asyncio
import json
from dataclasses import dataclass, field

import httpx
import pytest
from pydantic import SecretStr
from server_core.service_auth.signing import SIGNATURE_HEADER, sign

from app.billing.price_list import (
    PRICES_PATH,
    REFRESH_SECONDS,
    FreePriceList,
    HttpPriceList,
    PriceListUnavailable,
)
from app.billing.prices import FREE_BOOK

SECRET = 's' * 32
NOW = 1_800_000_000
BODY = {'prices': [{'code': 'narration.gpt-6-luna.i0.o0', 'credits': '20', 'tier': 'standard', 'next': None}]}
NEWER = {'prices': [{'code': 'narration.gpt-6-luna.i0.o0', 'credits': '30', 'tier': 'standard', 'next': None}]}


@dataclass
class Clock:
    """다시 물을 때를 재는 시계. 테스트가 시간을 흘린다."""

    seconds: float = 0.0

    def __call__(self) -> float:
        return self.seconds


@dataclass
class FakeBilling:
    """결제 서버인 척 답하는 것. 받은 요청을 쌓아 두고, 정해 둔 답을 차례로 준다."""

    answers: list[httpx.Response | Exception]
    requests: list[httpx.Request] = field(default_factory=list)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        # 답하기 전에 다른 일에 차례를 넘긴다. 함께 묻는 것들이 실제로 겹친다
        await asyncio.sleep(0)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


def ok(body: dict, etag: str = '"v1"') -> httpx.Response:
    return httpx.Response(200, content=json.dumps(body).encode(), headers={'ETag': etag})


def price_list(fake: FakeBilling, clock: Clock) -> HttpPriceList:
    return HttpPriceList(
        client=httpx.AsyncClient(transport=httpx.MockTransport(fake.handle)),
        base_url='http://billing.test/',
        secret=SecretStr(SECRET),
        timeout=5,
        clock=lambda: NOW,
        monotonic=clock,
    )


def credits_of(book) -> str:
    return book.prices['narration.gpt-6-luna.i0.o0'].current.credits


async def test_the_request_is_signed_like_the_holds():
    fake = FakeBilling([ok(BODY)])

    await price_list(fake, Clock()).book()

    (request,) = fake.requests
    assert (request.method, request.url.path) == ('GET', PRICES_PATH)
    assert request.content == b''
    # 결제 서버와 같은 모양의 서명이다(server_core/service_auth/signing.py). 메서드는 GET, 본문은 비어 있다
    assert request.headers[SIGNATURE_HEADER] == sign(SECRET, NOW, 'GET', PRICES_PATH, b'')
    assert 'If-None-Match' not in request.headers


async def test_the_list_is_kept_while_fresh():
    fake, clock = FakeBilling([ok(BODY)]), Clock()
    prices = price_list(fake, clock)

    first = await prices.book()
    clock.seconds = REFRESH_SECONDS - 1
    second = await prices.book()

    # 고르는 화면을 열 때마다 결제 서버를 부르지 않는다
    assert len(fake.requests) == 1
    assert credits_of(first) == credits_of(second) == '20'


async def test_after_a_minute_it_asks_with_the_version_and_keeps_the_list_on_304():
    fake, clock = FakeBilling([ok(BODY), httpx.Response(304)]), Clock()
    prices = price_list(fake, clock)

    await prices.book()
    clock.seconds = REFRESH_SECONDS
    book = await prices.book()

    assert fake.requests[1].headers['If-None-Match'] == '"v1"'
    assert credits_of(book) == '20'
    # 304 를 받은 때부터 다시 1분이다
    clock.seconds = REFRESH_SECONDS * 2 - 1
    await prices.book()
    assert len(fake.requests) == 2


async def test_a_new_list_and_version_replace_the_old():
    fake, clock = FakeBilling([ok(BODY), ok(NEWER, etag='"v2"'), httpx.Response(304)]), Clock()
    prices = price_list(fake, clock)

    await prices.book()
    clock.seconds = REFRESH_SECONDS
    book = await prices.book()
    clock.seconds = REFRESH_SECONDS * 2
    await prices.book()

    assert credits_of(book) == '30'
    assert fake.requests[2].headers['If-None-Match'] == '"v2"'


@pytest.mark.parametrize(
    ('answer', 'reason'),
    [
        (httpx.ConnectError('down'), 'unreachable'),
        (httpx.ReadTimeout('slow'), 'timeout'),
        (httpx.Response(401), 'status_401'),
        (httpx.Response(503), 'status_503'),
        (httpx.Response(200, content=b'{"prices": "nope"}'), 'malformed'),
    ],
)
async def test_without_a_kept_list_a_failure_is_unavailable(answer: httpx.Response | Exception, reason: str):
    with pytest.raises(PriceListUnavailable) as caught:
        await price_list(FakeBilling([answer]), Clock()).book()

    assert caught.value.reason == reason


async def test_with_a_kept_list_a_failure_keeps_the_last_list(caplog):
    fake, clock = FakeBilling([ok(BODY), httpx.Response(503)]), Clock()
    prices = price_list(fake, clock)
    await prices.book()

    clock.seconds = REFRESH_SECONDS
    with caplog.at_level('WARNING', logger='app.billing.price_list'):
        book = await prices.book()
    clock.seconds = REFRESH_SECONDS + 1
    await prices.book()

    # 고를 수 있는 모델이 갑자기 사라지지 않는다. 다음 물을 때까지 다시 두드리지 않는다
    assert credits_of(book) == '20'
    assert len(fake.requests) == 2
    (warning,) = [record for record in caplog.records if record.name == 'app.billing.price_list']
    assert warning.reason == 'status_503'


async def test_many_asking_at_once_ask_the_billing_server_once():
    fake = FakeBilling([ok(BODY)])
    prices = price_list(fake, Clock())

    books = await asyncio.gather(*(prices.book() for _ in range(5)))

    assert len(fake.requests) == 1
    assert {credits_of(book) for book in books} == {'20'}


async def test_without_a_billing_server_the_list_is_free():
    assert await FreePriceList().book() == FREE_BOOK
    assert FREE_BOOK.free and not FREE_BOOK.prices
