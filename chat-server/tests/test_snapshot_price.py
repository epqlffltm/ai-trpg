# chat-server/tests/test_snapshot_price.py

"""
장면 그림 한 장의 값(#983, GET /api/v1/chat/snapshots/price)을 검증한다. 가격 목록과 그림 모델은 가짜다.

보는 것.
  - 그림 provider 가 있고 가격 목록이 그 가격표를 팔면 값, 등급, 행사가 표시를 싣는다
  - provider 가 없거나, 가격표에 없거나, 판매를 멈췄으면 그릴 수 없다(available 이 거짓)
  - 결제 서버 없이 도는 서버면 그릴 수 있고 값이 없다. 예약된 바뀜의 시각이 지났으면 그 값이다
  - 가격 목록을 받지 못했으면 503 prices_unavailable, 토큰이 없으면 401 이다
"""

from datetime import UTC, datetime, timedelta

from ai_core.fake import FakeImageProvider
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey

from app.billing.prices import Change, Price, PriceBook, Sale, Tier
from app.main import API_PREFIX
from app.snapshots.pricing import snapshot_price
from app.snapshots.providers import price_code_of
from app.snapshots.schemas import SnapshotPriceOut
from tests.prices import StaticPrices
from tests.turns import bearer

MODEL = 'gemini-nano-banana-2.1'
CODE = price_code_of(MODEL)
PRICE_URL = f'{API_PREFIX}/snapshots/price'
NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)


def book_with(price: Price | None) -> PriceBook:
    return PriceBook(prices={} if price is None else {CODE: price})


def test_the_price_comes_from_the_price_list():
    selling = Price(code=CODE, current=Sale(credits='160', tier=Tier.STANDARD))

    assert snapshot_price(book_with(selling), CODE, True, NOW) == SnapshotPriceOut(
        available=True, credits='160', tier=Tier.STANDARD
    )
    assert snapshot_price(book_with(selling), CODE, False, NOW) == SnapshotPriceOut(available=False)
    assert snapshot_price(book_with(None), CODE, True, NOW) == SnapshotPriceOut(available=False)
    assert snapshot_price(PriceBook(free=True), CODE, True, NOW) == SnapshotPriceOut(available=True)


def test_a_scheduled_change_counts_once_its_time_has_come():
    soon = NOW + timedelta(hours=1)
    promo = Price(
        code=CODE,
        current=Sale(credits='120', tier=Tier.STANDARD, promo=True),
        next=Change(Sale(credits='160', tier=Tier.PREMIUM), soon),
    )
    stopping = Price(code=CODE, current=Sale(credits='160', tier=Tier.STANDARD), next=Change(None, soon))
    later = soon + timedelta(minutes=1)

    assert snapshot_price(book_with(promo), CODE, True, NOW).promo is True
    assert snapshot_price(book_with(promo), CODE, True, later) == SnapshotPriceOut(
        available=True, credits='160', tier=Tier.PREMIUM
    )
    assert snapshot_price(book_with(stopping), CODE, True, NOW).available is True
    assert snapshot_price(book_with(stopping), CODE, True, later).available is False


async def test_the_price_api(client: AsyncClient, app: FastAPI, signing_key: SigningKey):
    app.state.image_provider = FakeImageProvider(model=MODEL)
    app.state.price_list = StaticPrices(
        prices={CODE: Price(code=CODE, current=Sale(credits='160', tier=Tier.STANDARD))}
    )
    mine = bearer(signing_key)

    sold = await client.get(PRICE_URL, headers=mine)
    app.state.image_provider = None
    off = await client.get(PRICE_URL, headers=mine)

    assert sold.status_code == status.HTTP_200_OK, sold.text
    assert sold.json() == {'available': True, 'credits': '160', 'tier': 'standard', 'promo': False}
    assert off.json() == {'available': False, 'credits': None, 'tier': None, 'promo': False}


async def test_without_the_price_list_or_a_token(client: AsyncClient, app: FastAPI, signing_key: SigningKey):
    app.state.image_provider = FakeImageProvider(model=MODEL)
    app.state.price_list = StaticPrices(down=True)

    down = await client.get(PRICE_URL, headers=bearer(signing_key))
    anonymous = await client.get(PRICE_URL)

    assert (down.status_code, down.json()['code']) == (503, 'prices_unavailable')
    assert anonymous.status_code == status.HTTP_401_UNAUTHORIZED
