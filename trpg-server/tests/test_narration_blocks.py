# trpg-server/tests/test_narration_blocks.py

"""
서술 값을 잡지 못해 막힌 라운드를 알리고 푸는 것을 검증한다(#332).

보는 것.
  - 결제 서버의 답 읽기: 402 의 credit.gold_required 는 골드가 모자람, 400 의 price.* 는 팔지 않는 가격표다.
  - 팔지 않는 모델: 청구가 실패로 적히고, 라운드마다 한 번 모두에게 알린다. 서술은 model_not_for_sale 로 실패한다.
    서술의 실패로 세지 않는다. 방장이 모델을 바꾸면 그 라운드의 청구를 새 가격표로 다시 걸어 서술한다.
  - 골드가 모자람: 크레딧이 모자란 것과 같이 다루되 까닭(gold_required)을 알린다. 골드를 사면 풀린다.
    모델은 팔고 있으니 시작한 뒤에는 바꿀 수 없다(app/tables/narration_models.py).
  - 긴 이름표의 가격표 이름도 청구에 들어간다(64자).
"""

import uuid

import httpx
import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.client import BillingRejected, HoldResult
from app.billing.http_billing import hold_result, require_success
from app.billing.prices import FREE_BOOK, narration_code
from app.billing.routing import utc_now
from app.billing.settling import Readiness, worst
from app.catalog.schemas import ModelCreate
from app.rounds.service import NARRATION_FAILURE_LIMIT
from tests.billing import PRICES, FakeBillingServer
from tests.signing import SigningKey
from tests.test_model_offers import LUNA, NOW, OPUS, FixedPrices, add_enabled, book, on_sale
from tests.test_narration_billing import charges_of, tick
from tests.test_npc_actions import bearer, declare, events_of, table_url
from tests.test_round_time_limit import current, start_with

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
LUNA_CODE = narration_code('gpt-6-luna')
OPUS_CODE = narration_code('claude-opus-5-5')
LAUGH = '크게 웃는다.'


def reply(status_code: int, code: str | None = None) -> httpx.Response:
    body = {'detail': '...', **({'code': code} if code else {})}
    return httpx.Response(status_code, json=body)


# --- 결제 서버의 답 읽기 ---


@pytest.mark.parametrize(
    ('response', 'result'),
    [
        (reply(402, 'credit.gold_required'), HoldResult.GOLD_REQUIRED),
        (reply(402, 'credit.insufficient'), HoldResult.SHORT),
        (reply(402), HoldResult.SHORT),
        (httpx.Response(402, content=b'not json'), HoldResult.SHORT),
    ],
)
def test_a_payment_required_reply_tells_gold_from_credits(response: httpx.Response, result: HoldResult):
    assert hold_result(response).result == result


@pytest.mark.parametrize(
    ('response', 'code', 'unavailable'),
    [
        (reply(400, 'price.not_for_sale'), 'price.not_for_sale', True),
        (reply(400, 'price.unknown'), 'price.unknown', True),
        (reply(400, 'hold.invalid_request'), 'hold.invalid_request', False),
        (reply(409), None, False),
    ],
)
def test_a_rejection_carries_the_name_of_the_error(response: httpx.Response, code: str | None, unavailable: bool):
    with pytest.raises(BillingRejected) as caught:
        require_success(response)

    assert (caught.value.code, caught.value.price_unavailable) == (code, unavailable)


# --- 테이블 ---


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """두 번째로 앉는 사람."""
    return bearer(signing_key, FRIEND)


@pytest.fixture(autouse=True)
async def models(app: FastAPI, session: AsyncSession, clean_tables, monkeypatch: pytest.MonkeyPatch) -> None:
    """켜진 모델 둘(Luna, Opus)과 그 값. 고르는 것은 결제 서버 없이 도는 서버처럼 값 없이 된다."""
    await add_enabled(session, LUNA)
    await add_enabled(session, OPUS)
    app.state.price_list = FixedPrices(FREE_BOOK)
    app.dependency_overrides[utc_now] = lambda: NOW
    monkeypatch.setitem(PRICES, LUNA_CODE, 20)
    monkeypatch.setitem(PRICES, OPUS_CODE, 300)


