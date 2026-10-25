# story-server/tests/test_billing_client.py

"""
결제 서버를 부르는 것(app/billing/)을 결제 서버 없이 검증한다. 게임 서버의 같은 테스트를 옮겼다.

  - 서명: 보내는 바이트 그대로에 서명한다. 서명이 결제 서버(Go)와 같은지는 공용 코드의 테스트가 본다
    (shared/server-core 의 service_auth). 따로 계산하는 가짜 결제 서버가 받아들인다.
  - 답의 뜻: 결제 서버가 정한 상태 코드마다 결과나 예외가 무엇인지(app/billing/http_billing.py 의 표).
  - 설정: 주소를 비우면 받지 않는다. 주소를 적었으면 비밀이 있어야 뜬다.
"""

import json
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from server_core.service_auth.signing import SIGNATURE_HEADER, sign

from app.billing.client import (
    BillingRejected,
    BillingUnavailable,
    ExtendOutcome,
    ExtendResult,
    HoldOutcome,
    HoldResult,
)
from app.billing.free_billing import FreeBilling
from app.billing.http_billing import CAPTURE_PATH, EXTEND_PATH, HOLDS_PATH, RELEASE_PATH, HttpBilling
from app.billing.metered import MeteredBilling
from app.billing.price_list import FreePriceList, HttpPriceList
from app.billing.setup import build_billing, build_price_list
from tests.billing import BILLING_URL, SECRET, FakeBillingServer
from tests.conftest import make_test_settings

USER = uuid.UUID('11111111-2222-4333-8444-555555555555')
REFERENCE = 'story:message:abc'


class Recorder:
    """받은 요청을 적고, 정해 둔 답을 내는 결제 서버. answer 가 예외면 그것을 낸다."""

    def __init__(self, answer: httpx.Response | Exception) -> None:
        self.answer = answer
        self.requests: list[httpx.Request] = []

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def billing_answering(answer: httpx.Response | Exception) -> tuple[HttpBilling, Recorder]:
    """정해 둔 답을 받는 결제 서버로 부르는 것."""
    recorder = Recorder(answer)
    client = httpx.AsyncClient(transport=httpx.MockTransport(recorder.handle))
    billing = HttpBilling(client=client, base_url=BILLING_URL, secret=SecretStr(SECRET), timeout=5.0, clock=lambda: 1.0)
    return billing, recorder


def hold_body(status: str) -> dict:
    return {'reference': REFERENCE, 'status': status}


async def test_a_hold_sends_the_signed_body_it_signed():
    billing, recorder = billing_answering(httpx.Response(201, json=hold_body('held')))

    await billing.hold(REFERENCE, USER, 'story.standard')

    request = recorder.requests[0]
    assert str(request.url) == f'{BILLING_URL}{HOLDS_PATH}'
    assert json.loads(request.content) == {
        'user_id': str(USER),
        'reference': REFERENCE,
        'price_code': 'story.standard',
    }
    # 보낸 바이트 그대로에 서명했다. 금액은 보내지 않는다
    assert request.headers[SIGNATURE_HEADER] == sign(SECRET, 1, 'POST', HOLDS_PATH, request.content)
    assert request.headers['Content-Type'] == 'application/json'


async def test_a_fake_billing_server_accepts_the_signature():
    server = FakeBillingServer(balances={USER: 100})
    async with server.make_client() as client:
        result = await server.billing(client).hold(REFERENCE, USER, 'story.standard')

    # 서명을 따로 계산하는 가짜 결제 서버가 받아들였다
    assert result.result == HoldResult.HELD
    assert server.balance(USER) == 50


async def test_a_wrong_secret_is_refused_by_the_billing_server():
    server = FakeBillingServer(secret='another-secret-0123456789abcdef0123', balances={USER: 100})
    async with server.make_client() as client:
        with pytest.raises(BillingUnavailable) as raised:
            await server.billing(client).hold(REFERENCE, USER, 'story.standard')

    assert raised.value.reason == 'unauthorized'
    assert server.balance(USER) == 100


@pytest.mark.parametrize(
    ('answer', 'result'),
    [
        (httpx.Response(201, json=hold_body('held')), HoldResult.HELD),
        # 같은 이름표로 이미 건 것을 돌려받았다. 새로 빼지 않았다
        (httpx.Response(200, json=hold_body('held')), HoldResult.HELD),
        (httpx.Response(402, json={'detail': '모자란다'}), HoldResult.SHORT),
        # 프리미엄 가격표인데 골드가 모자란다. 실버가 있어도 같다
        (httpx.Response(402, json={'code': 'credit.gold_required'}), HoldResult.GOLD_REQUIRED),
    ],
)
async def test_what_a_hold_answer_means(answer: httpx.Response, result: HoldResult):
    billing, _ = billing_answering(answer)

    assert (await billing.hold(REFERENCE, USER, 'story.standard')).result == result


