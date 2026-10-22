# trpg-server/tests/test_call_costs.py

"""
AI 호출 한 번의 원가(ai_core/costs.py)가 호출의 기록(ai_invocations)에 남는 것을 검증한다.

실제 모델을 부르지 않는다. 단가와 토큰 수는 테스트가 정한다.
원가를 세는 것 자체(세기, 사용량)는 공용 코드의 테스트(shared/ai-core/tests/test_costs.py)가 본다.

둘을 본다.
  - 기록: 칸들이 DB 에 그대로 남는다.
  - 고르기에서 기록까지: 서술할 때 그날의 단가로 센 원가가 남는다. 모델 목록은 그날의 단가를 함께 돌려준다.
"""

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest
from ai_core.calls import CallRecord, CallScope, CallUsage, Outcome
from ai_core.catalog_contract import CatalogModel, Provider, TokenLimitField, UnitCost
from ai_core.catalog_file import CostEntry, ModelEntry
from ai_core.fake import FakeCallLog
from ai_core.provider import Reasoning
from ai_core.routing import Endpoint, ModelRouter
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_log.call_log import DbCallLog
from app.ai_log.models import AiInvocation
from app.catalog.lookup import DbModelLookup
from app.catalog.models import Grade
from app.rounds.narrator import Move, NarrationRequest, StoryContext
from app.rounds.routed_narrator import RoutedNarrator
from tests.catalog_rows import add_cost, put_models

TODAY = date(2026, 10, 17)
# GPT-6 Luna 의 공식 단가(2026-10-17 확인): 입력 $0.10, 캐시 입력 $0.01, 출력 $0.50
LUNA_COST = UnitCost(
    cost_id=7, input_per_mtok=Decimal('0.1'), output_per_mtok=Decimal('0.5'), cached_input_per_mtok=Decimal('0.01')
)


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


LUNA_ROW = ModelEntry(
    slug='gpt-6-luna',
    provider=Provider.OPENAI,
    api_model_id='gpt-6-luna-2026-09-22',
    display_name='GPT-6 Luna',
    vendor='openai',
    grade=Grade.STANDARD,
    token_limit_field=TokenLimitField.MAX_COMPLETION_TOKENS,
)


def price(input_price: str, starts: date) -> CostEntry:
    """그날부터의 단가."""
    return CostEntry(
        input_per_mtok=Decimal(input_price), output_per_mtok=Decimal('0.5'), effective_from=starts, checked_on=TODAY
    )


@pytest.mark.usefixtures('clean_tables')
async def test_the_catalog_gives_the_price_of_the_day(app: FastAPI, session: AsyncSession):
    await put_models(session, LUNA_ROW)
    today_price = await add_cost(session, 'gpt-6-luna', price('0.1', TODAY))
    await add_cost(session, 'gpt-6-luna', price('0.2', TODAY + timedelta(days=30)))
    lookup = DbModelLookup(app.state.session_factory)

    found = await lookup.find('gpt-6-luna', TODAY)

    # 앞으로 쓸 단가가 아니라 그날의 단가다
    assert found.cost == UnitCost(cost_id=today_price.id, input_per_mtok=Decimal('0.1'), output_per_mtok=Decimal('0.5'))
    assert (await lookup.find('gpt-6-luna', TODAY + timedelta(days=30))).cost.input_per_mtok == Decimal('0.2')


@pytest.mark.usefixtures('clean_tables')
async def test_a_model_without_a_price_of_the_day_has_no_cost(app: FastAPI, session: AsyncSession):
    await put_models(session, LUNA_ROW)

    assert (await DbModelLookup(app.state.session_factory).find('gpt-6-luna', TODAY)).cost is None
