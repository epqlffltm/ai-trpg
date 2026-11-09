# chat-server/tests/test_achievements_api.py

"""
업적(docs/architecture/achievements.md 의 "chat")을 API 로 검증한다. 실제 DB(chat_test)에서 돈다.
asset 서버, 결제 서버, 모델은 가짜다.

보는 것.
  - 답을 저장한 뒤 조건이 맞으면 업적을 받는다. done 메시지에 실리고,
    계정의 기록(GET /achievements)에 받은 대화와 함께 남는다
  - 보낸 말의 수, 행동(이동)으로 받는다. 다시 채워도 다시 주지 않는다. 숨긴 업적도 받은 사람에게는 이름이 보인다
  - 답을 받은 사람이 대화한 사람이다. 달성률(GET /achievements/rates)은 로그인하지 않아도 본다
  - 업적이 없는 판에서도 대화한 사람으로 센다. 업적의 기록은 로그인이 있어야 본다
  - 업적을 보다 실패해도 답은 그대로 끝난다. 같은 업적을 두 번 적으면 처음 것만 남는다.
    다른 대화가 먼저 적은 업적(읽은 뒤에 적혔다)은 이 답에서 알리지 않는다. 지운 대화에는 주지 않는다
"""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy.ext.asyncio import AsyncSession

from app.achievements import repository
from app.achievements import service as achievements_service
from app.assets.schemas import AchievementDocument
from app.main import API_PREFIX
from tests.assets import FakeAsset, make_character
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, ME, bearer, parse_sse, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

ACHIEVEMENTS_URL = f'{API_PREFIX}/achievements'
RATES_URL = f'{ACHIEVEMENTS_URL}/rates'
PICTURE = '7a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d'
WORLD = {
    'places': [
        {'id': 'library', 'name': '도서관', 'description': '', 'image_id': None},
        {'id': 'cafe', 'name': '카페', 'description': '', 'image_id': None},
    ],
    'paths': [{'a': 'library', 'b': 'cafe', 'minutes': 10}],
    'start_place': 'library',
}


def achievement(achievement_id: str, kind: str, target: str | None = None, count: int = 1, **fields) -> dict:
    when = {'match': 'all', 'items': [{'kind': kind, 'target': target, 'value': None, 'count': count}]}
    return {
        'id': achievement_id,
        'name': f'{achievement_id} 업적',
        'description': f'{achievement_id} 을 했다',
        'when': when,
        **fields,
    }


CHATTY = achievement('chatty', 'messages_at_least', count=2, image_id=PICTURE)
CAFE = achievement('cafe', 'visited_place', 'cafe', hidden=True)


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter(ScriptedProvider(pieces=['어서 와요.']))
    app.state.model_router = fake
    return fake


@pytest.fixture
async def model_on(clean_tables: None, session: AsyncSession) -> None:
    await turn_on_luna(session)


