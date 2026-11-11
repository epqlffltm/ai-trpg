# trpg-server/tests/test_snapshot_parts.py

"""
장면 그림(#983)의 순수한 조각들을 검증한다. DB 를 쓰지 않는다(값의 API 하나만 앱을 띄운다).

보는 것.
  - 가격표 이름: 이 서버의 머리(narration)와 image 뒤에 모델의 이름. 점은 붙임표로 바꾼다
  - 이름표: game:img:<기록의 id>. 서술 값의 이름표와 섞이지 않는다
  - 지시: 지킬 것이 맨 앞이고, 제목, 몇 번째 장면, 일행의 이름, 장면이 차례로 들어간다. 장면은 앞의 몇 글자만 쓴다
  - 값: provider 가 있고 가격 목록이 그 가격표를 팔면 값과 등급을 싣는다. 없거나 팔지 않으면 그릴 수 없다.
    결제 서버 없이 도는 서버면 그릴 수 있고 값이 없다. 예약된 바뀜의 시각이 지났으면 그 값이다
  - 홀드: 크레딧이 모자람, 골드만, 팔지 않음, 결제 서버가 죽음을 각각의 까닭으로 바꾼다
  - provider: asset 서버의 주소가 없으면 켜도 만들지 않는다
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from ai_core.fake import FakeImageProvider
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.billing.client import BillingRejected, BillingUnavailable, HoldOutcome, HoldResult
from server_core.billing.prices import Change, Price, PriceBook, Sale, Tier
from server_core.testing.tokens import SigningKey

from app.core.config import Settings
from app.main import API_PREFIX
from app.snapshots import charging
from app.snapshots.pricing import snapshot_price
from app.snapshots.prompt import RULES, SCENE_CHARS, snapshot_prompt
from app.snapshots.providers import build_image_provider, price_code_of
from app.snapshots.schemas import SnapshotPriceOut
from app.snapshots.service import hold_reference
from tests.test_round_closing import ME, bearer

MODEL = 'gemini-nano-banana-2.1'
CODE = price_code_of(MODEL)
NOW = datetime(2026, 12, 3, 12, tzinfo=UTC)


def book_with(price: Price | None) -> PriceBook:
    return PriceBook(prices={} if price is None else {CODE: price})


def test_the_price_code_carries_this_servers_prefix():
    assert CODE == 'narration.image.gemini-nano-banana-2-1'


def test_the_hold_reference_is_its_own():
    snapshot_id = uuid.UUID(int=7)

    assert hold_reference(snapshot_id) == f'game:img:{snapshot_id}'


def test_the_prompt_puts_the_rules_first_then_the_story_and_the_scene():
    prompt = snapshot_prompt('추격전', 3, ['엘프', '', '영애'], '  사이렌이 울린다.  ')

    assert prompt.startswith(RULES[0])
    assert prompt.index('제목: 추격전') < prompt.index('3번째 장면') < prompt.index('일행: 엘프, 영애')
    assert prompt.endswith('[장면]\n사이렌이 울린다.')


def test_a_long_scene_is_cut():
    prompt = snapshot_prompt('', 1, [], '가' * (SCENE_CHARS + 50))

    assert prompt.endswith('\n' + '가' * SCENE_CHARS)
    assert '제목' not in prompt and '일행' not in prompt


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
    later = soon + timedelta(minutes=1)
    promo = Price(
        code=CODE,
        current=Sale(credits='120', tier=Tier.STANDARD, promo=True),
        next=Change(Sale(credits='160', tier=Tier.PREMIUM), soon),
    )

    assert snapshot_price(book_with(promo), CODE, True, NOW).promo is True
    assert snapshot_price(book_with(promo), CODE, True, later) == SnapshotPriceOut(
        available=True, credits='160', tier=Tier.PREMIUM
    )


@dataclass
class FixedPrices:
    fixed: PriceBook

    async def book(self) -> PriceBook:
        return self.fixed


async def test_the_price_api(client: AsyncClient, app: FastAPI, signing_key: SigningKey):
    app.state.image_provider = FakeImageProvider(model=MODEL)
    app.state.price_list = FixedPrices(book_with(Price(code=CODE, current=Sale(credits='160', tier=Tier.PREMIUM))))

    response = await client.get(f'{API_PREFIX}/snapshots/price', headers=bearer(signing_key, ME))
    unsigned = await client.get(f'{API_PREFIX}/snapshots/price')

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json() == {'available': True, 'credits': '160', 'tier': 'premium', 'promo': False}
    assert unsigned.status_code == status.HTTP_401_UNAUTHORIZED


@dataclass
class AnsweringBilling:
    """정해 둔 답이나 오류로 답하는 결제 서버."""

    result: HoldResult = HoldResult.HELD
    error: Exception | None = None

    async def hold(self, reference: str, user_id: uuid.UUID, price_code: str) -> HoldOutcome:
        if self.error is not None:
            raise self.error
        return HoldOutcome(self.result)


@pytest.mark.parametrize(
    ('billing', 'code'),
    [
        (AnsweringBilling(HoldResult.SHORT), charging.CREDIT_SHORT),
        (AnsweringBilling(HoldResult.GOLD_REQUIRED), charging.GOLD_REQUIRED),
        (AnsweringBilling(error=BillingRejected(400, 'price.not_for_sale')), charging.NOT_FOR_SALE),
        (AnsweringBilling(error=BillingRejected(409)), charging.BILLING_UNAVAILABLE),
        (AnsweringBilling(error=BillingUnavailable('down')), charging.BILLING_UNAVAILABLE),
    ],
)
async def test_a_declined_hold_names_its_reason(billing: AnsweringBilling, code: str):
    with pytest.raises(charging.HoldDeclined) as declined:
        await charging.place_hold(billing, 'game:img:x', ME, CODE)

    assert declined.value.code == code


async def test_a_held_hold_passes():
    await charging.place_hold(AnsweringBilling(), 'game:img:x', ME, CODE)


def test_without_an_asset_server_nothing_is_drawn(settings: Settings):
    on = settings.model_copy(update={'snapshot_provider': 'fake', 'asset_url': 'http://asset.test'})
    off = on.model_copy(update={'asset_url': ''})
    http = httpx.AsyncClient()

    assert isinstance(build_image_provider(on, http), FakeImageProvider)
    assert build_image_provider(off, http) is None
    assert build_image_provider(on.model_copy(update={'snapshot_provider': 'off'}), http) is None
