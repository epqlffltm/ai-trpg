# game-server/tests/test_call_costs.py

"""
AI 호출 한 번의 원가를 세는 것(app/ai/costs.py)과, 그것이 호출의 기록(ai_invocations)에 남는 것을 검증한다.

실제 모델을 부르지 않는다. 단가와 토큰 수는 테스트가 정한다.

넷을 본다.
  - 세기: 캐시 읽기·쓰기·나머지 입력·출력을 각자의 단가로. 캐시 단가가 없으면 입력 단가. 토큰 수를 모르면 모른다.
  - 사용량: 모델 목록의 모델이면 이름표와 원가, 목록에 없는 모델이면 토큰의 자세한 수만. 받지 못하면 원가가 없다.
  - 기록: 칸들이 DB 에 그대로 남는다.
  - 고르기에서 기록까지: 서술할 때 그날의 단가로 센 원가가 남는다. 모델 목록은 그날의 단가를 함께 돌려준다.
"""

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.call_log import DbCallLog
from app.ai.calls import NO_USAGE, CallRecord, CallScope, CallUsage, Outcome
from app.ai.costs import PriceTag, cost_usd, usage_of
from app.ai.fake import FakeCallLog
from app.ai.models import AiInvocation
from app.ai.provider import Completion, Reasoning
from app.ai.routing import Endpoint, ModelRouter
from app.catalog import service
from app.catalog.lookup import CatalogModel, DbModelLookup, UnitCost
from app.catalog.models import Grade, Provider, TokenLimitField
from app.catalog.schemas import CostCreate, ModelCreate
from app.rounds.narrator import Move, NarrationRequest, StoryContext
from app.rounds.routed_narrator import RoutedNarrator

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


# --- 기록 ---


@pytest.mark.usefixtures('clean_tables')
async def test_the_usage_is_written_to_the_database(app: FastAPI, session: AsyncSession):
    usage = CallUsage(
        cached_input_tokens=1_024,
        cache_write_tokens=0,
        reasoning_tokens=120,
        model_slug='gpt-6-luna',
        cost_usd=Decimal('0.0018'),
        cost_id=7,
    )
    record = CallRecord(
        scope=CallScope(purpose='narration'),
        provider='openai',
        model='gpt-6-luna-2026-09-22',
        prompt_version='narration-27',
        reasoning=Reasoning.NONE,
        outcome=Outcome.OK,
        latency_ms=900,
        input_tokens=12_000,
        output_tokens=1_200,
        usage=usage,
    )

    await DbCallLog(app.state.session_factory).write(record)

    row = await session.scalar(select(AiInvocation))
    assert (row.cached_input_tokens, row.cache_write_tokens, row.reasoning_tokens) == (1_024, 0, 120)
    assert (row.model_slug, row.cost_usd, row.cost_id) == ('gpt-6-luna', Decimal('0.00180000'), 7)


@pytest.mark.usefixtures('clean_tables')
async def test_a_record_without_usage_leaves_the_columns_empty(app: FastAPI, session: AsyncSession):
    record = CallRecord(
        scope=CallScope(purpose='narration'),
        provider='openai_compat',
        model='gemma4:26b',
        prompt_version='narration-27',
        reasoning=Reasoning.NONE,
        outcome=Outcome.OK,
        latency_ms=900,
    )

    await DbCallLog(app.state.session_factory).write(record)

    row = await session.scalar(select(AiInvocation))
    assert (row.model_slug, row.cost_usd, row.cost_id, row.reasoning_tokens) == (None, None, None, None)


# --- 고르기에서 기록까지 ---

LUNA = CatalogModel(
    slug='gpt-6-luna',
    provider=Provider.OPENAI,
    api_model_id='gpt-6-luna-2026-09-22',
    supports_reasoning=True,
    supports_temperature=True,
    token_limit_field=TokenLimitField.MAX_COMPLETION_TOKENS,
    enabled=True,
    retires_on=None,
    cost=LUNA_COST,
)


@dataclass
class OneModel:
    """모델 하나만 든 목록. 찾은 날이 쌓인다."""

    model: CatalogModel
    days: list[date] = field(default_factory=list)

    async def find(self, slug: str, day: date) -> CatalogModel | None:
        self.days.append(day)
        return self.model if slug == self.model.slug else None