async def start(client: AsyncClient, asset: FakeAsset, headers: dict, achievements: list[dict] | None = None) -> dict:
    world = {**WORLD, 'achievements': achievements or []}
    character = asset.add_character(make_character(world=world))
    body = {'character_id': str(character.id), 'model': 'luna'}
    response = await client.post(CONVERSATIONS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return {**response.json(), 'source': str(character.id)}


async def finished(app: FastAPI) -> None:
    await asyncio.gather(*list(app.state.turns))


async def send(app: FastAPI, client: AsyncClient, headers: dict, conversation: dict) -> dict:
    """말을 보내고 done 메시지를 돌려준다."""
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    response = await client.post(url, json={'content': '안녕'}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await finished(app)
    return parse_sse(response.text)[-1][1]


async def move(app: FastAPI, client: AsyncClient, headers: dict, conversation: dict, place: str) -> dict:
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/actions'
    response = await client.post(url, json={'kind': 'move', 'place': place}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await finished(app)
    return parse_sse(response.text)[-1][1]


async def mine_of(client: AsyncClient, headers: dict, source: str) -> list[dict]:
    response = await client.get(ACHIEVEMENTS_URL, params={'character_id': source}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()['items']


async def rates_of(client: AsyncClient, source: str) -> dict:
    response = await client.get(RATES_URL, params={'character_id': source})
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def test_enough_messages_give_the_achievement_once(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start(client, asset, mine, [CHATTY])

    first = await send(app, client, mine, conversation)
    second = await send(app, client, mine, conversation)
    third = await send(app, client, mine, conversation)

    assert first['achievements'] == []
    assert second['achievements'] == [
        {'id': 'chatty', 'name': 'chatty 업적', 'description': 'chatty 을 했다', 'image_id': PICTURE}
    ]
    assert third['achievements'] == []
    records = await mine_of(client, mine, conversation['source'])
    assert [(one['achievement_id'], one['image_id'], one['conversation_id']) for one in records] == [
        ('chatty', PICTURE, conversation['id'])
    ]
    assert await rates_of(client, conversation['source']) == {
        'players': 1,
        'items': [{'achievement_id': 'chatty', 'earned_count': 1}],
    }


async def test_a_move_gives_the_hidden_achievement_with_its_name(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start(client, asset, mine, [CAFE])

    done = await move(app, client, mine, conversation, 'cafe')

    assert [one['id'] for one in done['achievements']] == ['cafe']
    records = await mine_of(client, mine, conversation['source'])
    assert [(one['name'], one['description']) for one in records] == [('cafe 업적', 'cafe 을 했다')]


async def test_talking_counts_as_playing_even_without_achievements(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start(client, asset, mine)
    assert await rates_of(client, conversation['source']) == {'players': 0, 'items': []}

    done = await send(app, client, mine, conversation)

    assert done['achievements'] == []
    assert await rates_of(client, conversation['source']) == {'players': 1, 'items': []}
    assert await mine_of(client, mine, conversation['source']) == []


async def test_a_failing_award_does_not_break_the_answer(
    client: AsyncClient,
    app: FastAPI,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    mine: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    conversation = await start(client, asset, mine, [CHATTY])

    async def broken(*_args, **_kwargs):
        raise RuntimeError('db is gone')

    monkeypatch.setattr(achievements_service, 'award', broken)
    done = await send(app, client, mine, conversation)

    assert (done['message']['content'], done['achievements']) == ('어서 와요.', [])


async def test_my_achievements_need_login_but_rates_do_not(client: AsyncClient):
    character_id = str(uuid.uuid4())

    mine = await client.get(ACHIEVEMENTS_URL, params={'character_id': character_id})
    rates = await client.get(RATES_URL, params={'character_id': character_id})

    assert mine.status_code == status.HTTP_401_UNAUTHORIZED
    assert (rates.status_code, rates.json()) == (status.HTTP_200_OK, {'players': 0, 'items': []})


async def test_writing_the_same_achievement_twice_keeps_the_first(session: AsyncSession):
    source = uuid.uuid4()
    now = datetime(2026, 11, 9, tzinfo=UTC)
    first = AchievementDocument(id='chatty', name='처음 이름')
    later = AchievementDocument(id='chatty', name='바뀐 이름')

    added = await repository.add_achievements(session, ME, source, [first], None, now)
    again = await repository.add_achievements(session, ME, source, [later], None, now)
    await session.commit()

    assert (added, again) == (frozenset({'chatty'}), frozenset())
    assert [record.name for record in await repository.achievements_of(session, ME, source)] == ['처음 이름']
    assert await repository.add_achievements(session, ME, source, [], None, now) == frozenset()


async def test_an_award_for_a_conversation_that_is_gone_gives_nothing(app: FastAPI, clean_tables: None):
    now = datetime(2026, 11, 9, tzinfo=UTC)

    earned = await achievements_service.award(app.state.session_factory, ME, uuid.uuid4(), uuid.uuid4(), now)

    assert earned == ()


async def test_an_achievement_another_conversation_wrote_first_is_not_announced(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    mine: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    conversation = await start(client, asset, mine, [achievement('hello', 'messages_at_least', count=1)])
    source = uuid.UUID(conversation['source'])
    early = AchievementDocument(id='hello', name='먼저')
    await repository.add_achievements(session, ME, source, [early], None, datetime.now(UTC))
    await session.commit()

    # 받은 것을 읽은 뒤에 다른 대화가 적은 것과 같다. 이 답은 받은 것이 없다고 읽는다
    async def nothing_owned(*_args) -> frozenset[str]:
        return frozenset()

    monkeypatch.setattr(achievements_service.repository, 'achievement_ids_of', nothing_owned)
    done = await send(app, client, mine, conversation)

    assert done['achievements'] == []
    assert [one['name'] for one in await mine_of(client, mine, conversation['source'])] == ['먼저']