@pytest.mark.parametrize(
    ('answer', 'reason'),
    [
        (httpx.Response(401), 'unauthorized'),
        (httpx.Response(408), 'server_error'),
        (httpx.Response(429), 'server_error'),
        (httpx.Response(500), 'server_error'),
        (httpx.Response(503), 'server_error'),
        (httpx.Response(200, text='<html>proxy</html>'), 'bad_response'),
        (httpx.ConnectError('연결할 수 없다'), 'unreachable'),
        (httpx.ReadTimeout('늦다'), 'timeout'),
    ],
)
async def test_answers_worth_trying_again(answer: httpx.Response | Exception, reason: str):
    billing, _ = billing_answering(answer)

    with pytest.raises(BillingUnavailable) as raised:
        await billing.hold(REFERENCE, USER, 'story.standard')

    assert raised.value.reason == reason
    # 비밀은 예외에 실리지 않는다
    assert SECRET not in str(raised.value)


@pytest.mark.parametrize(
    'answer',
    [
        httpx.Response(400, json={'detail': '이름표의 모양이 틀렸다'}),
        httpx.Response(404, json={'detail': '없다'}),
        httpx.Response(409, json={'detail': '다른 사용자가 쓴 이름표'}),
        # 같은 이름표의 홀드가 이미 돌려준 것이다. 다시 걸 수 없다
        httpx.Response(200, json=hold_body('released')),
    ],
)
async def test_a_hold_the_billing_server_will_never_take(answer: httpx.Response):
    billing, _ = billing_answering(answer)

    with pytest.raises(BillingRejected) as raised:
        await billing.hold(REFERENCE, USER, 'story.standard')

    assert raised.value.status_code == answer.status_code


@pytest.mark.parametrize(
    ('expires_at', 'expected'),
    [
        # 결제 서버(Go)의 모양. 나노초까지 오고 끝이 Z 다
        ('2026-10-12T10:00:00.123456789Z', datetime(2026, 10, 12, 10, 0, 0, 123456, tzinfo=UTC)),
        ('2026-10-12T10:00:00Z', datetime(2026, 10, 12, 10, 0, tzinfo=UTC)),
        # 시간대가 없으면 UTC 로 본다
        ('2026-10-12T10:00:00', datetime(2026, 10, 12, 10, 0, tzinfo=UTC)),
        # 없거나 읽을 수 없으면 모른다. 실패로 보지 않는다
        (None, None),
        ('어제', None),
    ],
)
async def test_the_expiry_of_a_hold_is_read_from_the_answer(expires_at: str | None, expected: datetime | None):
    body = {**hold_body('held'), **({'expires_at': expires_at} if expires_at else {})}
    billing, _ = billing_answering(httpx.Response(201, json=body))

    outcome = await billing.hold(REFERENCE, USER, 'story.standard')

    assert outcome == HoldOutcome(HoldResult.HELD, expected)


async def test_the_new_expiry_comes_back_from_an_extension():
    body = {**hold_body('held'), 'expires_at': '2026-10-13T10:00:00Z'}
    billing, _ = billing_answering(httpx.Response(200, json=body))

    outcome = await billing.extend(REFERENCE)

    assert outcome == ExtendOutcome(ExtendResult.EXTENDED, datetime(2026, 10, 13, 10, 0, tzinfo=UTC))


async def test_a_capture_goes_to_its_address():
    billing, recorder = billing_answering(httpx.Response(200, json=hold_body('captured')))

    await billing.capture(REFERENCE)

    request = recorder.requests[0]
    assert request.url.path == CAPTURE_PATH
    assert json.loads(request.content) == {'reference': REFERENCE}


@pytest.mark.parametrize(
    'answer', [httpx.Response(404), httpx.Response(409), httpx.Response(200, json=hold_body('held'))]
)
async def test_a_capture_that_did_not_happen_is_rejected(answer: httpx.Response):
    billing, _ = billing_answering(answer)

    with pytest.raises(BillingRejected):
        await billing.capture(REFERENCE)


@pytest.mark.parametrize('answer', [httpx.Response(200, json=hold_body('released')), httpx.Response(404)])
async def test_a_release_with_nothing_left_to_hold_is_done(answer: httpx.Response):
    billing, recorder = billing_answering(answer)

    # 걸린 적이 없는 홀드(404)도 돌려줄 것이 없으니 된 것이다
    await billing.release(REFERENCE)

    assert recorder.requests[0].url.path == RELEASE_PATH


