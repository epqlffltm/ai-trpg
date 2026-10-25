# story-server/tests/test_session_models.py

"""
세션의 모델(app/catalog/router.py, app/conversations/ 의 모델 고르기)을 검증한다. 실제 DB(story_test)에서 돌고,
asset 서버는 가짜다(tests/assets.py). 모델은 들여오기(tests/catalog_rows.py)로 넣고 켠다.

"지금"은 테스트가 정한다(utc_now 를 바꿔 끼운다). 은퇴일을 오늘에 맞춰 시험한다.
값과 판매는 아직 없다(결제를 붙이는 PR).

보는 것.
  - 모델 목록: 켜져 있고 은퇴하지 않은 모델만, 운영의 칸(창구, 원가) 없이. 로그인을 요구한다
  - 시작: 고른 모델을 쓴다. 고를 수 없으면(없다, 꺼졌다, 은퇴했다, 성인 세션에 안 된다) 422 이고
    아무것도 저장하지 않는다.
    null 이면 없이, 보내지 않으면 지난번 세션의 것. 지난번 것을 쓸 수 없으면 없이 시작한다
  - 읽기와 목록: 세션의 모델과 지금도 고를 수 있나(usable)를 싣는다. 끝난 모델을 몰래 바꾸지 않는다
  - 바꾸기: 고를 수 있는 모델로만. 남의 세션는 404. 목록의 차례(최근의 것부터)는 그대로다
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from ai_core.catalog_contract import Grade, Provider, TokenLimitField
from ai_core.catalog_file import CostEntry, ModelEntry
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import service as catalog
from app.conversations.models import Conversation
from app.core.dependencies import utc_now
from app.main import API_PREFIX
from app.ratings import Rating
from tests.assets import FakeAsset, make_world
from tests.catalog_rows import add_cost, put_models, retire

pytestmark = pytest.mark.usefixtures('clean_tables')

MODELS_URL = f'{API_PREFIX}/models'
CONVERSATIONS_URL = f'{API_PREFIX}/conversations'
NOW = datetime(2026, 10, 17, 12, tzinfo=UTC)
TODAY = NOW.date()
ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')


def model_entry(slug: str, vendor: str = 'openai', grade: Grade = Grade.STANDARD) -> ModelEntry:
    """OpenAI 창구로 부르는 모델 하나. API 모델 이름은 지어낸 것이다."""
    return ModelEntry(
        slug=slug,
        provider=Provider.OPENAI,
        api_model_id=f'{slug}-2026-09-22',
        display_name=slug.upper(),
        vendor=vendor,
        grade=grade,
        token_limit_field=TokenLimitField.MAX_COMPLETION_TOKENS,
    )


LUNA = model_entry('luna')
SOL = model_entry('sol', grade=Grade.PREMIUM)
NOVA = model_entry('nova', vendor='xai')


def bearer(signing_key: SigningKey, user_id: uuid.UUID = ME, adult: bool = False) -> dict[str, str]:
    claims = make_access_claims(sub=str(user_id))
    if adult:
        claims['adult_content'] = True
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


@pytest.fixture(autouse=True)
def fixed_today(app: FastAPI) -> Iterator[None]:
    """API 가 보는 "지금"을 NOW 로 둔다."""
    app.dependency_overrides[utc_now] = lambda: NOW
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def my_adult(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, adult=True)


@pytest.fixture
def theirs(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, SOMEONE_ELSE)


@pytest.fixture
async def offered(clean_tables: None, session: AsyncSession) -> None:
    """LUNA, SOL, NOVA 를 들여와 켠다. NOVA 만 성인 등급의 세션에 쓴다. 표를 비운 뒤에 넣는다(clean_tables)."""
    await put_models(session, LUNA, SOL, NOVA)
    for entry in (LUNA, SOL, NOVA):
        cost = CostEntry(
            input_per_mtok=Decimal('1'), output_per_mtok=Decimal('5'), effective_from=TODAY, checked_on=TODAY
        )
        await add_cost(session, entry.slug, cost)
        await catalog.enable_model(session, entry.slug, TODAY)
    await catalog.allow_adult(session, 'nova')


async def start(client: AsyncClient, asset: FakeAsset, headers: dict, rating: Rating = Rating.ALL, **body) -> dict:
    world = asset.add_world(make_world(rating=rating))
    response = await client.post(CONVERSATIONS_URL, json={'world_id': str(world.id), **body}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def read(client: AsyncClient, headers: dict, conversation: dict) -> dict:
    response = await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def change(client: AsyncClient, headers: dict, conversation: dict, model: str):
    return await client.put(f'{CONVERSATIONS_URL}/{conversation["id"]}/model', json={'model': model}, headers=headers)


async def slug_of(client: AsyncClient, headers: dict, conversation: dict) -> str | None:
    model = (await read(client, headers, conversation))['model']
    return model and model['slug']


# --- 오늘 ---


def test_now_is_in_utc():
    # 은퇴일과 원가의 날을 UTC 로 본다. 관리 명령, chat 서버와 같다
    now = utc_now()

    assert now.utcoffset() == timedelta(0)
    assert abs(now - datetime.now(UTC)) < timedelta(minutes=1)


# --- 모델 목록 ---


async def test_the_model_list_needs_login(client: AsyncClient):
    response = await client.get(MODELS_URL)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_the_model_list_has_only_offered_models(client: AsyncClient, session: AsyncSession, mine: dict):
    await put_models(session, LUNA, SOL, NOVA)
    await add_cost(
        session, 'luna', CostEntry(input_per_mtok=1, output_per_mtok=5, effective_from=TODAY, checked_on=TODAY)
    )
    await add_cost(
        session, 'nova', CostEntry(input_per_mtok=1, output_per_mtok=5, effective_from=TODAY, checked_on=TODAY)
    )
    await catalog.enable_model(session, 'luna', TODAY)
    await catalog.enable_model(session, 'nova', TODAY)
    await catalog.allow_adult(session, 'nova')
    await retire(session, 'luna', TODAY + timedelta(days=45))

    response = await client.get(MODELS_URL, headers=mine)

    # 꺼진 SOL 은 없다. 회사, 이름표 순서다. 창구, API 모델 이름, 원가는 싣지 않는다
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        'items': [
            {
                'slug': 'luna',
                'display_name': 'LUNA',
                'vendor': 'openai',
                'grade': 'standard',
                'allows_adult': False,
                'retires_on': '2026-12-01',
            },
            {
                'slug': 'nova',
                'display_name': 'NOVA',
                'vendor': 'xai',
                'grade': 'standard',
                'allows_adult': True,
                'retires_on': None,
            },
        ],
    }


async def test_a_retired_model_leaves_the_list_on_its_day(
    client: AsyncClient, session: AsyncSession, offered: None, mine: dict
):
    await retire(session, 'luna', TODAY)

    response = await client.get(MODELS_URL, headers=mine)

    assert [item['slug'] for item in response.json()['items']] == ['sol', 'nova']


# --- 시작 ---


async def test_the_first_conversation_starts_without_a_model(client: AsyncClient, asset: FakeAsset, mine: dict):
    made = await start(client, asset, mine)

    assert made['model'] is None


@pytest.mark.usefixtures('offered')
async def test_a_chosen_model_is_used(client: AsyncClient, asset: FakeAsset, mine: dict):
    made = await start(client, asset, mine, model='sol')

    assert made['model'] == {
        'slug': 'sol',
        'display_name': 'SOL',
        'vendor': 'openai',
        'grade': 'premium',
        'retires_on': None,
        'usable': True,
    }


@pytest.mark.parametrize('model', ['nothing', 'disabled', 'retired'])
async def test_a_model_that_cannot_be_chosen_is_422_and_nothing_is_saved(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, offered: None, mine: dict, model: str
):
    await put_models(session, model_entry('disabled'))
    await put_models(session, model_entry('retired'))
    await add_cost(
        session, 'retired', CostEntry(input_per_mtok=1, output_per_mtok=5, effective_from=TODAY, checked_on=TODAY)
    )
    await catalog.enable_model(session, 'retired', TODAY)
    await retire(session, 'retired', TODAY)
    world = asset.add_world(make_world())

    response = await client.post(CONVERSATIONS_URL, json={'world_id': str(world.id), 'model': model}, headers=mine)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {'detail': '이 세션에 쓸 수 없는 모델입니다.', 'code': 'model_unavailable'}
    assert await session.scalar(select(func.count()).select_from(Conversation)) == 0


@pytest.mark.usefixtures('offered')
async def test_an_adult_conversation_takes_only_an_adult_model(client: AsyncClient, asset: FakeAsset, my_adult: dict):
    world = asset.add_world(make_world(rating=Rating.ADULT))
    body = {'world_id': str(world.id)}

    refused = await client.post(CONVERSATIONS_URL, json={**body, 'model': 'luna'}, headers=my_adult)
    made = await client.post(CONVERSATIONS_URL, json={**body, 'model': 'nova'}, headers=my_adult)

    assert refused.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert made.json()['model']['slug'] == 'nova'


@pytest.mark.parametrize('model', ['', 'x' * 49])
async def test_a_malformed_model_is_refused(client: AsyncClient, asset: FakeAsset, mine: dict, model: str):
    world = asset.add_world(make_world())

    response = await client.post(CONVERSATIONS_URL, json={'world_id': str(world.id), 'model': model}, headers=mine)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.usefixtures('offered')
async def test_without_a_model_the_last_conversations_model_is_used(
    client: AsyncClient, asset: FakeAsset, mine: dict, theirs: dict
):
    await start(client, asset, mine, model='luna')
    await start(client, asset, mine, model='sol')
    await start(client, asset, theirs, model='nova')

    made = await start(client, asset, mine)

    # 가장 최근에 시작한 세션의 것이다. 남의 세션은 보지 않는다
    assert made['model']['slug'] == 'sol'


@pytest.mark.usefixtures('offered')
async def test_null_starts_without_a_model_even_with_a_last_one(client: AsyncClient, asset: FakeAsset, mine: dict):
    await start(client, asset, mine, model='sol')

    made = await start(client, asset, mine, model=None)

    assert made['model'] is None


@pytest.mark.usefixtures('offered')
async def test_a_last_model_that_was_disabled_is_not_carried_over(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict
):
    await start(client, asset, mine, model='sol')
    await catalog.disable_model(session, 'sol')

    made = await start(client, asset, mine)

    # 고르지 않은 것이라 422 가 아니다. 모델 없이 시작하고 화면이 고르게 한다
    assert made['model'] is None


@pytest.mark.usefixtures('offered')
async def test_a_last_model_unfit_for_an_adult_conversation_is_not_carried_over(
    client: AsyncClient, asset: FakeAsset, my_adult: dict
):
    await start(client, asset, my_adult, model='luna')

    made = await start(client, asset, my_adult, Rating.ADULT)

    assert made['model'] is None


@pytest.mark.usefixtures('offered')
async def test_a_last_model_fit_for_an_adult_conversation_is_carried_over(
    client: AsyncClient, asset: FakeAsset, my_adult: dict
):
    await start(client, asset, my_adult, model='nova')

    made = await start(client, asset, my_adult, Rating.ADULT)

    assert made['model']['slug'] == 'nova'


# --- 읽기와 목록 ---


@pytest.mark.usefixtures('offered')
async def test_a_model_that_ended_stays_and_shows_it_is_not_usable(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict
):
    disabled = await start(client, asset, mine, model='sol')
    retired = await start(client, asset, mine, model='luna')
    await catalog.disable_model(session, 'sol')
    await retire(session, 'luna', TODAY)

    page = (await client.get(CONVERSATIONS_URL, headers=mine)).json()

    # 몰래 다른 모델로 바꾸지 않는다. 가리킨 채로 두고 "더는 쓸 수 없다"를 싣는다
    assert [(item['model']['slug'], item['model']['usable']) for item in page['items']] == [
        ('luna', False),
        ('sol', False),
    ]
    assert (await read(client, mine, disabled))['model']['usable'] is False
    assert (await read(client, mine, retired))['model']['usable'] is False


@pytest.mark.usefixtures('offered')
async def test_forbidding_adult_makes_the_adult_conversations_model_unusable(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, my_adult: dict
):
    adult = await start(client, asset, my_adult, Rating.ADULT, model='nova')
    everyone = await start(client, asset, my_adult, model='nova')
    await catalog.forbid_adult(session, 'nova')

    # 전체 이용가의 세션에는 그대로 쓴다
    assert (await read(client, my_adult, adult))['model']['usable'] is False
    assert (await read(client, my_adult, everyone))['model']['usable'] is True


async def test_a_conversation_without_a_model_lists_none(client: AsyncClient, asset: FakeAsset, mine: dict):
    await start(client, asset, mine)

    page = (await client.get(CONVERSATIONS_URL, headers=mine)).json()

    assert page['items'][0]['model'] is None


# --- 바꾸기 ---


@pytest.mark.usefixtures('offered')
async def test_the_model_is_changed(client: AsyncClient, asset: FakeAsset, mine: dict):
    made = await start(client, asset, mine)

    response = await change(client, mine, made, 'sol')

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        'slug': 'sol',
        'display_name': 'SOL',
        'vendor': 'openai',
        'grade': 'premium',
        'retires_on': None,
        'usable': True,
    }
    assert await slug_of(client, mine, made) == 'sol'


@pytest.mark.usefixtures('offered')
async def test_changing_the_model_keeps_the_list_order(client: AsyncClient, asset: FakeAsset, mine: dict):
    older = await start(client, asset, mine, model='luna')
    newer = await start(client, asset, mine, model='luna')

    await change(client, mine, older, 'sol')
    page = (await client.get(CONVERSATIONS_URL, headers=mine)).json()

    # 목록은 최근의 것부터다. 모델을 바꿨다고 앞으로 오지 않는다
    assert [item['id'] for item in page['items']] == [newer['id'], older['id']]
    assert page['items'][1]['updated_at'] == older['updated_at']


@pytest.mark.parametrize('model', ['nothing', 'luna'])
async def test_changing_to_a_model_that_cannot_be_chosen_is_422(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, offered: None, my_adult: dict, model: str
):
    made = await start(client, asset, my_adult, Rating.ADULT, model='nova')

    response = await change(client, my_adult, made, model)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['code'] == 'model_unavailable'
    assert await slug_of(client, my_adult, made) == 'nova'


@pytest.mark.usefixtures('offered')
async def test_someone_elses_conversation_is_404(client: AsyncClient, asset: FakeAsset, mine: dict, theirs: dict):
    made = await start(client, asset, mine, model='luna')

    response = await change(client, theirs, made, 'sol')

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert await slug_of(client, mine, made) == 'luna'


async def test_changing_needs_login(client: AsyncClient):
    response = await client.put(f'{CONVERSATIONS_URL}/{uuid.uuid4()}/model', json={'model': 'luna'})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.parametrize('body', [{}, {'model': None}, {'model': 'luna', 'owner_id': str(ME)}])
async def test_a_malformed_change_is_refused(client: AsyncClient, asset: FakeAsset, mine: dict, body: dict):
    made = await start(client, asset, mine)

    response = await client.put(f'{CONVERSATIONS_URL}/{made["id"]}/model', json=body, headers=mine)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
