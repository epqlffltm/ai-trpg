# game-server/tests/test_prices.py

"""
결제 서버의 가격 목록의 값(app/billing/prices.py)을 검증한다.

결제 서버 README 의 예시 모양을 읽는 것, 팔지 않는 이름과 판매를 멈추는 예약, 예약 시각이 지나면
스스로 갈아 끼우는 것, 가격표 이름의 모양을 본다.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.billing import charges
from app.billing.prices import Change, Price, Sale, Tier, narration_code, parse_price_list, price_at

AT = datetime(2026, 11, 30, 15, 0, tzinfo=UTC)

# 결제 서버 README 의 예시(billing-server/README.md 의 "가격 목록")와 같은 모양
EXAMPLE = {
    'prices': [
        {
            'code': 'narration.gemini-4-argon.i0.o0',
            'credits': '120',
            'since': '2026-10-17T00:00:00Z',
            'tier': 'standard',
            'next': {'credits': '240', 'tier': 'premium', 'effective_at': '2026-11-30T15:00:00Z'},
        },
        {
            'code': 'narration.old-model.i0.o0',
            'credits': '30',
            'since': '2026-10-01T00:00:00Z',
            'tier': 'standard',
            'next': {'credits': None, 'tier': None, 'effective_at': '2026-12-01T00:00:00Z'},
        },
        {
            'code': 'narration.coming.i0.o0',
            'credits': None,
            'since': None,
            'tier': None,
            'next': {'credits': '60', 'tier': 'standard', 'effective_at': '2026-11-01T00:00:00Z'},
        },
        {
            'code': 'narration.plain.i0.o0',
            'credits': '0.0120',
            'since': '2026-10-01T00:00:00Z',
            'tier': 'standard',
            'next': None,
        },
    ]
}


def test_the_example_of_the_billing_server_is_read():
    book = parse_price_list(json.dumps(EXAMPLE).encode())

    argon = book.prices['narration.gemini-4-argon.i0.o0']
    assert argon.current == Sale(credits='120', tier=Tier.STANDARD)
    assert argon.next == Change(sale=Sale(credits='240', tier=Tier.PREMIUM), effective_at=AT)
    # 값은 글자 그대로 둔다. 게임 서버는 셈하지 않고 보여 주기만 한다
    assert book.prices['narration.plain.i0.o0'].current == Sale(credits='0.0120', tier=Tier.STANDARD)
    assert book.free is False


def test_a_name_reserved_only_is_not_on_sale_now():
    book = parse_price_list(json.dumps(EXAMPLE).encode())

    coming = book.prices['narration.coming.i0.o0']
    assert coming.current is None
    assert coming.next is not None and coming.next.sale == Sale(credits='60', tier=Tier.STANDARD)


def test_a_reservation_without_credits_stops_the_sale():
    book = parse_price_list(json.dumps(EXAMPLE).encode())

    old = book.prices['narration.old-model.i0.o0']
    assert old.next is not None and old.next.sale is None


def test_unknown_fields_are_ignored():
    body = {'prices': [{**EXAMPLE['prices'][3], 'currency': 'credit'}], 'generated_at': 'now'}

    # 결제 서버가 칸을 더해도 깨지지 않는다
    assert list(parse_price_list(json.dumps(body).encode()).prices) == ['narration.plain.i0.o0']


@pytest.mark.parametrize(
    'body',
    [
        b'not json',
        b'{}',
        json.dumps({'prices': [{**EXAMPLE['prices'][3], 'credits': '-5'}]}).encode(),
        json.dumps({'prices': [{**EXAMPLE['prices'][3], 'tier': 'gold'}]}).encode(),
        json.dumps(
            {
                'prices': [
                    {
                        **EXAMPLE['prices'][0],
                        'next': {'credits': '1', 'tier': 'standard', 'effective_at': '2026-11-30T15:00:00'},
                    }
                ]
            }
        ).encode(),
    ],
)
def test_a_body_of_the_wrong_shape_is_refused(body: bytes):
    # 시간대가 없는 시각도 거절한다. 언제 바뀌는지 틀리게 읽는다
    with pytest.raises(ValidationError):
        parse_price_list(body)


def test_the_reservation_takes_over_when_its_time_comes():
    price = Price(
        code='narration.gemini-4-argon.i0.o0',
        current=Sale('120', Tier.STANDARD),
        next=Change(Sale('240', Tier.PREMIUM), AT),
    )

    # 1분마다 다시 받는 사이에 시각이 지나도 늦게 보이지 않는다
    assert price_at(price, AT - timedelta(seconds=1)) == price
    assert price_at(price, AT) == Price(code=price.code, current=Sale('240', Tier.PREMIUM))


def test_a_stop_takes_the_name_off_sale_when_its_time_comes():
    price = Price(code='narration.old-model.i0.o0', current=Sale('30', Tier.STANDARD), next=Change(None, AT))

    assert price_at(price, AT).current is None


def test_the_price_code_of_a_model_is_its_slug_with_the_base_steps():
    assert narration_code('claude-sonnet-5-5') == 'narration.claude-sonnet-5-5.i0.o0'
    # 등급의 가격표 이름과 앞부분이 같다(app/billing/charges.py)
    assert charges.price_code_for('standard').split('.')[0] == narration_code('x').split('.')[0]
