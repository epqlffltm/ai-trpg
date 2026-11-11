# shared/catalog-core/tests/test_lookup.py

"""
모델 하나를 찾는 것(catalog_core/lookup.py)을 본다. 찾은 것은 세션과 떨어진 값(CatalogModel)이다.
"""

from datetime import date
from decimal import Decimal

from ai_core.catalog_contract import Provider, ReasoningStyle, TokenLimitField, UnitCost
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog_core import repository
from catalog_core.lookup import DbModelLookup, to_value
from tests.tables import PLAIN, AiModel, AiModelCost

TODAY = date(2026, 10, 17)


def luna(**extra) -> AiModel:
    values = {
        'slug': 'luna',
        'provider': 'openai',
        'api_model_id': 'luna-2026-09-22',
        'display_name': 'Luna',
        'vendor': 'openai',
        'grade': 'standard',
        'supports_reasoning': True,
        'supports_temperature': False,
        'token_limit_field': 'max_completion_tokens',
        'reasoning_style': None,
        'enabled': True,
        'retires_on': None,
    }
    return AiModel(**{**values, **extra})


def test_a_model_without_cost_becomes_a_value():
    value = to_value(luna(reasoning_style='always', token_limit_field=None))

    assert value.provider is Provider.OPENAI
    assert value.token_limit_field is None
    assert value.reasoning_style is ReasoningStyle.ALWAYS
    assert value.cost is None


async def test_the_model_and_the_cost_of_the_day_are_found(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
):
    await repository.add(session, luna())
    row = AiModelCost(
        model_slug='luna',
        input_per_mtok=Decimal('0.1'),
        cached_input_per_mtok=Decimal('0.01'),
        output_per_mtok=Decimal('0.5'),
        effective_from=TODAY,
        checked_on=TODAY,
    )
    await repository.add(session, row)
    await session.commit()

    found = await DbModelLookup(session_factory, PLAIN).find('luna', TODAY)

    assert (found.slug, found.enabled, found.token_limit_field) == (
        'luna',
        True,
        TokenLimitField.MAX_COMPLETION_TOKENS,
    )
    assert found.cost == UnitCost(
        cost_id=row.id,
        input_per_mtok=Decimal('0.1'),
        output_per_mtok=Decimal('0.5'),
        cached_input_per_mtok=Decimal('0.01'),
        cache_write_per_mtok=None,
    )


async def test_an_unknown_slug_is_none(session_factory: async_sessionmaker[AsyncSession]):
    assert await DbModelLookup(session_factory, PLAIN).find('nova', TODAY) is None
