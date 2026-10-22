# trpg-server/tests/test_recommended_model.py

"""
시나리오의 추천 서술 모델(app/assets/scenarios/recommended_model.py)과 대신 쓸 모델(app/catalog/offers.py),
테이블을 만들 때 모델을 정하는 것(app/tables/model_choice.py)을 검증한다.

보는 것.
  - 대신 쓸 모델: 운영자가 정한 회사의 대체 모델이 먼저, 없으면 같은 회사의 standard 중 가장 싼 모델.
    다른 회사, standard 가 아닌 모델, 지금 고를 수 없는 모델은 고르지 않는다.
  - 회사의 대체 모델 정하기: 회사마다 하나. 새로 정하면 앞의 것이 풀린다. 은퇴한 모델은 정하지 않는다.
  - 저장: 추천 모델은 반드시 정한다. 서비스 중인 모델만 된다(premium 도). 가격 목록은 보지 않는다.
  - 상태: ok, retiring(은퇴일), unavailable 과 대신 쓸 모델. 작성자 화면이 이것으로 알린다.
  - 테이블: 고르지 않으면 추천 모델. 쓸 수 없으면 대신 쓸 모델로 만들고 이벤트에 둘 다 남긴다.
    대신할 모델이 없거나 추천 모델이 없는 옛 시나리오면 방장이 고른다(422).
"""

import uuid
from datetime import UTC, date, datetime

import pytest
from ai_core.catalog_contract import Provider, TokenLimitField
from ai_core.catalog_file import ModelEntry
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.price_list import PriceListUnavailable
from app.billing.prices import FREE_BOOK, Tier
from app.billing.routing import utc_now
from app.catalog import service as catalog
from app.catalog.errors import CatalogConflictError, Conflict
from app.catalog.models import Grade
from app.catalog.offers import OfferedModel, replacement_for
from scripts import models as script
from tests.catalog_rows import put_models, retire
from tests.narration_model import TEST_MODEL
from tests.signing import SigningKey
from tests.test_model_offers import LUNA, OPUS, FixedPrices, add_enabled, book, on_sale
from tests.test_npc_actions import bearer, events_of
from tests.test_tables_api import SCENARIOS_URL, TABLES_URL, publish_scenario

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
NOW = datetime(2026, 10, 18, 3, 0, tzinfo=UTC)
LATER = date(2026, 12, 1)

MINI = ModelEntry(
    slug='gpt-6-mini',
    provider=Provider.OPENAI,
    api_model_id='gpt-6-mini-2026-09-22',
    display_name='GPT-6 Mini',
    vendor='openai',
    grade=Grade.STANDARD,
    token_limit_field=TokenLimitField.MAX_COMPLETION_TOKENS,
)
PRO = ModelEntry(
    slug='gpt-6-pro',
    provider=Provider.OPENAI,
    api_model_id='gpt-6-pro-2026-09-22',
    display_name='GPT-6 Pro',
    vendor='openai',
    grade=Grade.PREMIUM,
    token_limit_field=TokenLimitField.MAX_COMPLETION_TOKENS,
)


def offered(slug: str, vendor: str = 'openai', credits: str | None = '20', tier: Tier | None = Tier.STANDARD, **more):
    """고를 수 있는 모델 하나."""
    grade = more.pop('grade', Grade.STANDARD)
    return OfferedModel(slug, slug, vendor, grade, credits, tier, **more)


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """작성자이자 방장."""
    return bearer(signing_key, ME)


@pytest.fixture
async def openai_models(app: FastAPI, session: AsyncSession, clean_tables) -> None:
    """켜진 OpenAI 모델 셋(Luna, Mini, Pro)과 Anthropic 의 Opus. 결제 서버는 넷 다 판다. 가장 싼 standard 는 Mini 다."""
    for data in (LUNA, MINI, PRO, OPUS):
        await add_enabled(session, data)
    app.state.price_list = FixedPrices(
        book(
            on_sale('gpt-6-luna', '30'),
            on_sale('gpt-6-mini', '10'),
            on_sale('gpt-6-pro', '5', Tier.PREMIUM),
            on_sale('claude-opus-5-5', '8'),
            on_sale(TEST_MODEL, '1'),
        )
    )
    app.dependency_overrides[utc_now] = lambda: NOW


async def disable(session: AsyncSession, slug: str) -> None:
    """모델을 끈다."""
    await catalog.disable_model(session, slug)


