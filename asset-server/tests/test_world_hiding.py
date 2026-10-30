# asset-server/tests/test_world_hiding.py

"""
운영자가 세계관을 숨기고 푸는 것(app/operators/, 캐릭터의 숨김과 같다)을 검증한다. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 운영자가 아니면 404 다. 사유가 없으면 422, 없는 세계관은 404 다
  - 숨긴 세계관은 공개여도 공개 목록과 소개, 남에게 내주는 판(story 의 새 세션), 남이 보는 그림에서 빠진다.
    주인은 계속 쓴다(초안의 hidden_at 으로 안다). 주인이 비공개로 했다가 공개로 돌려도 숨김이 앞선다. 풀면 돌아온다
  - 조치마다 감사 기록(world_hide, world_unhide)이 남는다. 두 번 숨겨도 처음 숨긴 시각을 둔다
  - 숨김이 바뀌면 주인에게 world.hidden, world.unhidden 을 알린다. 그대로면 알리지 않는다
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from app.notifications.models import OutgoingNotification
from app.operators.models import OperatorAction
from tests.images import FakeImageStore, own_image
from tests.signing import signed_get
from tests.worlds import OTHER, OWNER, WORLDS_URL, bearer, character, create_world, full_world, publish

pytestmark = pytest.mark.usefixtures('clean_tables')

ADMIN_URL = f'{API_PREFIX}/admin'
LISTINGS_URL = f'{API_PREFIX}/listings/worlds'
IMAGES_URL = f'{API_PREFIX}/images'
OPERATOR = uuid.UUID('22222222-2222-4333-8444-555555555555')


@pytest.fixture
def owner(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OWNER)


@pytest.fixture
def player(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OTHER, operator=False)


@pytest.fixture
def operator(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OPERATOR)


@pytest.fixture
def store(app: FastAPI) -> FakeImageStore:
    fake = FakeImageStore()
    app.state.image_store = fake
    return fake


async def public_world(client: AsyncClient, headers: dict, **fields) -> dict:
    """공개로 두고 게시한 세계관."""
    ari, beo = await character(client, headers, '아리'), await character(client, headers, '버')
    world = await create_world(client, headers, {**full_world(ari['id'], beo['id']), **fields})
    await client.patch(f'{WORLDS_URL}/{world["id"]}', json={'visibility': 'public'}, headers=headers)
    response = await publish(client, headers, world)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return world


async def set_hidden(client: AsyncClient, headers: dict, world: dict, hidden: bool, reason: str = '신고 확인'):
    body = {'hidden': hidden, 'reason': reason}
    return await client.put(f'{ADMIN_URL}/worlds/{world["id"]}/hidden', json=body, headers=headers)


async def listed_ids(client: AsyncClient, headers: dict) -> list[str]:
    return [item['id'] for item in (await client.get(LISTINGS_URL, headers=headers)).json()['items']]


async def outgoing(session: AsyncSession) -> list[OutgoingNotification]:
    session.expire_all()
    return list(await session.scalars(select(OutgoingNotification).order_by(OutgoingNotification.id)))


async def test_only_operators_hide_with_a_reason(client: AsyncClient, owner: dict, player: dict, operator: dict):
    world = await public_world(client, owner)

    refused = await set_hidden(client, player, world, True)
    blank = await set_hidden(client, operator, world, True, reason='  ')
    missing = await set_hidden(client, operator, {'id': str(uuid.uuid4())}, True)

    assert refused.status_code == status.HTTP_404_NOT_FOUND
    assert blank.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert missing.status_code == status.HTTP_404_NOT_FOUND


async def test_a_hidden_world_is_gone_for_everyone_but_the_owner(
    client: AsyncClient, owner: dict, player: dict, operator: dict
):
    world = await public_world(client, owner)

    hidden = await set_hidden(client, operator, world, True)

    assert (hidden.status_code, hidden.json()) == (status.HTTP_200_OK, {'hidden': True})
    assert await listed_ids(client, player) == []
    assert (await client.get(f'{LISTINGS_URL}/{world["id"]}', headers=player)).status_code == 404
    # 다른 사람은 story 의 새 세션을 시작하지 못하고, 주인은 계속 쓴다
    assert (await signed_get(client, f'/worlds/{world["id"]}/latest', player)).status_code == 404
    assert (await signed_get(client, f'/worlds/{world["id"]}/latest', owner)).status_code == 200
    draft = (await client.get(f'{WORLDS_URL}/{world["id"]}', headers=owner)).json()
    mine = (await client.get(WORLDS_URL, headers=owner)).json()['items']
    assert draft['hidden_at'] is not None and mine[0]['hidden_at'] is not None


async def test_going_public_again_does_not_unhide_but_the_operator_does(
    client: AsyncClient, owner: dict, player: dict, operator: dict
):
    world = await public_world(client, owner)
    await set_hidden(client, operator, world, True)

    await client.patch(f'{WORLDS_URL}/{world["id"]}', json={'visibility': 'private'}, headers=owner)
    await client.patch(f'{WORLDS_URL}/{world["id"]}', json={'visibility': 'public'}, headers=owner)
    still = await listed_ids(client, player)
    unhidden = await set_hidden(client, operator, world, False)

    assert still == []
    assert unhidden.json() == {'hidden': False}
    assert await listed_ids(client, player) == [world['id']]
    assert (await signed_get(client, f'/worlds/{world["id"]}/latest', player)).status_code == 200


async def test_a_hidden_worlds_images_are_not_seen_by_others(
    client: AsyncClient, session: AsyncSession, owner: dict, player: dict, operator: dict, store: FakeImageStore
):
    cover = await own_image(session, OWNER)
    world = await public_world(client, owner, image_id=cover)
    shown = (await client.get(f'{IMAGES_URL}/{cover}', headers=player)).status_code

    await set_hidden(client, operator, world, True)

    assert (shown, (await client.get(f'{IMAGES_URL}/{cover}', headers=player)).status_code) == (200, 404)
    assert (await client.get(f'{IMAGES_URL}/{cover}', headers=owner)).status_code == 200


async def test_actions_are_recorded_and_the_first_time_is_kept(
    client: AsyncClient, session: AsyncSession, owner: dict, operator: dict
):
    world = await public_world(client, owner)

    await set_hidden(client, operator, world, True, '첫 숨김')
    first = (await client.get(f'{WORLDS_URL}/{world["id"]}', headers=owner)).json()['hidden_at']
    await set_hidden(client, operator, world, True, '다시 숨김')
    again = (await client.get(f'{WORLDS_URL}/{world["id"]}', headers=owner)).json()['hidden_at']
    await set_hidden(client, operator, world, False, '풀기')

    assert first == again
    actions = list(await session.scalars(select(OperatorAction).order_by(OperatorAction.id)))
    assert [(action.action, action.reason, str(action.target_id)) for action in actions] == [
        ('world_hide', '첫 숨김', world['id']),
        ('world_hide', '다시 숨김', world['id']),
        ('world_unhide', '풀기', world['id']),
    ]
    assert all(action.operator_id == OPERATOR for action in actions)


async def test_the_owner_is_told_only_when_the_hiding_changes(
    client: AsyncClient, session: AsyncSession, owner: dict, operator: dict
):
    world = await public_world(client, owner, name='여름 마을')

    await set_hidden(client, operator, world, False)
    await set_hidden(client, operator, world, True)
    await set_hidden(client, operator, world, True)
    await set_hidden(client, operator, world, False)

    action_ids = list(await session.scalars(select(OperatorAction.id).order_by(OperatorAction.id)))
    hidden, unhidden = await outgoing(session)
    payload = {'world_id': world['id'], 'name': '여름 마을'}
    assert (hidden.user_id, hidden.kind, hidden.payload) == (OWNER, 'world.hidden', payload)
    assert (unhidden.user_id, unhidden.kind, unhidden.payload) == (OWNER, 'world.unhidden', payload)
    assert hidden.source_key == f'world.hidden:{world["id"]}:{action_ids[1]}'
    assert unhidden.source_key == f'world.unhidden:{world["id"]}:{action_ids[3]}'
