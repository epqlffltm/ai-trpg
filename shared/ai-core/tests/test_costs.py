# shared/ai-core/tests/test_costs.py

"""
AI 호출 한 번의 원가를 세는 것(ai_core/costs.py)을 검증한다.

실제 모델을 부르지 않는다. 단가와 토큰 수는 테스트가 정한다.

둘을 본다.
  - 세기: 캐시 읽기·쓰기·나머지 입력·출력을 각자의 단가로. 캐시 단가가 없으면 입력 단가. 토큰 수를 모르면 모른다.
  - 사용량: 모델 목록의 모델이면 이름표와 원가, 목록에 없는 모델이면 토큰의 자세한 수만. 받지 못하면 원가가 없다.

원가가 호출의 기록(ai_invocations)에 남는 것은 게임 서버의 테스트(trpg-server/tests/test_call_costs.py)가 본다.
"""

from datetime import date
from decimal import Decimal

import pytest

from ai_core.calls import NO_USAGE, CallUsage
from ai_core.catalog_contract import UnitCost
from ai_core.costs import PriceTag, cost_usd, usage_of
from ai_core.provider import Completion

TODAY = date(2026, 10, 17)
# GPT-6 Luna 의 공식 단가(2026-10-17 확인): 입력 $0.10, 캐시 입력 $0.01, 출력 $0.50
LUNA_COST = UnitCost(
    cost_id=7, input_per_mtok=Decimal('0.1'), output_per_mtok=Decimal('0.5'), cached_input_per_mtok=Decimal('0.01')
)


def answer(input_tokens: int | None = 12_000, output_tokens: int | None = 1_200, **details) -> Completion:
    """토큰 수가 적힌 답."""
    return Completion(text='장면', model='m', input_tokens=input_tokens, output_tokens=output_tokens, **details)


# --- 세기 ---


def test_a_round_of_luna_costs_what_the_pricing_plan_says():
    # 입력 12,000, 출력 1,200: 0.0012 + 0.0006. 1달러 1,500원이면 2.7원이다
    assert cost_usd(answer(), LUNA_COST) == Decimal('0.0018')


def test_cached_input_is_counted_at_the_cached_price():
    # 캐시 아닌 입력 2,000 x 0.1 + 캐시 10,000 x 0.01 + 출력 1,200 x 0.5
    assert cost_usd(answer(cached_input_tokens=10_000), LUNA_COST) == Decimal('0.0009')


def test_cached_input_without_a_cached_price_is_counted_at_the_input_price():
    plain = UnitCost(cost_id=1, input_per_mtok=Decimal('0.1'), output_per_mtok=Decimal('0.5'))

    assert cost_usd(answer(cached_input_tokens=10_000), plain) == Decimal('0.0018')


def test_cache_writes_are_counted_at_their_price():
    claude = UnitCost(
        cost_id=2,
        input_per_mtok=Decimal('3'),
        output_per_mtok=Decimal('15'),
        cached_input_per_mtok=Decimal('0.3'),
        cache_write_per_mtok=Decimal('3.75'),
    )

    # 나머지 입력 2,000 x 3 + 캐시 쓰기 10,000 x 3.75 + 출력 1,200 x 15
    assert cost_usd(answer(cache_write_tokens=10_000), claude) == Decimal('0.0615')


def test_reasoning_is_part_of_the_output_and_not_counted_twice():
    assert cost_usd(answer(reasoning_tokens=800), LUNA_COST) == cost_usd(answer(), LUNA_COST)


@pytest.mark.parametrize(('input_tokens', 'output_tokens'), [(None, 1_200), (12_000, None), (None, None)])
def test_without_the_counts_the_cost_is_unknown(input_tokens: int | None, output_tokens: int | None):
    # 0 으로 적으면 쓴 돈이 없던 것처럼 보인다
    assert cost_usd(answer(input_tokens, output_tokens), LUNA_COST) is None


def test_a_cached_count_over_the_input_does_not_go_negative():
    assert cost_usd(answer(input_tokens=100, output_tokens=0, cached_input_tokens=200), LUNA_COST) == Decimal(
        '0.000002'
    )


def test_the_cost_keeps_eight_decimal_places():
    assert cost_usd(answer(input_tokens=1, output_tokens=0), LUNA_COST) == Decimal('0.00000010')


# --- 사용량 ---


def test_a_local_model_without_an_answer_has_no_usage():
    assert usage_of(None, None) is NO_USAGE


def test_a_local_model_keeps_the_detailed_counts_but_no_cost():
    usage = usage_of(answer(cached_input_tokens=1_000, reasoning_tokens=50), None)

    assert usage == CallUsage(cached_input_tokens=1_000, reasoning_tokens=50)


def test_a_catalog_model_gets_its_slug_cost_and_price_row():
    usage = usage_of(answer(), PriceTag('gpt-6-luna', LUNA_COST))

    assert (usage.model_slug, usage.cost_usd, usage.cost_id) == ('gpt-6-luna', Decimal('0.0018'), 7)


def test_a_failed_call_to_a_catalog_model_has_its_slug_but_no_cost():
    # 받지 못한 호출에는 공급자가 값을 매기지 않는다
    assert usage_of(None, PriceTag('gpt-6-luna', LUNA_COST)) == CallUsage(model_slug='gpt-6-luna')


def test_a_day_without_a_price_has_no_cost():
    usage = usage_of(answer(), PriceTag('gpt-6-luna', None))

    assert (usage.model_slug, usage.cost_usd, usage.cost_id) == ('gpt-6-luna', None, None)


def test_unknown_counts_leave_no_price_row():
    usage = usage_of(answer(input_tokens=None), PriceTag('gpt-6-luna', LUNA_COST))

    assert (usage.cost_usd, usage.cost_id) == (None, None)