async def open_table(client: AsyncClient, me: dict[str, str], scenario: dict, **fields):
    """그 시나리오의 1번 판으로 테이블을 연다. 응답을 그대로 돌려준다."""
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 1, **fields}
    return await client.post(TABLES_URL, json=body, headers=me)


async def read_scenario(client: AsyncClient, me: dict[str, str], scenario: dict) -> dict:
    """시나리오를 다시 읽는다."""
    response = await client.get(f'{SCENARIOS_URL}/{scenario["id"]}', headers=me)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


# --- 대신 쓸 모델 ---


def test_the_operator_fallback_comes_first():
    offers = [offered('gpt-6-mini', credits='10'), offered('gpt-6-luna', credits='30', vendor_fallback=True)]

    # 더 비싸도 운영자가 정한 모델이다
    assert replacement_for(offers, 'openai').slug == 'gpt-6-luna'


def test_without_a_fallback_the_cheapest_standard_of_the_vendor_is_chosen():
    offers = [
        offered('gpt-6-luna', credits='30'),
        offered('gpt-6-mini', credits='10'),
        offered('gpt-6-pro', credits='5', tier=Tier.PREMIUM),
        offered('gpt-6-nano', credits='2', tier=Tier.BASIC),
        offered('claude-haiku-5-5', vendor='anthropic', credits='1'),
    ]

    # premium 과 basic, 다른 회사의 모델은 더 싸도 고르지 않는다
    assert replacement_for(offers, 'openai').slug == 'gpt-6-mini'


def test_the_price_compares_as_a_number_and_ties_go_by_slug():
    offers = [offered('gpt-6-b', credits='9'), offered('gpt-6-c', credits='10'), offered('gpt-6-a', credits='9.0')]

    # 글자로 견주면 '10' 이 '9' 보다 앞선다. 값이 같으면 이름표 순서다
    assert replacement_for(offers, 'openai').slug == 'gpt-6-a'


def test_without_a_billing_server_the_catalog_grade_decides():
    offers = [
        offered('gpt-6-pro', credits=None, tier=None, grade=Grade.PREMIUM),
        offered('gpt-6-mini', credits=None, tier=None),
        offered('gpt-6-luna', credits=None, tier=None),
    ]

    # 값도 등급도 없다. 모델 목록의 분류로 standard 를 고르고 이름표 순서다
    assert replacement_for(offers, 'openai').slug == 'gpt-6-luna'


def test_a_vendor_without_a_standard_has_no_replacement():
    offers = [offered('gpt-6-pro', tier=Tier.PREMIUM), offered('claude-sonnet-5-5', vendor='anthropic')]

    assert replacement_for(offers, 'openai') is None
    assert replacement_for(offers, 'zai') is None


# --- 회사의 대체 모델 정하기 ---


async def test_setting_a_fallback_moves_it_within_the_vendor(session: AsyncSession):
    for data in (LUNA, MINI, OPUS):
        await put_models(session, data)
    await catalog.set_fallback(session, 'claude-opus-5-5', NOW.date())

    await catalog.set_fallback(session, 'gpt-6-luna', NOW.date())
    await catalog.set_fallback(session, 'gpt-6-mini', NOW.date())
    flags = await fallback_flags(session)

    # 회사마다 하나다. 다른 회사의 대체 모델은 그대로다
    assert flags == {'gpt-6-luna': False, 'gpt-6-mini': True, 'claude-opus-5-5': True, TEST_MODEL: False}


async def test_a_retired_model_cannot_be_the_fallback(session: AsyncSession):
    await put_models(session, LUNA)
    await retire(session, 'gpt-6-luna', NOW.date())

    with pytest.raises(CatalogConflictError) as raised:
        await catalog.set_fallback(session, 'gpt-6-luna', NOW.date())

    assert raised.value.reason == Conflict.RETIRED


async def test_clearing_and_moving_vendor_drop_the_flag(session: AsyncSession):
    for data in (LUNA, MINI):
        await put_models(session, data)
    await catalog.set_fallback(session, 'gpt-6-luna', NOW.date())
    await catalog.clear_fallback(session, 'gpt-6-luna')
    await catalog.set_fallback(session, 'gpt-6-mini', NOW.date())

    # 다른 회사로 옮기면 옛 회사의 대체 표시를 들고 가지 않는다
    await put_models(session, MINI.model_copy(update={'vendor': 'other'}))

    assert (await fallback_flags(session))['gpt-6-mini'] is False
    assert (await fallback_flags(session))['gpt-6-luna'] is False


