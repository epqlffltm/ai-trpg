# game-server/tests/test_model_retirement.py

"""
서술 모델의 은퇴를 알리고 바꾸는 것(app/tables/model_retirement.py, app/tables/retirement_watch.py)을 검증한다.

보는 것.
  - 알리는 단계: 30, 14, 7, 1 일 전에 한 번씩. 같은 단계는 두 번 알리지 않는다. 늦게 보면 지금 단계 하나만.
  - 바꾸기: 은퇴하면 같은 회사의 대신 쓸 모델로. 아직 서술하지 않은 지금 라운드도 바꾸고 이벤트로 알린다.
    은퇴만 바꾼다(운영자가 끈 것은 그대로). 같은 회사에 없으면 바꾸지 않고 한 번 알린다.
  - 라운드가 열린 뒤에도 본다: 테이블을 시작할 때, 서술이 끝나 다음 라운드가 열릴 때.
  - 고를 수 있는 모델의 목록에 은퇴일이 보인다.
"""

import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.price_list import PriceListUnavailable
from app.billing.prices import Tier
from app.billing.routing import utc_now
from app.catalog import service as catalog
from app.tables import repository as table_repository
from app.tables.model_retirement import notice_stage
from app.tables.retirement_watch import RetirementWatch
from tests.signing import SigningKey
from tests.test_model_offers import LUNA, FixedPrices, add_enabled, book, on_sale
from tests.test_npc_actions import bearer, declare, events_of, table_url
from tests.test_recommended_model import MINI
from tests.test_round_time_limit import current, open_with, start_with

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
NOW = datetime(2026, 10, 18, 3, 0, tzinfo=UTC)
TODAY = NOW.date()
MODELS_URL = '/api/v1/game/tables/narration-models'


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장."""
    return bearer(signing_key, ME)


@pytest.fixture
async def models(app: FastAPI, session: AsyncSession, clean_tables) -> None:
    """켜진 OpenAI 모델 둘(Luna, Mini). 결제 서버는 둘 다 판다. 대신 쓸 모델을 고르면 standard 인 Mini 다."""
    for data in (LUNA, MINI):
        await add_enabled(session, data)
    app.state.price_list = FixedPrices(book(on_sale('gpt-6-luna', '30'), on_sale('gpt-6-mini', '10')))
    app.dependency_overrides[utc_now] = lambda: NOW
    set_clock(app, NOW)


def set_clock(app: FastAPI, now: datetime) -> RetirementWatch:
    """앱의 은퇴 지켜보기의 시계를 now 로 바꿔 꽂는다. 바꾼 것을 돌려준다."""
    app.state.retirement_watch = replace(app.state.retirement_watch, clock=lambda: now)
    return app.state.retirement_watch


async def tick(app: FastAPI, now: datetime) -> None:
    """그 시각에 지켜보기가 한 바퀴 돈다."""
    await set_clock(app, now).tick()


async def retire(session: AsyncSession, slug: str, on: date) -> None:
    """모델의 은퇴일을 적는다."""
    await catalog.retire_model(session, slug, on)


async def table_model(session: AsyncSession, table: dict) -> str:
    """DB 에 있는 테이블의 서술 모델."""
    query = text('SELECT narration_model FROM game_tables WHERE id = :id')
    return await session.scalar(query, {'id': uuid.UUID(table['id'])})


# --- 알리는 단계 ---


@pytest.mark.parametrize(
    ('left', 'stage'),
    [(31, None), (30, 30), (20, 30), (15, 30), (14, 14), (8, 14), (7, 7), (2, 7), (1, 1), (0, None), (-3, None)],
)
def test_the_stages_are_thirty_fourteen_seven_and_one_day(left: int, stage: int | None):
    assert notice_stage(TODAY + timedelta(days=left), TODAY) == stage


@pytest.mark.usefixtures('models')
async def test_each_stage_is_noticed_once(client: AsyncClient, app: FastAPI, session: AsyncSession, me):
    table = await start_with(client, me, narration_model='gpt-6-luna')
    await retire(session, 'gpt-6-luna', TODAY + timedelta(days=20))

    await tick(app, NOW)
    await tick(app, NOW + timedelta(hours=1))
    await tick(app, NOW + timedelta(days=7))
    notices = await events_of(client, me, table, 'narration_model_retiring')

    # 20 일 남았을 때 30 일 단계, 13 일 남았을 때 14 일 단계. 같은 단계는 다시 알리지 않는다
    assert [(event['payload']['days_left'], event['payload']['retires_on']) for event in notices] == [
        (20, '2026-11-07'),
        (13, '2026-11-07'),
    ]
    assert notices[0]['payload']['narration_model'] == 'gpt-6-luna'


@pytest.mark.usefixtures('models')
async def test_a_late_look_notices_only_the_stage_reached(client: AsyncClient, app: FastAPI, session, me):
    table = await start_with(client, me, narration_model='gpt-6-luna')
    await retire(session, 'gpt-6-luna', TODAY + timedelta(days=3))

    await tick(app, NOW)

    # 서버가 꺼져 있다가 3 일 남았을 때 처음 봤다. 30, 14 일 단계를 몰아서 알리지 않는다
    (notice,) = await events_of(client, me, table, 'narration_model_retiring')
    assert notice['payload']['days_left'] == 3


@pytest.mark.usefixtures('models')
async def test_a_postponed_retirement_counts_again(client: AsyncClient, app: FastAPI, session, me):
    table = await start_with(client, me, narration_model='gpt-6-luna')
    await retire(session, 'gpt-6-luna', TODAY + timedelta(days=5))
    await tick(app, NOW)

    await retire(session, 'gpt-6-luna', TODAY + timedelta(days=25))
    await tick(app, NOW + timedelta(hours=1))

    # 공급자가 은퇴를 미뤘다. 새 은퇴일로 처음부터 센다
    notices = await events_of(client, me, table, 'narration_model_retiring')
    assert [event['payload']['days_left'] for event in notices] == [5, 25]


@pytest.mark.usefixtures('models')
async def test_the_host_changing_the_model_counts_again(client: AsyncClient, app: FastAPI, session, me):
    # 모집 중인 테이블이다. 시작한 테이블은 쓸 수 있는 모델을 바꾸지 못한다(app/tables/narration_models.py)
    table = (await open_with(client, me, narration_model='gpt-6-luna')).json()
    await retire(session, 'gpt-6-luna', TODAY + timedelta(days=5))
    await tick(app, NOW)

    for model in ('gpt-6-mini', 'gpt-6-luna'):
        await client.put(table_url(table, '/narration-model'), json={'narration_model': model}, headers=me)
    await tick(app, NOW + timedelta(hours=1))

    # 모델을 바꾸면 알린 것을 지운다. 다시 Luna 를 고르면 그 은퇴를 다시 알린다
    assert len(await events_of(client, me, table, 'narration_model_retiring')) == 2


# --- 바꾸기 ---


@pytest.mark.usefixtures('models')
async def test_a_retired_model_is_replaced_in_the_table_and_the_open_round(
    client: AsyncClient, app: FastAPI, session: AsyncSession, me
):
    table = await start_with(client, me, narration_model='gpt-6-luna')
    await retire(session, 'gpt-6-luna', TODAY)

    await tick(app, NOW)
    (replaced,) = await events_of(client, me, table, 'narration_model_replaced')

    # 같은 회사의 standard 중 가장 싼 Mini 다. 선언을 받는 중인 1 라운드도 바뀌고 새 가격표로 다시 건다
    assert await table_model(session, table) == 'gpt-6-mini'
    assert (await current(client, me, table))['narration_model'] == 'gpt-6-mini'
    # 바뀐 라운드의 1인 1라운드의 값도 새 모델의 것으로 알린다
    assert replaced['payload'] == {
        'from': 'gpt-6-luna',
        'narration_model': 'gpt-6-mini',
        'reason': 'retired',
        'round': 1,
        'price': {'credits': '10', 'tier': 'standard'},
    }
    # 바꾼 뒤에는 볼 것이 없다
    await tick(app, NOW + timedelta(hours=1))
    assert len(await events_of(client, me, table, 'narration_model_replaced')) == 1


@pytest.mark.usefixtures('models')
async def test_replacing_forgets_the_notices_of_the_old_model(client: AsyncClient, app: FastAPI, session, me):
    table = await start_with(client, me, narration_model='gpt-6-luna')
    await retire(session, 'gpt-6-luna', TODAY + timedelta(days=1))
    await tick(app, NOW)

    await tick(app, NOW + timedelta(days=1))
    notices = await session.execute(
        text('SELECT retire_notice_for, retire_notice_days FROM game_tables WHERE id = :id'),
        {'id': uuid.UUID(table['id'])},
    )

    # 새 모델의 은퇴는 처음부터 센다
    assert notices.one() == (None, None)


@pytest.mark.usefixtures('models')
async def test_an_ended_table_is_left_alone(client: AsyncClient, app: FastAPI, session: AsyncSession, me):
    table = await start_with(client, me, narration_model='gpt-6-luna')
    await client.post(table_url(table, '/end'), headers=me)
    await retire(session, 'gpt-6-luna', TODAY)

    await set_clock(app, NOW).check(uuid.UUID(table['id']), NOW)
    found = await table_repository.find_tables_near_retirement(session, TODAY, 30)

    # 작업이 찾지도 않고, 찾았다 해도(찾은 뒤 끝났다) 바꾸지 않는다
    assert uuid.UUID(table['id']) not in found
    assert await events_of(client, me, table, 'narration_model_replaced') == []


@pytest.mark.usefixtures('models')
@pytest.mark.parametrize(('left', 'watched'), [(31, False), (30, True), (0, True), (-5, True)])
async def test_the_watch_looks_at_tables_within_thirty_days(
    client: AsyncClient, session: AsyncSession, me, left: int, watched: bool
):
    table = await start_with(client, me, narration_model='gpt-6-luna')
    await retire(session, 'gpt-6-luna', TODAY + timedelta(days=left))

    found = await table_repository.find_tables_near_retirement(session, TODAY, 30)

    assert (uuid.UUID(table['id']) in found) is watched


@pytest.mark.usefixtures('models')
async def test_the_operator_fallback_is_used_first(client: AsyncClient, app: FastAPI, session: AsyncSession, me):
    table = await start_with(client, me, narration_model='gpt-6-mini')
    await catalog.set_fallback(session, 'gpt-6-luna', TODAY)
    await retire(session, 'gpt-6-mini', TODAY)

    await tick(app, NOW)

    assert await table_model(session, table) == 'gpt-6-luna'


@pytest.mark.usefixtures('models')
async def test_a_disabled_model_is_not_replaced(client: AsyncClient, app: FastAPI, session: AsyncSession, me):
    table = await start_with(client, me, narration_model='gpt-6-luna')
    await catalog.disable_model(session, 'gpt-6-luna')

    await tick(app, NOW)

    # 운영자가 잠깐 끈 것이다. 은퇴가 아니라 바꾸지 않는다(방장에게 알리고 방장이 바꾸는 길)
    assert await table_model(session, table) == 'gpt-6-luna'
    assert await events_of(client, me, table, 'narration_model_replaced') == []


@pytest.mark.usefixtures('models')
async def test_without_a_replacement_the_host_is_told_once(client: AsyncClient, app: FastAPI, session, me):
    table = await start_with(client, me, narration_model='gpt-6-luna')
    await catalog.disable_model(session, 'gpt-6-mini')
    await retire(session, 'gpt-6-luna', TODAY)

    await tick(app, NOW)
    await tick(app, NOW + timedelta(hours=1))

    # 같은 회사에 대신할 모델이 없다. 다른 회사로 넘기지 않는다. 방장이 고를 때까지 그대로다
    (stranded,) = await events_of(client, me, table, 'narration_model_unavailable')
    assert stranded['payload'] == {'narration_model': 'gpt-6-luna', 'reason': 'retired'}
    assert await table_model(session, table) == 'gpt-6-luna'


@pytest.mark.usefixtures('models')
async def test_without_the_price_list_the_table_waits_for_the_next_look(
    client: AsyncClient, app: FastAPI, session: AsyncSession, me
):
    table = await start_with(client, me, narration_model='gpt-6-luna')
    await retire(session, 'gpt-6-luna', TODAY)
    prices = app.state.price_list
    app.state.price_list = FixedPrices(prices.fixed, error=PriceListUnavailable('unreachable'))

    await tick(app, NOW)
    app.state.price_list = prices
    await tick(app, NOW + timedelta(hours=1))

    # 값을 모르면 대신 쓸 모델을 고르지 않는다. 다음 바퀴에 바꾼다
    assert len(await events_of(client, me, table, 'narration_model_replaced')) == 1
    assert await events_of(client, me, table, 'narration_model_unavailable') == []


# --- 라운드가 열린 뒤 ---


@pytest.mark.usefixtures('models')
async def test_starting_a_table_replaces_a_retired_model(client: AsyncClient, app: FastAPI, session, me):
    created = (await open_with(client, me, capacity=1, narration_model='gpt-6-luna')).json()
    await client.put(table_url(created, '/character'), json={'name': '캐릭터'}, headers=me)
    await retire(session, 'gpt-6-luna', TODAY)

    started = await client.post(table_url(created, '/start'), headers=me)

    # 작업이 아직 돌지 않았어도 첫 라운드가 은퇴한 모델로 가지 않는다
    assert started.json()['narration_model'] == 'gpt-6-mini'
    assert (await current(client, me, created))['narration_model'] == 'gpt-6-mini'


@pytest.mark.usefixtures('models')
async def test_the_next_round_after_narration_is_checked(client: AsyncClient, app: FastAPI, session, me, narrated):
    table = await start_with(client, me, narration_model='gpt-6-luna')
    # 1 라운드를 서술하는 사이에 은퇴했다고 본다. 서술은 연 때의 모델로 했다
    await session.execute(text("UPDATE ai_models SET retires_on = :day WHERE slug = 'gpt-6-luna'"), {'day': TODAY})
    await session.commit()

    await declare(client, me, table, '크게 웃는다.')
    await narrated()

    second = await current(client, me, table)
    assert (second['number'], second['narration_model']) == (2, 'gpt-6-mini')


# --- 고를 수 있는 모델의 목록 ---


@pytest.mark.usefixtures('models')
async def test_the_model_list_shows_the_retirement_day(client: AsyncClient, session: AsyncSession, me):
    await retire(session, 'gpt-6-luna', TODAY + timedelta(days=40))

    models = {model['slug']: model for model in (await client.get(MODELS_URL, headers=me)).json()['models']}

    assert models['gpt-6-luna']['retires_on'] == '2026-11-27'
    assert models['gpt-6-mini']['retires_on'] is None
    assert models['gpt-6-mini']['tier'] == Tier.STANDARD