def openai_answer() -> httpx.MockTransport:
    """글 하나와 자세한 토큰 수를 흘려 보내는 OpenAI 의 답."""
    usage = {
        'prompt_tokens': 12_000,
        'completion_tokens': 1_200,
        'prompt_tokens_details': {'cached_tokens': 10_000},
        'completion_tokens_details': {'reasoning_tokens': 200},
    }
    pieces = [
        {'model': 'gpt-6-luna-2026-09-22', 'choices': [{'index': 0, 'delta': {'content': '사이렌이 울린다.'}}]},
        {'model': 'gpt-6-luna-2026-09-22', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]},
        {'model': 'gpt-6-luna-2026-09-22', 'choices': [], 'usage': usage},
    ]
    text = ''.join(f'data: {json.dumps(piece, ensure_ascii=False)}\n\n' for piece in pieces) + 'data: [DONE]\n\n'
    return httpx.MockTransport(lambda request: httpx.Response(200, text=text))


async def test_a_narration_records_the_cost_with_the_price_of_the_day():
    lookup = OneModel(LUNA)
    router = ModelRouter(
        lookup=lookup,
        client=httpx.AsyncClient(transport=openai_answer()),
        local=Endpoint('http://127.0.0.1:11434/v1', None, 'openai_compat'),
        openai=Endpoint('https://api.openai.com/v1', SecretStr('sk-test'), 'openai'),
        timeout=30,
        today=lambda: TODAY,
    )
    log = FakeCallLog()
    story = StoryContext(title='추격전', rating='all', guide='추격은 언제나 바이크로 한다.')
    request = NarrationRequest(round_number=1, scene='도로.', moves=[Move('엘프', '달린다.')], story=story)

    await RoutedNarrator('gpt-6-luna', router, log).narrate(request)

    (record,) = log.records
    # 캐시 아닌 입력 2,000 x 0.1 + 캐시 10,000 x 0.01 + 출력 1,200 x 0.5. 생각은 출력에 들어 있다
    assert record.usage == CallUsage(
        cached_input_tokens=10_000,
        reasoning_tokens=200,
        model_slug='gpt-6-luna',
        cost_usd=Decimal('0.0009'),
        cost_id=7,
    )
    assert lookup.days == [TODAY]


LUNA_ROW = ModelCreate(
    slug='gpt-6-luna',
    provider=Provider.OPENAI,
    api_model_id='gpt-6-luna-2026-09-22',
    display_name='GPT-6 Luna',
    vendor='openai',
    grade=Grade.STANDARD,
    token_limit_field=TokenLimitField.MAX_COMPLETION_TOKENS,
)


def price(input_price: str, starts: date) -> CostCreate:
    """그날부터의 단가."""
    return CostCreate(
        input_per_mtok=Decimal(input_price), output_per_mtok=Decimal('0.5'), effective_from=starts, checked_on=TODAY
    )


@pytest.mark.usefixtures('clean_tables')
async def test_the_catalog_gives_the_price_of_the_day(app: FastAPI, session: AsyncSession):
    await service.add_model(session, LUNA_ROW)
    today_price = await service.add_cost(session, 'gpt-6-luna', price('0.1', TODAY))
    await service.add_cost(session, 'gpt-6-luna', price('0.2', TODAY + timedelta(days=30)))
    lookup = DbModelLookup(app.state.session_factory)

    found = await lookup.find('gpt-6-luna', TODAY)

    # 앞으로 쓸 단가가 아니라 그날의 단가다
    assert found.cost == UnitCost(cost_id=today_price.id, input_per_mtok=Decimal('0.1'), output_per_mtok=Decimal('0.5'))
    assert (await lookup.find('gpt-6-luna', TODAY + timedelta(days=30))).cost.input_per_mtok == Decimal('0.2')


@pytest.mark.usefixtures('clean_tables')
async def test_a_model_without_a_price_of_the_day_has_no_cost(app: FastAPI, session: AsyncSession):
    await service.add_model(session, LUNA_ROW)

    assert (await DbModelLookup(app.state.session_factory).find('gpt-6-luna', TODAY)).cost is None