async def test_the_database_allows_one_fallback_per_vendor(session: AsyncSession):
    for data in (LUNA, MINI):
        await put_models(session, data)

    with pytest.raises(IntegrityError):
        await session.execute(text("UPDATE ai_models SET vendor_fallback = true WHERE vendor = 'openai'"))
        await session.commit()


async def test_the_script_sets_and_clears_the_fallback(session: AsyncSession):
    await put_models(session, LUNA)

    set_code, set_lines = await script.execute(
        session, script.build_parser().parse_args(['fallback', 'gpt-6-luna']), NOW.date()
    )
    listed = await script.execute(session, script.build_parser().parse_args(['list']), NOW.date())
    clear_code, clear_lines = await script.execute(
        session, script.build_parser().parse_args(['fallback', 'gpt-6-luna', '--cancel']), NOW.date()
    )

    assert (set_code, set_lines) == (0, ['gpt-6-luna: openai 의 대체 모델로 정했다'])
    assert any(line.startswith('gpt-6-luna') and line.endswith(' 대체') for line in listed[1])
    assert clear_code == 0 and clear_lines[0].startswith('gpt-6-luna: 대체 모델에서 뺐다')


async def fallback_flags(session: AsyncSession) -> dict[str, bool]:
    """이름표마다 대체 모델 표시."""
    session.expire_all()
    rows = await session.execute(text('SELECT slug, vendor_fallback FROM ai_models'))
    return dict(rows.all())


# --- 저장 ---


