# shared/catalog-core/tests/test_repository.py

"""
모델 목록의 SQL(catalog_core/repository.py)을 본다. 받은 꾸러미의 표로 읽고 적는가.

메모리의 SQLite 로 돌린다. 모델마다 그날의 단가(costs_on)는 PostgreSQL 의 DISTINCT ON 이라 글자만 견준다.
실제 PostgreSQL 에서 도는 것은 쓰는 서버의 테스트(test_model_catalog.py 등)가 본다.
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from catalog_core import repository
from tests.tables import PLAIN, AiModel, AiModelCost, AiModelSnapshot

TODAY = date(2026, 10, 17)


def model(slug: str, vendor: str = 'openai', api_model_id: str | None = None) -> AiModel:
    return AiModel(
        slug=slug,
        provider='openai',
        api_model_id=api_model_id or f'{slug}-2026-09-22',
        display_name=slug,
        vendor=vendor,
        grade='standard',
    )


def cost(slug: str, input_price: str, starts: date = TODAY) -> AiModelCost:
    return AiModelCost(
        model_slug=slug,
        input_per_mtok=Decimal(input_price),
        output_per_mtok=Decimal(input_price) * 5,
        effective_from=starts,
        checked_on=starts,
    )


async def put(session: AsyncSession, *rows) -> None:
    for row in rows:
        await repository.add(session, row)
    await session.commit()


async def test_models_are_found_by_slug(session: AsyncSession):
    await put(session, model('luna'), model('sol'))

    assert (await repository.get_model(PLAIN, session, 'luna')).slug == 'luna'
    assert (await repository.lock_model(PLAIN, session, 'sol')).slug == 'sol'
    assert await repository.get_model(PLAIN, session, 'nova') is None
    assert set(await repository.models_in(PLAIN, session, {'luna', 'nova'})) == {'luna'}


async def test_models_are_listed_by_vendor_then_slug(session: AsyncSession):
    await put(session, model('sol', 'openai'), model('opus', 'anthropic'), model('luna', 'openai'))

    assert [row.slug for row in await repository.list_models(PLAIN, session)] == ['opus', 'luna', 'sol']


async def test_a_taken_api_model_is_found(session: AsyncSession):
    await put(session, model('luna'))

    assert await repository.api_model_taken(PLAIN, session, 'openai', 'luna-2026-09-22')
    assert not await repository.api_model_taken(PLAIN, session, 'openai', 'sol-2026-09-22')
    assert not await repository.api_model_taken(PLAIN, session, 'anthropic', 'luna-2026-09-22')


async def test_the_cost_of_a_day_is_the_latest_started_one(session: AsyncSession):
    later = TODAY + timedelta(days=10)
    await put(session, model('luna'), cost('luna', '0.1'), cost('luna', '0.2', later), cost('luna', '0.15'))

    assert (await repository.cost_on(PLAIN, session, 'luna', TODAY)).input_per_mtok == Decimal('0.15')
    assert (await repository.cost_on(PLAIN, session, 'luna', later)).input_per_mtok == Decimal('0.2')
    assert await repository.cost_on(PLAIN, session, 'luna', TODAY - timedelta(1)) is None
    history = await repository.cost_history(PLAIN, session, 'luna')
    assert [row.input_per_mtok for row in history] == [Decimal('0.2'), Decimal('0.15'), Decimal('0.1')]


async def test_snapshots_are_listed_latest_first(session: AsyncSession):
    first = AiModelSnapshot(model_slug='luna', previous_api_model_id='a', api_model_id='b')
    second = AiModelSnapshot(model_slug='luna', previous_api_model_id='b', api_model_id='c')
    await put(session, model('luna'), first, second)

    history = await repository.snapshot_history(PLAIN, session, 'luna')

    assert [row.api_model_id for row in history] == ['c', 'b']


class Recording:
    """보낸 쿼리를 적어 두고 빈 결과를 돌려주는 가짜 세션."""

    def __init__(self) -> None:
        self.queries = []

    async def scalars(self, query):
        self.queries.append(query)
        return []


async def test_costs_of_a_day_pick_one_row_per_model_with_distinct_on():
    session = Recording()

    assert await repository.costs_on(PLAIN, session, TODAY) == {}

    sql = str(session.queries[0].compile(dialect=postgresql.dialect()))
    assert 'DISTINCT ON (ai_model_costs.model_slug)' in sql
    assert 'ORDER BY ai_model_costs.model_slug, ai_model_costs.effective_from DESC, ai_model_costs.id DESC' in sql
