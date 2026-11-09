# story-server/tests/test_achievements_api.py

"""
업적(docs/architecture/achievements.md 의 "story")을 API 로 검증한다. 실제 DB(story_test)에서 돈다.
asset 서버, 결제 서버, 모델은 가짜다(tests/assets.py, tests/billing.py, tests/models.py).

보는 것.
  - 행동 뒤에 조건이 맞으면 업적을 받는다. turn 메시지에 실리고,
    계정의 기록(GET /achievements)에 받은 세션과 함께 남는다
  - 다시 채워도, 다른 세션에서 채워도 다시 주지 않는다. 숨긴 업적도 받은 사람에게는 이름이 보인다
  - 엔딩에 닿은 행동에 "그 엔딩을 봤다" 업적을 받는다
  - 말이나 행동을 보낸 사람이 플레이한 사람이다. 달성률(GET /achievements/rates)은 로그인하지 않아도 본다
  - 업적이 없는 판에서도 플레이한 사람으로 센다. 업적의 기록은 로그인이 있어야 본다
  - 같은 업적을 두 번 적으면 처음 것만 남고 두 번째는 새로 적힌 것이 없다.
    다른 세션이 먼저 적은 업적(읽은 뒤에 적혔다)은 이 행동에서 알리지 않는다
"""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.world import Achievement
from app.records import repository
from app.turns import service
from tests.assets import FakeAsset
from tests.billing import FakeBillingServer
from tests.engine_worlds import condition, confession, ending, member
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, ME, PRICE_CODE, bearer, parse_sse, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

ACHIEVEMENTS_URL = CONVERSATIONS_URL.replace('/conversations', '/achievements')
RATES_URL = f'{ACHIEVEMENTS_URL}/rates'
PICTURE = uuid.UUID('aaaaaaaa-1111-4222-8333-444444444444')
PATHS = [{'a': 'home', 'b': 'beach', 'minutes': 30}]


def achievement(achievement_id: str, *items: dict, **fields) -> dict:
    """업적 하나. 조건은 items 다."""
    return {
        'id': achievement_id,
        'name': f'{achievement_id} 업적',
        'description': f'{achievement_id} 을 했다',
        'hidden': False,
        'image_id': None,
        'when': {'match': 'all', 'items': list(items)},
        **fields,
    }


BEACH = achievement('beach', condition('reach_place', 'beach'), image_id=str(PICTURE))
SECRET = achievement('secret', condition('reach_place', 'beach'), hidden=True)


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter()
    app.state.model_router = fake
    return fake


@pytest.fixture
def billing(app: FastAPI) -> FakeBillingServer:
    server = FakeBillingServer(balances={ME: 100})
    server.prices[PRICE_CODE] = 30
    app.state.billing = server.billing(server.make_client())
    return server


@pytest.fixture
async def model_on(clean_tables: None, session: AsyncSession) -> None:
    await turn_on_luna(session)


async def finished(app: FastAPI) -> None:
    await asyncio.gather(*list(app.state.turns))


async def acted(app: FastAPI, client: AsyncClient, headers: dict, conversation: dict, body: dict) -> dict:
    """행동 하나를 보내고 turn 메시지를 돌려준다."""
    response = await client.post(f'{CONVERSATIONS_URL}/{conversation["id"]}/actions', json=body, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await finished(app)
    return parse_sse(response.text)[0][1]


async def world_of(client: AsyncClient, headers: dict, conversation: dict) -> str:
    detail = await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)
    return detail.json()['world']['id']


async def mine_of(client: AsyncClient, headers: dict, world_id: str) -> list[dict]:
    return (await client.get(ACHIEVEMENTS_URL, params={'world_id': world_id}, headers=headers)).json()['items']