@pytest.fixture
async def billing(app: FastAPI) -> FakeBillingServer:
    """앱에 꽂은 가짜 결제 서버. 둘 다 1000 크레딧이 있다. 골드는 없다."""
    server = FakeBillingServer(balances={ME: 1000, FRIEND: 1000})
    client = server.make_client()
    app.state.billing = server.billing(client)
    yield server
    await client.aclose()


async def set_model(client: AsyncClient, headers: dict[str, str], table: dict, model: str | None) -> httpx.Response:
    response = await client.put(table_url(table, '/narration-model'), json={'narration_model': model}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response


async def retry(client: AsyncClient, me: dict[str, str], table: dict, narrated) -> None:
    """실패한 서술을 방장이 다시 맡기고 끝날 때까지 기다린다."""
    response = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    assert response.status_code == status.HTTP_202_ACCEPTED, response.text
    await narrated()


# --- 팔지 않는 모델 ---


async def test_a_model_no_longer_sold_is_told_once_per_round(
    client: AsyncClient,
    app: FastAPI,
    me: dict[str, str],
    friend: dict[str, str],
    session: AsyncSession,
    billing: FakeBillingServer,
):
    billing.not_for_sale.add(LUNA_CODE)
    table = await start_with(client, me, friend, narration_model='gpt-6-luna')

    await tick(app)
    mine, theirs = await charges_of(session, table), await charges_of(session, table, FRIEND)
    events = await events_of(client, me, table, 'narration_model_not_for_sale')

    # 내는 사람마다 같은 일이라 알림은 한 번이다. 방장이 모델을 바꾸도록 서술 전에 알린다
    assert [(charge.status, charge.last_error) for charge in mine + theirs] == [
        ('failed', 'price.not_for_sale'),
        ('failed', 'price.not_for_sale'),
    ]
    assert [event['payload'] for event in events] == [{'round': 1, 'narration_model': 'gpt-6-luna'}]


async def test_a_round_whose_model_is_not_sold_fails_and_is_not_counted(
    client: AsyncClient, app: FastAPI, me: dict[str, str], billing: FakeBillingServer, narrated
):
    billing.not_for_sale.add(LUNA_CODE)
    table = await start_with(client, me, narration_model='gpt-6-luna')
    await tick(app)

    await declare(client, me, table, LAUGH)
    await narrated()
    for _ in range(NARRATION_FAILURE_LIMIT):
        await retry(client, me, table, narrated)
    failed = await events_of(client, me, table, 'narration_failed')
    round_ = await current(client, me, table)

    # 모델을 부르지 않았으니 서술의 실패로 세지 않는다. 그만두지 않고 방장이 모델을 바꾸기를 기다린다
    assert {event['payload']['reason'] for event in failed} == {'model_not_for_sale'}
    assert (round_['number'], round_['narration_failures']) == (1, 0)


async def test_changing_the_model_reprices_the_blocked_round(
    client: AsyncClient,
    app: FastAPI,
    me: dict[str, str],
    session: AsyncSession,
    billing: FakeBillingServer,
    narrated,
):
    billing.not_for_sale.add(LUNA_CODE)
    table = await start_with(client, me, narration_model='gpt-6-luna')
    await tick(app)
    await declare(client, me, table, LAUGH)
    await narrated()
    # 결제 서버의 가격 목록에서도 Luna 가 빠졌다. 지금 모델을 쓸 수 없으니 시작한 뒤에도 바꿀 수 있다
    app.state.price_list = FixedPrices(book(on_sale('claude-opus-5-5', '300')))

    # 서술이 실패해 멈춘 라운드다. 그 라운드의 모델도 바뀌고, 청구는 새 가격표로 다시 건다
    await set_model(client, me, table, 'claude-opus-5-5')
    (changed,) = await events_of(client, me, table, 'narration_model_changed')
    (repriced,) = [(charge.status, charge.price_code) for charge in await charges_of(session, table)]
    await tick(app)
    await retry(client, me, table, narrated)
    await tick(app)
    (first, _) = await charges_of(session, table)

    assert changed['payload'] == {
        'narration_model': 'claude-opus-5-5',
        'round': 1,
        'price': {'tier': 'standard', 'credits': '300'},
    }
    assert repriced == ('release_due', OPUS_CODE)
    assert (await current(client, me, table))['number'] == 2
    # 새 이름표, 새 가격표로 걸어 확정했다. 빠진 것은 Opus 의 값뿐이다
    assert (first.status, first.price_code, first.renewals) == ('captured', OPUS_CODE, 1)
    assert billing.balance(ME) == 1000 - 300 - 300


# --- 골드가 모자람 ---


async def test_a_premium_model_without_gold_is_told_with_its_reason(
    client: AsyncClient,
    app: FastAPI,
    me: dict[str, str],
    session: AsyncSession,
    billing: FakeBillingServer,
    narrated,
):
    billing.gold_only.add(OPUS_CODE)
    table = await start_with(client, me, narration_model='claude-opus-5-5')

    await tick(app)
    (charge,) = await charges_of(session, table)
    (short,) = await events_of(client, me, table, 'narration_credits_short')
    await declare(client, me, table, LAUGH)
    await narrated()
    (failed,) = await events_of(client, me, table, 'narration_failed')

    # 실버가 1000 있어도 프리미엄은 골드로만 낸다. 화면이 "골드가 필요하다"를 알린다
    assert (charge.status, charge.last_error) == ('short', 'gold_required')
    assert short['payload'] == {'round': 1, 'user_id': str(ME), 'reason': 'gold_required'}
    assert failed['payload']['reason'] == 'gold_required'
    assert (await current(client, me, table))['narration_failures'] == 0


async def test_a_model_still_sold_cannot_be_changed_for_want_of_gold(
    client: AsyncClient, app: FastAPI, me: dict[str, str], billing: FakeBillingServer, narrated
):
    billing.gold_only.add(OPUS_CODE)
    table = await start_with(client, me, narration_model='claude-opus-5-5')
    await tick(app)
    await declare(client, me, table, LAUGH)
    await narrated()

    response = await client.put(
        table_url(table, '/narration-model'), json={'narration_model': 'gpt-6-luna'}, headers=me
    )

    # Opus 는 아직 판다. 골드가 모자란 것은 한 사람의 일이라 방장이 모두의 모델을 바꾸는 까닭이 되지 않는다.
    # 골드를 사거나, 모자란 사람을 기다리거나 빼는 길로 푼다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'narration_model_locked'
    assert (await current(client, me, table))['narration_model'] == 'claude-opus-5-5'


async def test_buying_gold_also_unblocks_the_round(
    client: AsyncClient, app: FastAPI, me: dict[str, str], billing: FakeBillingServer, narrated
):
    billing.gold_only.add(OPUS_CODE)
    table = await start_with(client, me, narration_model='claude-opus-5-5')
    await tick(app)
    await declare(client, me, table, LAUGH)
    await narrated()

    billing.gold.add(ME)
    await retry(client, me, table, narrated)

    assert (await current(client, me, table))['number'] == 2


# --- 긴 이름표 ---


async def test_a_model_with_the_longest_slug_fits_the_price_code(
    client: AsyncClient,
    app: FastAPI,
    me: dict[str, str],
    session: AsyncSession,
    billing: FakeBillingServer,
    monkeypatch: pytest.MonkeyPatch,
):
    slug = 'a' * 20 + '-' + 'b' * 27
    long = ModelCreate(**{**LUNA.model_dump(), 'slug': slug, 'api_model_id': 'long-model-2026-10-01'})
    await add_enabled(session, long)
    monkeypatch.setitem(PRICES, narration_code(slug), 20)

    table = await start_with(client, me, narration_model=slug)
    await tick(app)
    (charge,) = await charges_of(session, table)

    # 이름표는 48자까지다. 가격표 이름은 64자가 되어 결제 서버의 상한(64자)에 꼭 맞는다
    assert len(slug) == 48
    assert (len(charge.price_code), charge.status) == (64, 'held')


@pytest.mark.parametrize(
    ('results', 'expected'),
    [
        ([Readiness.UNAVAILABLE, Readiness.SHORT, Readiness.READY], Readiness.SHORT),
        ([Readiness.SHORT, Readiness.GOLD_REQUIRED], Readiness.GOLD_REQUIRED),
        ([Readiness.GOLD_REQUIRED, Readiness.NOT_FOR_SALE, Readiness.UNAVAILABLE], Readiness.NOT_FOR_SALE),
        ([Readiness.READY, Readiness.READY], Readiness.READY),
    ],
)
def test_the_reason_people_must_act_on_comes_first(results: list[Readiness], expected: Readiness):
    # 팔지 않는 모델은 방장이 모델을 바꿔야, 골드와 크레딧은 그 사람이 사야 풀린다. 답 없음은 저절로 풀린다
    assert worst(results) == expected