async def test_releasing_a_captured_hold_is_rejected():
    billing, _ = billing_answering(httpx.Response(409))

    with pytest.raises(BillingRejected):
        await billing.release(REFERENCE)


@pytest.mark.parametrize(
    ('answer', 'result'),
    [
        (httpx.Response(200, json=hold_body('held')), ExtendResult.EXTENDED),
        (httpx.Response(404, json={'detail': '없다'}), ExtendResult.MISSING),
        # 이미 끝난 홀드. 만료되어 결제 서버가 돌려준 것도 여기다
        (httpx.Response(409, json={'detail': '끝났다'}), ExtendResult.ENDED),
    ],
)
async def test_what_an_extend_answer_means(answer: httpx.Response, result: ExtendResult):
    billing, recorder = billing_answering(answer)

    assert (await billing.extend(REFERENCE)).result == result
    assert recorder.requests[0].url.path == EXTEND_PATH
    assert json.loads(recorder.requests[0].content) == {'reference': REFERENCE}


@pytest.mark.parametrize(
    ('answer', 'error'),
    [
        (httpx.Response(503), BillingUnavailable),
        (httpx.Response(401), BillingUnavailable),
        (httpx.Response(400), BillingRejected),
        (httpx.Response(200, json=hold_body('captured')), BillingRejected),
    ],
)
async def test_an_extend_that_did_not_happen(answer: httpx.Response, error: type[Exception]):
    billing, _ = billing_answering(answer)

    with pytest.raises(error):
        await billing.extend(REFERENCE)


async def test_free_billing_always_holds():
    free = FreeBilling()

    assert await free.hold(REFERENCE, USER, 'story.standard') == HoldOutcome(HoldResult.HELD)
    await free.capture(REFERENCE)
    await free.release(REFERENCE)
    # 만료 시각을 주지 않는다
    assert await free.extend(REFERENCE) == ExtendOutcome(ExtendResult.EXTENDED)


def test_without_an_address_nothing_is_charged():
    settings = make_test_settings()

    assert isinstance(build_billing(settings, httpx.AsyncClient()), FreeBilling)


def test_with_an_address_the_billing_server_is_called():
    settings = make_test_settings(billing_url=BILLING_URL, billing_secret=SECRET)

    billing = build_billing(settings, httpx.AsyncClient())

    # 부를 때마다 센다(app/billing/metered.py)
    assert isinstance(billing, MeteredBilling)
    assert isinstance(billing.inner, HttpBilling)
    assert billing.inner.base_url == BILLING_URL


@pytest.mark.parametrize('secret', ['', 'short-secret'])
def test_an_address_without_a_long_secret_does_not_start(secret: str):
    with pytest.raises(ValidationError, match='BILLING_SECRET'):
        make_test_settings(billing_url=BILLING_URL, billing_secret=secret)


def test_a_blank_address_needs_no_secret():
    settings = make_test_settings(billing_url='  ', billing_secret='')

    assert isinstance(build_billing(settings, httpx.AsyncClient()), FreeBilling)


def test_a_call_cannot_take_longer_than_the_billing_budget():
    with pytest.raises(ValidationError):
        make_test_settings(billing_timeout_seconds=10.5)


def test_the_secret_is_not_shown():
    settings = make_test_settings(billing_url=BILLING_URL, billing_secret=SECRET)

    assert SECRET not in repr(settings)


@pytest.mark.parametrize(
    ('error', 'unavailable'),
    [
        (BillingRejected(400, 'price.not_for_sale'), True),
        (BillingRejected(400, 'price.unknown'), True),
        (BillingRejected(409), False),
        (BillingRejected(400, 'reference.invalid'), False),
    ],
)
def test_a_price_not_on_sale_is_not_a_bug(error: BillingRejected, unavailable: bool):
    # 판매를 멈췄거나 아직 열지 않은 모델이다. 말을 보내는 길이 사람에게 모델을 다시 고르게 한다
    assert error.price_unavailable is unavailable


def test_the_price_list_follows_the_billing_address():
    client = httpx.AsyncClient()
    settings = make_test_settings(billing_url=BILLING_URL + ' ', billing_secret=SECRET)

    prices = build_price_list(settings, client)

    # 홀드와 같은 주소, 비밀, 시간 상한, 앱의 연결 풀이다
    assert isinstance(prices, HttpPriceList)
    assert (prices.base_url, prices.secret.get_secret_value(), prices.timeout) == (BILLING_URL, SECRET, 5.0)
    assert prices.client is client
    assert isinstance(build_price_list(make_test_settings(), client), FreePriceList)