async def rates_of(client: AsyncClient, world_id: str) -> dict:
    response = await client.get(RATES_URL, params={'world_id': world_id})
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def test_an_action_that_meets_the_conditions_gives_the_achievement_once(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start_with_luna(client, asset, mine, {'paths': PATHS, 'achievements': [BEACH], 'format': 9})

    turn = await acted(app, client, mine, conversation, {'kind': 'move', 'place': 'beach'})

    assert turn['achievements'] == [
        {'id': 'beach', 'name': 'beach 업적', 'description': 'beach 을 했다', 'image_id': str(PICTURE)}
    ]
    world_id = await world_of(client, mine, conversation)
    records = await mine_of(client, mine, world_id)
    assert [(one['achievement_id'], one['name'], one['image_id'], one['conversation_id']) for one in records] == [
        ('beach', 'beach 업적', str(PICTURE), conversation['id'])
    ]
    assert await rates_of(client, world_id) == {'players': 1, 'items': [{'achievement_id': 'beach', 'earned_count': 1}]}
    # 집에 갔다가 다시 해변에 가도 다시 받지 않는다
    await acted(app, client, mine, conversation, {'kind': 'move', 'place': 'home'})
    again = await acted(app, client, mine, conversation, {'kind': 'move', 'place': 'beach'})
    assert again['achievements'] == []
    assert len(await mine_of(client, mine, world_id)) == 1


async def test_another_session_of_the_same_world_does_not_give_it_again(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    first = await start_with_luna(client, asset, mine, {'paths': PATHS, 'achievements': [SECRET]})
    await acted(app, client, mine, first, {'kind': 'move', 'place': 'beach'})
    world_id = await world_of(client, mine, first)
    body = {'world_id': world_id, 'model': 'luna'}
    second = (await client.post(CONVERSATIONS_URL, json=body, headers=mine)).json()

    turn = await acted(app, client, mine, second, {'kind': 'move', 'place': 'beach'})

    assert turn['achievements'] == []
    # 숨긴 업적도 받은 사람의 기록에는 이름과 받는 법이 있다. 처음 받은 세션이 남는다
    records = await mine_of(client, mine, world_id)
    assert [(one['achievement_id'], one['name'], one['description'], one['conversation_id']) for one in records] == [
        ('secret', 'secret 업적', 'secret 을 했다', first['id'])
    ]


async def test_the_action_that_reaches_an_ending_gives_the_ending_achievement(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    mina = {**member('mina', home='home', start=80, confession=confession('연인')), 'character': {'name': '미나'}}
    fields = {
        'cast': [mina],
        'endings': [ending('with_mina', 'confess_success', 'mina')],
        'achievements': [achievement('lover', condition('ending_seen', 'with_mina'))],
    }
    conversation = await start_with_luna(client, asset, mine, fields)

    turn = await acted(app, client, mine, conversation, {'kind': 'confess', 'cast': 'mina'})

    assert (turn['state']['ending'], [one['id'] for one in turn['achievements']]) == ('with_mina', ['lover'])


async def test_talking_counts_as_playing_even_without_achievements(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start_with_luna(client, asset, mine)
    world_id = await world_of(client, mine, conversation)
    assert await rates_of(client, world_id) == {'players': 0, 'items': []}

    response = await client.post(
        f'{CONVERSATIONS_URL}/{conversation["id"]}/messages', json={'content': '안녕'}, headers=mine
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    await finished(app)

    assert await rates_of(client, world_id) == {'players': 1, 'items': []}
    assert await mine_of(client, mine, world_id) == []


async def test_my_achievements_need_login_but_rates_do_not(client: AsyncClient):
    world_id = str(uuid.uuid4())

    mine = await client.get(ACHIEVEMENTS_URL, params={'world_id': world_id})
    rates = await client.get(RATES_URL, params={'world_id': world_id})

    assert mine.status_code == status.HTTP_401_UNAUTHORIZED
    assert (rates.status_code, rates.json()) == (status.HTTP_200_OK, {'players': 0, 'items': []})


async def test_writing_the_same_achievement_twice_keeps_the_first(session: AsyncSession):
    owner, world = uuid.uuid4(), uuid.uuid4()
    first = Achievement(id='beach', name='처음 이름')
    later = Achievement(id='beach', name='바뀐 이름')
    now = datetime(2026, 11, 9, tzinfo=UTC)

    added = await repository.add_achievements(session, owner, world, [first], None, now)
    again = await repository.add_achievements(session, owner, world, [later], None, now)
    await session.commit()

    assert (added, again) == (frozenset({'beach'}), frozenset())
    assert [record.name for record in await repository.achievements_of(session, owner, world)] == ['처음 이름']
    assert await repository.add_achievements(session, owner, world, [], None, now) == frozenset()


async def test_an_achievement_another_session_wrote_first_is_not_announced(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    mine: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    conversation = await start_with_luna(client, asset, mine, {'paths': PATHS, 'achievements': [BEACH]})
    world_id = uuid.UUID(await world_of(client, mine, conversation))
    await repository.add_achievements(
        session, ME, world_id, [Achievement(id='beach', name='먼저')], None, datetime.now(UTC)
    )
    await session.commit()

    # 받은 것을 읽은 뒤에 다른 세션이 적은 것과 같다. 이 행동은 받은 것이 없다고 읽는다
    async def nothing_owned(*_args) -> frozenset[str]:
        return frozenset()

    monkeypatch.setattr(service.records, 'achievement_ids_of', nothing_owned)
    turn = await acted(app, client, mine, conversation, {'kind': 'move', 'place': 'beach'})

    assert turn['achievements'] == []
    assert [one['name'] for one in await mine_of(client, mine, str(world_id))] == ['먼저']
