# game-server/tests/test_operator_sanctions.py

"""
운영자의 제재(#392).

보는 것.
  - 시나리오 제재: 공개가 내려가고 그 판은 다시 공개하지 못한다. 제작자는 그 판으로 혼자 테이블을 연다.
    고쳐서 새 판을 내면 바로 공개된다. 공개 중이 아닌 시나리오는 제재할 수 없다(409)
  - 공개 금지: 제재가 정해진 수에 닿으면 저절로 금지된다. 운영자가 금지하고 푼다. 푼 뒤의 제재부터 다시 센다.
    금지되어도 플레이(자기 판, 남의 공개 판)는 된다
  - 테이블 끝내기: 앉은 사람에게 "운영자가 끝냈다"가 보이고 사유와 운영자는 보이지 않는다
  - 운영자가 아니면 404, 사유가 없으면 422. 제재할 때마다 감사 기록이 남고, 고치거나 지울 수 없다
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from app.operators.models import OperatorAction
from tests.signing import SigningKey, make_access_claims, make_token
from tests.test_listings_api import (
    LISTINGS_URL,
    ME,
    create_scenario,
    listing_url,
    make_public,
    publish_version,
    write_page,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

ADMIN_URL = f'{API_PREFIX}/admin'
TABLES_URL = f'{API_PREFIX}/tables'
OPERATOR = uuid.UUID('77777777-2222-4333-8444-555555555555')
PLAYER = uuid.UUID('55555555-2222-4333-8444-555555555555')
REASON = {'reason': '신고 #7'}


def bearer(signing_key: SigningKey, user_id: uuid.UUID, **claims) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id), **claims))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """시나리오를 쓰고 공개하는 제작자의 머리말."""
    return bearer(signing_key, ME)


@pytest.fixture
def player(signing_key: SigningKey) -> dict[str, str]:
    """남의 시나리오로 노는 사람의 머리말."""
    return bearer(signing_key, PLAYER)


@pytest.fixture
def operator(signing_key: SigningKey) -> dict[str, str]:
    """운영자의 머리말."""
    return bearer(signing_key, OPERATOR, roles=['operator'])


async def sanction(client: AsyncClient, headers: dict, scenario: dict, **body) -> object:
    """시나리오를 제재해 본다. 응답을 그대로 돌려준다."""
    return await client.post(f'{ADMIN_URL}/scenarios/{scenario["id"]}/sanction', json=body or REASON, headers=headers)


async def publish(client: AsyncClient, headers: dict, scenario: dict, number: int) -> object:
    """그 판을 공개해 본다."""
    return await client.put(f'{listing_url(scenario)}/publication', json={'version': number}, headers=headers)


async def listed(client: AsyncClient, headers: dict) -> list[str]:
    """공개 목록에 보이는 시나리오들."""
    return [item['scenario_id'] for item in (await client.get(LISTINGS_URL, headers=headers)).json()['items']]


async def open_table(client: AsyncClient, headers: dict, scenario: dict, number: int | None = 1) -> object:
    """그 시나리오의 판으로 테이블을 열어 본다. 번호가 없으면 공개 중인 판이다(남의 시나리오는 이 길로만 연다)."""
    body = {'scenario_id': scenario['id'], 'version': number, 'capacity': 2}
    return await client.post(TABLES_URL, json=body, headers=headers)


async def actions(session: AsyncSession) -> list[tuple[str, uuid.UUID]]:
    """제재의 감사 기록. 적힌 순서대로 (종류, 대상)."""
    rows = await session.scalars(select(OperatorAction).order_by(OperatorAction.id))
    return [(row.action, row.target_id) for row in rows]


# --- 운영자만 ---


async def test_a_player_cannot_sanction(client: AsyncClient, me: dict, session: AsyncSession):
    scenario = await make_public(client, me)

    response = await sanction(client, me, scenario)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert await actions(session) == []


@pytest.mark.parametrize('body', [{}, {'reason': ''}, {'reason': '   '}, {'reason': 'x' * 201}])
async def test_a_sanction_needs_a_reason(client: AsyncClient, me: dict, operator: dict, body: dict):
    scenario = await make_public(client, me)

    response = await client.post(f'{ADMIN_URL}/scenarios/{scenario["id"]}/sanction', json=body, headers=operator)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 시나리오 제재 ---


async def test_a_sanction_takes_the_scenario_down(
    client: AsyncClient, me: dict, player: dict, operator: dict, session: AsyncSession
):
    scenario = await make_public(client, me)

    response = await sanction(client, operator, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    body = response.json()
    assert (body['version_number'], body['owner_id'], body['publishing_banned']) == (1, str(ME), False)
    assert await listed(client, player) == []
    assert await actions(session) == [('scenario_sanction', uuid.UUID(scenario['id']))]


async def test_the_owner_still_plays_a_sanctioned_version_alone(client: AsyncClient, me: dict, operator: dict):
    scenario = await make_public(client, me)
    await sanction(client, operator, scenario)

    opened = await open_table(client, me, scenario)

    assert opened.status_code == status.HTTP_201_CREATED, opened.text


async def test_a_sanctioned_version_cannot_be_published_again_but_a_new_one_can(
    client: AsyncClient, me: dict, player: dict, operator: dict
):
    scenario = await make_public(client, me)
    await sanction(client, operator, scenario)

    again = await publish(client, me, scenario, 1)
    number = await publish_version(client, me, scenario, note='고쳤다')
    fixed = await publish(client, me, scenario, number)

    assert again.status_code == status.HTTP_403_FORBIDDEN
    assert again.json()['code'] == 'version_sanctioned'
    assert fixed.status_code == status.HTTP_200_OK, fixed.text
    assert await listed(client, player) == [scenario['id']]


async def test_a_scenario_that_is_not_public_cannot_be_sanctioned(
    client: AsyncClient, me: dict, operator: dict, session: AsyncSession
):
    scenario = await make_public(client, me)
    await client.put(f'{listing_url(scenario)}/publication', json={'version': None}, headers=me)

    response = await sanction(client, operator, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'not_published'
    assert await actions(session) == []


# --- 공개 금지 ---


async def ready_to_publish(client: AsyncClient, headers: dict) -> dict:
    """판을 내고 소개 페이지까지 써서 공개만 남은 시나리오."""
    scenario = await create_scenario(client, headers)
    await publish_version(client, headers, scenario)
    await write_page(client, headers, scenario)
    return scenario


async def sanction_many(client: AsyncClient, me: dict, operator: dict, count: int) -> list[dict]:
    """제작자의 시나리오를 count 개 공개하고 모두 제재한다. 제재의 응답들을 돌려준다."""
    results = []
    for _ in range(count):
        scenario = await make_public(client, me)
        results.append((await sanction(client, operator, scenario)).json())
    return results


async def ban(client: AsyncClient, operator: dict, user_id: uuid.UUID, lift: bool = False) -> object:
    """공개를 금지하거나(lift 가 거짓) 풀어 본다."""
    path = f'{ADMIN_URL}/users/{user_id}/publishing-ban' + ('/lift' if lift else '')
    return await client.post(path, json=REASON, headers=operator)


async def test_enough_sanctions_ban_publishing(app: FastAPI, client: AsyncClient, me: dict, operator: dict):
    app.state.settings.publishing_ban_threshold = 2
    first, second = await sanction_many(client, me, operator, 2)
    scenario = await ready_to_publish(client, me)

    refused = await publish(client, me, scenario, 1)

    assert (first['publishing_banned'], second['publishing_banned']) == (False, True)
    assert refused.status_code == status.HTTP_403_FORBIDDEN
    assert refused.json()['code'] == 'publishing_banned'


async def test_a_banned_creator_still_plays(client: AsyncClient, me: dict, player: dict, operator: dict):
    others = await make_public(client, player)
    mine = await ready_to_publish(client, me)
    await ban(client, operator, ME)

    own_table = await open_table(client, me, mine)
    other_table = await open_table(client, me, others, None)

    # 공개만 막는다. 자기 판으로도, 남의 공개 판으로도 테이블을 연다
    assert own_table.status_code == status.HTTP_201_CREATED, own_table.text
    assert other_table.status_code == status.HTTP_201_CREATED, other_table.text


async def test_an_operator_bans_and_lifts(client: AsyncClient, me: dict, operator: dict, session: AsyncSession):
    scenario = await ready_to_publish(client, me)

    banned = await ban(client, operator, ME)
    banned_again = await ban(client, operator, ME)
    refused = await publish(client, me, scenario, 1)
    lifted = await ban(client, operator, ME, lift=True)
    lifted_again = await ban(client, operator, ME, lift=True)
    published = await publish(client, me, scenario, 1)

    assert (banned.json()['banned'], banned.json()['banned_by']) == (True, str(OPERATOR))
    assert banned_again.json()['reason'] == 'already_banned'
    assert refused.json()['code'] == 'publishing_banned'
    assert (lifted.json()['banned'], lifted_again.json()['reason']) == (False, 'not_banned')
    assert published.status_code == status.HTTP_200_OK
    assert [action for action, _ in await actions(session)] == ['publishing_ban', 'publishing_unban']


async def test_a_lifted_ban_can_be_imposed_again(client: AsyncClient, me: dict, operator: dict):
    scenario = await ready_to_publish(client, me)
    await ban(client, operator, ME)
    await ban(client, operator, ME, lift=True)

    again = await ban(client, operator, ME)
    refused = await publish(client, me, scenario, 1)

    # 같은 줄을 다시 금지로 쓴다. 풀린 시각이 지워져야 다시 금지 중이다
    assert (again.json()['banned'], again.json()['lifted_at']) == (True, None)
    assert refused.json()['code'] == 'publishing_banned'


async def test_sanctions_before_a_lift_are_not_counted_again(
    app: FastAPI, client: AsyncClient, me: dict, operator: dict
):
    app.state.settings.publishing_ban_threshold = 2
    await sanction_many(client, me, operator, 2)
    await ban(client, operator, ME, lift=True)

    # 푼 뒤의 제재 하나로는 다시 금지되지 않는다. 옛 제재 둘은 세지 않는다
    (after,) = await sanction_many(client, me, operator, 1)

    assert after['publishing_banned'] is False


# --- 테이블 끝내기 ---


async def test_an_operator_ends_a_table(client: AsyncClient, me: dict, operator: dict, session: AsyncSession):
    scenario = await make_public(client, me)
    table = (await open_table(client, me, scenario)).json()

    ended = await client.post(f'{ADMIN_URL}/tables/{table["id"]}/end', json=REASON, headers=operator)
    again = await client.post(f'{ADMIN_URL}/tables/{table["id"]}/end', json=REASON, headers=operator)
    events = (await client.get(f'{TABLES_URL}/{table["id"]}/events', headers=me)).json()['items']

    assert ended.status_code == status.HTTP_200_OK, ended.text
    assert ended.json()['status'] == 'ended'
    assert again.json()['reason'] == 'already_ended'
    # 앉은 사람에게는 운영자가 끝냈다는 것만 보인다. 누가, 왜는 보이지 않는다
    last = events[-1]
    assert (last['type'], last['actor_id'], last['payload']) == ('table_ended', None, {'by': 'operator'})
    assert await actions(session) == [('table_end', uuid.UUID(table['id']))]


async def test_an_unknown_table_cannot_be_ended(client: AsyncClient, operator: dict, session: AsyncSession):
    response = await client.post(f'{ADMIN_URL}/tables/{uuid.uuid4()}/end', json=REASON, headers=operator)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert await actions(session) == []


# --- 감사 기록 ---


async def test_the_actions_cannot_be_deleted(client: AsyncClient, me: dict, operator: dict, session: AsyncSession):
    await ban(client, operator, ME)

    with pytest.raises(DBAPIError):
        await session.execute(delete(OperatorAction))
    await session.rollback()

    assert len(await actions(session)) == 1