async def test_a_scenario_needs_a_recommended_model(client: AsyncClient, me: dict[str, str]):
    response = await client.post(SCENARIOS_URL, json={'title': '추천 없음'}, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.usefixtures('openai_models')
@pytest.mark.parametrize('slug', ['not-in-catalog', 'gpt-6-mini'])
async def test_a_model_out_of_service_cannot_be_recommended(
    client: AsyncClient, session: AsyncSession, me: dict[str, str], slug: str
):
    await disable(session, 'gpt-6-mini')

    response = await client.post(SCENARIOS_URL, json={'title': '꺼진 모델', 'narration_model': slug}, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() | {'detail': None} == {'detail': None, 'field': 'narration_model', 'reason': 'not_offered'}


@pytest.mark.usefixtures('openai_models')
async def test_a_retired_model_cannot_be_recommended(client: AsyncClient, session: AsyncSession, me: dict[str, str]):
    await retire(session, 'gpt-6-mini', NOW.date())

    response = await client.post(SCENARIOS_URL, json={'title': '은퇴', 'narration_model': 'gpt-6-mini'}, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.usefixtures('openai_models')
async def test_any_model_in_service_can_be_recommended_even_unsold(
    client: AsyncClient, app: FastAPI, me: dict[str, str]
):
    # 저장할 때는 가격 목록을 보지 않는다. 결제 서버가 내려가 있어도 premium 을 추천할 수 있다
    app.state.price_list = FixedPrices(FREE_BOOK, error=PriceListUnavailable('unreachable'))

    response = await client.post(SCENARIOS_URL, json={'title': '프로', 'narration_model': 'gpt-6-pro'}, headers=me)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert response.json()['narration_model'] == 'gpt-6-pro'
    assert response.json()['narration_model_status'] == {'state': 'ok', 'retires_on': None, 'replacement': None}


@pytest.mark.usefixtures('openai_models')
async def test_an_update_checks_only_a_sent_model(client: AsyncClient, session: AsyncSession, me: dict[str, str]):
    scenario = await publish_scenario(client, me, narration_model='gpt-6-luna')
    url = f'{SCENARIOS_URL}/{scenario["id"]}'
    await disable(session, 'gpt-6-mini')

    unsold = await client.patch(url, json={'narration_model': 'gpt-6-mini'}, headers=me)
    await disable(session, 'gpt-6-luna')
    # 지금 모델이 꺼져도 다른 칸은 고칠 수 있다. 작성자가 알림을 보고 고를 때까지 테이블은 대신 쓸 모델로 만든다
    other = await client.patch(url, json={'title': '새 제목'}, headers=me)
    chosen = await client.patch(url, json={'narration_model': 'claude-opus-5-5'}, headers=me)

    assert unsold.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert other.status_code == status.HTTP_200_OK, other.text
    assert other.json()['narration_model'] == 'gpt-6-luna'
    assert chosen.json()['narration_model'] == 'claude-opus-5-5'


@pytest.mark.usefixtures('openai_models')
async def test_an_old_scenario_needs_a_model_to_be_saved(
    client: AsyncClient, session: AsyncSession, me: dict[str, str]
):
    scenario = await publish_scenario(client, me)
    await clear_recommendation(session, scenario)
    url = f'{SCENARIOS_URL}/{scenario["id"]}'

    without = await client.patch(url, json={'title': '새 제목'}, headers=me)
    with_one = await client.patch(url, json={'title': '새 제목', 'narration_model': 'gpt-6-luna'}, headers=me)

    assert without.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert without.json()['reason'] == 'missing'
    assert with_one.status_code == status.HTTP_200_OK, with_one.text


async def clear_recommendation(session: AsyncSession, scenario: dict) -> None:
    """추천 모델을 비운다. 이 규칙 전에 만든 시나리오와 같다."""
    await session.execute(
        text('UPDATE scenarios SET narration_model = NULL WHERE asset_id = :id'), {'id': uuid.UUID(scenario['id'])}
    )
    await session.commit()


# --- 상태 ---


@pytest.mark.usefixtures('openai_models')
async def test_a_retiring_model_shows_its_day_and_the_replacement(
    client: AsyncClient, session: AsyncSession, me: dict[str, str]
):
    scenario = await publish_scenario(client, me, narration_model='gpt-6-mini')
    await retire(session, 'gpt-6-mini', LATER)

    found = await read_scenario(client, me, scenario)

    # 은퇴할 모델 자신은 빼고 고른다. 남은 standard 중 가장 싼 Luna 다
    assert found['narration_model_status'] == {
        'state': 'retiring',
        'retires_on': LATER.isoformat(),
        'replacement': 'gpt-6-luna',
    }


@pytest.mark.usefixtures('openai_models')
async def test_an_unavailable_model_shows_the_replacement(
    client: AsyncClient, session: AsyncSession, me: dict[str, str]
):
    scenario = await publish_scenario(client, me, narration_model='gpt-6-luna')
    await disable(session, 'gpt-6-luna')

    found = await read_scenario(client, me, scenario)

    assert found['narration_model_status'] == {'state': 'unavailable', 'retires_on': None, 'replacement': 'gpt-6-mini'}


@pytest.mark.usefixtures('openai_models')
async def test_the_status_survives_a_missing_price_list(client: AsyncClient, app: FastAPI, session: AsyncSession, me):
    scenario = await publish_scenario(client, me, narration_model='gpt-6-luna')
    await disable(session, 'gpt-6-luna')
    app.state.price_list = FixedPrices(FREE_BOOK, error=PriceListUnavailable('unreachable'))

    found = await read_scenario(client, me, scenario)

    # 알리는 것은 그대로다. 대신 쓸 모델만 비운다. 테이블을 만들 때 다시 정한다
    assert found['narration_model_status'] == {'state': 'unavailable', 'retires_on': None, 'replacement': None}


@pytest.mark.usefixtures('openai_models')
async def test_a_model_removed_from_the_catalog_has_no_replacement(
    client: AsyncClient, session: AsyncSession, me: dict[str, str]
):
    scenario = await publish_scenario(client, me, narration_model='gpt-6-luna')
    await session.execute(text("DELETE FROM ai_model_costs WHERE model_slug = 'gpt-6-luna'"))
    await session.execute(text("DELETE FROM ai_models WHERE slug = 'gpt-6-luna'"))
    await session.commit()

    found = await read_scenario(client, me, scenario)

    # 회사를 알 수 없다
    assert found['narration_model_status'] == {'state': 'unavailable', 'retires_on': None, 'replacement': None}


@pytest.mark.usefixtures('openai_models')
async def test_an_old_scenario_has_no_status(client: AsyncClient, session: AsyncSession, me: dict[str, str]):
    scenario = await publish_scenario(client, me)
    await clear_recommendation(session, scenario)

    found = await read_scenario(client, me, scenario)

    assert (found['narration_model'], found['narration_model_status']) == (None, None)


# --- 테이블 ---


@pytest.mark.usefixtures('openai_models')
async def test_the_table_takes_the_recommended_model(client: AsyncClient, me: dict[str, str]):
    scenario = await publish_scenario(client, me, narration_model='gpt-6-luna')

    response = await open_table(client, me, scenario)
    (created,) = await events_of(client, me, response.json(), 'table_created')

    assert response.json()['narration_model'] == 'gpt-6-luna'
    assert created['payload'] == {'narration_model': 'gpt-6-luna', 'recommended_model': 'gpt-6-luna'}


@pytest.mark.usefixtures('openai_models')
async def test_the_recommendation_changes_new_tables_without_publishing(client: AsyncClient, me: dict[str, str]):
    scenario = await publish_scenario(client, me, narration_model='gpt-6-luna')
    await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'narration_model': 'claude-opus-5-5'}, headers=me)

    response = await open_table(client, me, scenario)

    # 판에 굳히지 않는다. 다시 게시하지 않아도 새 테이블은 바꾼 모델이다
    assert response.json()['narration_model'] == 'claude-opus-5-5'


@pytest.mark.usefixtures('openai_models')
async def test_an_unsold_recommendation_is_replaced_and_recorded(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    scenario = await publish_scenario(client, me, narration_model='gpt-6-luna')
    app.state.price_list = FixedPrices(book(on_sale('gpt-6-mini', '10'), on_sale('gpt-6-pro', '5', Tier.PREMIUM)))

    response = await open_table(client, me, scenario)
    (created,) = await events_of(client, me, response.json(), 'table_created')

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert response.json()['narration_model'] == 'gpt-6-mini'
    # 방장이 바뀐 것을 안다. 몰래 바꾸지 않는다
    assert created['payload'] == {'narration_model': 'gpt-6-mini', 'recommended_model': 'gpt-6-luna'}


@pytest.mark.usefixtures('openai_models')
async def test_a_retired_recommendation_uses_the_operator_fallback(
    client: AsyncClient, session: AsyncSession, me: dict[str, str]
):
    scenario = await publish_scenario(client, me, narration_model='gpt-6-mini')
    await catalog.set_fallback(session, 'gpt-6-luna', NOW.date())
    await retire(session, 'gpt-6-mini', NOW.date())

    response = await open_table(client, me, scenario)

    # 더 싼 standard 가 없어도 운영자가 정한 Luna 다
    assert response.json()['narration_model'] == 'gpt-6-luna'


@pytest.mark.usefixtures('openai_models')
async def test_without_a_replacement_the_host_picks(client: AsyncClient, session: AsyncSession, me: dict[str, str]):
    scenario = await publish_scenario(client, me, narration_model='gpt-6-luna')
    for slug in ('gpt-6-luna', 'gpt-6-mini'):
        await disable(session, slug)

    refused = await open_table(client, me, scenario)
    picked = await open_table(client, me, scenario, narration_model='claude-opus-5-5')

    # 같은 회사에 standard 가 없다(Pro 는 premium). 다른 회사로 넘기지 않는다
    assert refused.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'narration_model' in refused.json()['detail']
    assert picked.status_code == status.HTTP_201_CREATED, picked.text


@pytest.mark.usefixtures('openai_models')
async def test_an_old_scenario_needs_the_host_to_pick(client: AsyncClient, session: AsyncSession, me: dict[str, str]):
    scenario = await publish_scenario(client, me)
    await clear_recommendation(session, scenario)

    refused = await open_table(client, me, scenario)
    picked = await open_table(client, me, scenario, narration_model='gpt-6-luna')
    (created,) = await events_of(client, me, picked.json(), 'table_created')

    assert refused.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert created['payload'] == {'narration_model': 'gpt-6-luna', 'recommended_model': None}


@pytest.mark.usefixtures('openai_models')
async def test_the_host_pick_wins_over_the_recommendation(client: AsyncClient, me: dict[str, str]):
    scenario = await publish_scenario(client, me, narration_model='gpt-6-luna')

    response = await open_table(client, me, scenario, narration_model='gpt-6-pro')
    (created,) = await events_of(client, me, response.json(), 'table_created')

    assert response.json()['narration_model'] == 'gpt-6-pro'
    assert created['payload'] == {'narration_model': 'gpt-6-pro', 'recommended_model': 'gpt-6-luna'}
