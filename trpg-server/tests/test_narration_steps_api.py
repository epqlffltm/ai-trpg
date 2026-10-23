# trpg-server/tests/test_narration_steps_api.py

"""
방장이 서술의 입력·출력 단계(#387)를 고르는 것을 API 로 검증한다. 예산과 길이는 tests/test_narration_steps.py 가 본다.

보는 것.
  - 목록: 모델마다 지금 파는 단계와 그 값(options)이 나온다. 기본 단계가 맨 앞이다.
  - 만들 때: 단계를 고른다. 적지 않으면 0, 0 이다. 그 모델이 팔지 않는 단계면 422(narration_steps)다.
  - 바꾸기: 모델과 함께 바꾼다. 모집 중에는 바꾼다. 시작한 뒤에는 지금 쓰는 단계를 쓸 수 없을 때만 바꾼다.
  - 라운드에 굳기: 열 때의 단계의 가격표로 걸고, 서술자는 그 단계를 받는다.
  - 작가의 글: 입력 단계가 높으면 더 긴 작가의 글로도 시작한다.
  - 은퇴: 대신 쓸 모델은 테이블의 단계를 팔아야 하고, 단계는 그대로다. 단계를 바꿔 가며 대신하지 않는다.
"""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import WORLD_GM_NOTES_MAX_LENGTH, WORLD_SETTING_MAX_LENGTH
from app.billing.prices import FREE_BOOK, Price, PriceBook, Sale, Tier, narration_code
from app.billing.routing import utc_now
from app.catalog.steps import BASE_STEPS, NarrationSteps
from tests.billing import PRICES, FakeBillingServer
from tests.catalog_rows import retire
from tests.test_model_offers import LUNA, MODELS_URL, OPUS, FixedPrices, add_enabled
from tests.test_model_retirement import tick as watch_tick
from tests.test_narration_billing import charges_of, tick
from tests.test_narration_model_pick import RecordingNarrator, close_solo
from tests.test_npc_actions import bearer, events_of, table_url
from tests.test_recommended_model import MINI
from tests.test_round_time_limit import current, open_with, start_with
from tests.test_tables_api import TABLES_URL, WORLDS_URL, publish_scenario, set_character

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
NOW = datetime(2026, 10, 23, 3, 0, tzinfo=UTC)

LONG = NarrationSteps(1, 2)


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장."""
    return bearer(signing_key, ME)


def sold(slug: str, steps: NarrationSteps, credits: str) -> Price:
    return Price(code=narration_code(slug, steps), current=Sale(credits, Tier.STANDARD))


def selling(*prices: Price) -> FixedPrices:
    """그 가격표만 파는 가격 목록."""
    return FixedPrices(PriceBook(prices={price.code: price for price in prices}))


# Luna 는 기본 단계(20)와 입력 1·출력 2 단계(70)를 판다. Opus 는 기본 단계(60)만 판다
LUNA_BASE = sold('gpt-6-luna', BASE_STEPS, '20')
LUNA_LONG = sold('gpt-6-luna', LONG, '70')
OPUS_BASE = sold('claude-opus-5-5', BASE_STEPS, '60')


@pytest.fixture(autouse=True)
async def models(app: FastAPI, session: AsyncSession, clean_tables) -> None:
    """켜진 모델 둘(Luna, Opus)과, Luna 만 긴 단계를 파는 가격 목록."""
    await add_enabled(session, LUNA)
    await add_enabled(session, OPUS)
    app.state.price_list = selling(LUNA_BASE, LUNA_LONG, OPUS_BASE)
    app.dependency_overrides[utc_now] = lambda: NOW


@pytest.fixture
def recording(app: FastAPI) -> RecordingNarrator:
    """앱에 꽂은, 받은 요청을 적는 서술자."""
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    return narrator


@pytest.fixture
async def billing(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> FakeBillingServer:
    """앱에 꽂은 가짜 결제 서버. 방장에게 1000 크레딧이 있다. Luna 의 두 단계를 판다."""
    monkeypatch.setitem(PRICES, LUNA_BASE.code, 20)
    monkeypatch.setitem(PRICES, LUNA_LONG.code, 70)
    server = FakeBillingServer(balances={ME: 1000})
    client = server.make_client()
    app.state.billing = server.billing(client)
    yield server
    await client.aclose()


async def set_choice(client: AsyncClient, headers: dict, table: dict, model: str, steps: NarrationSteps):
    """서술 모델과 단계를 바꾼다. 응답을 그대로 돌려준다."""
    body = {'narration_model': model, 'input_step': steps.input, 'output_step': steps.output}
    return await client.put(table_url(table, '/narration-model'), json=body, headers=headers)


def steps_in(body: dict) -> NarrationSteps:
    return NarrationSteps(body['input_step'], body['output_step'])


# --- 목록 ---


async def test_each_model_lists_the_steps_on_sale(client: AsyncClient, me: dict[str, str]):
    response = await client.get(MODELS_URL, headers=me)

    assert response.status_code == status.HTTP_200_OK, response.text
    models = {model['slug']: model for model in response.json()['models']}
    luna = models['gpt-6-luna']['options']
    assert [(item['input_step'], item['output_step'], item['credits']) for item in luna] == [(0, 0, '20'), (1, 2, '70')]
    assert (luna[1]['input_tokens'], luna[1]['output_tokens']) == (20_000, 3_200)
    assert [(item['input_step'], item['output_step']) for item in models['claude-opus-5-5']['options']] == [(0, 0)]


async def test_without_a_billing_server_every_step_is_listed(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    app.state.price_list = FixedPrices(FREE_BOOK)

    response = await client.get(MODELS_URL, headers=me)

    options = response.json()['models'][0]['options']
    assert len(options) == 9
    assert all(item['credits'] is None for item in options)


# --- 만들 때 ---


async def test_a_table_is_made_on_the_base_step_by_default(client: AsyncClient, me: dict[str, str]):
    response = await open_with(client, me, narration_model='gpt-6-luna')

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert steps_in(response.json()) == BASE_STEPS


async def test_a_table_is_made_on_a_step_on_sale(client: AsyncClient, me: dict[str, str]):
    response = await open_with(client, me, narration_model='gpt-6-luna', input_step=1, output_step=2)
    (created,) = await events_of(client, me, response.json(), 'table_created')

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert steps_in(response.json()) == LONG
    assert steps_in(created['payload']) == LONG


@pytest.mark.parametrize(
    ('model', 'steps', 'field'),
    [
        # Opus 는 기본 단계만 판다
        ('claude-opus-5-5', LONG, 'narration_steps'),
        # Luna 도 입력 2 단계는 팔지 않는다
        ('gpt-6-luna', NarrationSteps(2, 2), 'narration_steps'),
        # 모델을 못 고르면 모델이 먼저다
        ('not-in-catalog', LONG, 'narration_model'),
    ],
)
async def test_a_step_not_on_sale_cannot_be_picked(
    client: AsyncClient, me: dict[str, str], model: str, steps: NarrationSteps, field: str
):
    response = await open_with(client, me, narration_model=model, input_step=steps.input, output_step=steps.output)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert field in response.json()['detail']


@pytest.mark.parametrize('step', [-1, 3])
async def test_a_step_out_of_range_is_refused(client: AsyncClient, me: dict[str, str], step: int):
    response = await open_with(client, me, narration_model='gpt-6-luna', input_step=step)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 바꾸기 ---


async def test_the_host_changes_the_steps_while_recruiting(client: AsyncClient, me: dict[str, str]):
    table = (await open_with(client, me, narration_model='gpt-6-luna')).json()

    response = await set_choice(client, me, table, 'gpt-6-luna', LONG)
    (changed,) = await events_of(client, me, table, 'narration_model_changed')

    assert response.status_code == status.HTTP_200_OK, response.text
    assert steps_in(response.json()) == LONG
    assert changed['payload'] == {
        'narration_model': 'gpt-6-luna',
        'input_step': 1,
        'output_step': 2,
        'round': None,
        'price': None,
    }


async def test_the_steps_are_locked_after_the_start(client: AsyncClient, me: dict[str, str]):
    table = await start_with(client, me, narration_model='gpt-6-luna')

    response = await set_choice(client, me, table, 'gpt-6-luna', LONG)

    # 앉은 사람 모두가 그 값을 보고 앉았다. 방장 혼자 단계를 올리지 못한다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'narration_model_locked'


async def test_steps_no_longer_on_sale_can_be_changed_after_the_start(
    client: AsyncClient, app: FastAPI, me: dict[str, str]
):
    table = await start_with(client, me, narration_model='gpt-6-luna', input_step=1, output_step=2)
    # 긴 단계를 팔지 않게 됐다. 모델은 그대로 판다
    app.state.price_list = selling(LUNA_BASE, OPUS_BASE)

    response = await set_choice(client, me, table, 'gpt-6-luna', BASE_STEPS)

    assert response.status_code == status.HTTP_200_OK, response.text
    assert steps_in(response.json()) == BASE_STEPS
    # 아직 서술하지 않은 지금 라운드도 함께 바뀐다
    assert steps_in(await current(client, me, table)) == BASE_STEPS


# --- 라운드에 굳기 ---


async def test_a_round_holds_the_price_of_its_steps_and_narrates_with_them(
    client: AsyncClient,
    app: FastAPI,
    me: dict[str, str],
    session: AsyncSession,
    billing: FakeBillingServer,
    recording: RecordingNarrator,
    narrated,
):
    table = await start_with(client, me, narration_model='gpt-6-luna', input_step=1, output_step=2)
    await tick(app)
    opened = await current(client, me, table)
    await close_solo(client, me, table, narrated)
    await tick(app)

    charges = await charges_of(session, table)

    assert steps_in(opened) == LONG
    assert opened['price']['credits'] == '70'
    assert charges[0].price_code == 'narration.gpt-6-luna.i1.o2'
    assert charges[0].status == 'captured'
    # 1 라운드를 확정했고, 이어 열린 2 라운드도 같은 단계의 값을 걸었다
    assert billing.balance(ME) == 1000 - 2 * 70
    assert recording.requests[0].steps == LONG


# --- 은퇴 ---


async def start_retiring_luna(
    client: AsyncClient, app: FastAPI, session: AsyncSession, me: dict, mini_sells_long: bool
):
    """긴 단계로 시작한 Luna 의 테이블. Luna 가 오늘 은퇴하고, 같은 회사의 Mini 가 있다."""
    await add_enabled(session, MINI)
    mini = [sold('gpt-6-mini', BASE_STEPS, '10')] + ([sold('gpt-6-mini', LONG, '40')] if mini_sells_long else [])
    app.state.price_list = selling(LUNA_BASE, LUNA_LONG, OPUS_BASE, *mini)
    table = await start_with(client, me, narration_model='gpt-6-luna', input_step=1, output_step=2)
    await retire(session, 'gpt-6-luna', NOW.date())
    await watch_tick(app, NOW)
    return table


async def test_a_replacement_keeps_the_steps_of_the_table(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    table = await start_retiring_luna(client, app, session, me, mini_sells_long=True)

    detail = (await client.get(table_url(table), headers=me)).json()

    assert (detail['narration_model'], steps_in(detail)) == ('gpt-6-mini', LONG)
    assert steps_in(await current(client, me, table)) == LONG


async def test_a_model_that_does_not_sell_the_steps_does_not_replace(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    table = await start_retiring_luna(client, app, session, me, mini_sells_long=False)

    # Mini 는 기본 단계만 판다. 단계를 바꿔 가며 대신하지 않고, 방장에게 고르라고 알린다
    (stranded,) = await events_of(client, me, table, 'narration_model_unavailable')
    assert stranded['payload']['narration_model'] == 'gpt-6-luna'
    assert (await client.get(table_url(table), headers=me)).json()['narration_model'] == 'gpt-6-luna'


# --- 작가의 글 ---


async def test_a_long_story_starts_only_on_a_higher_input_step(client: AsyncClient, me: dict[str, str]):
    long_world = {
        'title': '세계관',
        'setting': '가' * WORLD_SETTING_MAX_LENGTH,
        'gm_notes': '나' * WORLD_GM_NOTES_MAX_LENGTH,
    }
    world = (await client.post(WORLDS_URL, json=long_world, headers=me)).json()
    scenario = await publish_scenario(client, me, world_id=world['id'])
    tables = []
    for steps in (BASE_STEPS, LONG):
        body = {
            'scenario_id': scenario['id'],
            'version': 1,
            'capacity': 1,
            'narration_model': 'gpt-6-luna',
            'input_step': steps.input,
            'output_step': steps.output,
        }
        table = (await client.post(TABLES_URL, json=body, headers=me)).json()
        await set_character(client, me, table, pregen_index=0)
        tables.append(table)

    base, long = [await client.post(table_url(table, '/start'), headers=me) for table in tables]

    # 작가의 글이 12,000 토큰을 넘는다. 기본 단계로는 시작하지 못하고, 입력 20,000 토큰의 단계로는 시작한다
    assert base.status_code == status.HTTP_409_CONFLICT
    assert base.json()['reason'] == 'story_too_long'
    assert long.status_code == status.HTTP_200_OK, long.text
