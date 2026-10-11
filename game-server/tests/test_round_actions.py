# game-server/tests/test_round_actions.py

"""
선언에 붙이는 행동을 검증한다.

행동은 선언의 글을 엔진이 읽을 수 있는 모양으로 적은 것이다. 여기서는 받고, 검사하고, 저장하고, 보여 주는 것까지 본다.
행동으로 판정하는 것은 라운드를 닫을 때의 일이다(다른 테스트).
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')

KICK = '문을 걷어찬다.'
LAUGH = '크게 웃는다.'
# 근력으로 어려움에 도전한다
KICK_ACTION = {'kind': 'check', 'ability': 'str', 'difficulty': 'hard'}


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 방장이다. 캐릭터는 '엘프'다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 들어오는 사람의 머리말. 캐릭터는 '영애'다."""
    return bearer(signing_key, FRIEND)


def rounds_url(table: dict, path: str = '') -> str:
    return f'{TABLES_URL}/{table["id"]}/rounds{path}'


async def start_duo(client: AsyncClient, me: dict[str, str], friend: dict[str, str]) -> dict:
    """나와 친구가 앉은 테이블을 시작한다. 규칙은 SRD5 템플릿이다."""
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북'}, headers=me)
    body = {'title': '추격전', 'rulebook_id': rulebook.json()['id'], 'openings': ['사이렌이 울린다.']}
    scenario = (await client.post(SCENARIOS_URL, json={**body, 'default_sheet': SHEET}, headers=me)).json()
    await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)
    created = await client.post(
        TABLES_URL, json={'scenario_id': scenario['id'], 'version': 1, 'capacity': 2}, headers=me
    )
    table = created.json()
    await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    await client.put(f'{TABLES_URL}/{table["id"]}/character', json={'name': '엘프'}, headers=me)
    await client.put(f'{TABLES_URL}/{table["id"]}/character', json={'name': '영애'}, headers=friend)
    started = await client.post(f'{TABLES_URL}/{table["id"]}/start', headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return table


async def declare(client: AsyncClient, headers: dict[str, str], table: dict, content: str, action: dict | None = None):
    """선언을 내는 요청을 보낸다. 응답을 그대로 돌려준다. action 을 주지 않으면 그 칸을 보내지 않는다."""
    body = {'content': content} if action is None else {'content': content, 'action': action}
    return await client.put(rounds_url(table, '/current/declaration'), json=body, headers=headers)


async def current(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    response = await client.get(rounds_url(table, '/current'), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def stored(action: dict) -> dict:
    """
    저장된 행동의 모양. 보낸 칸에 더해, 붙이지 않은 대가와 보상과 대상과 타격이 None 으로 들어 있다.

    죽이려는지(lethal)는 붙이지 않으면 false 다.
    """
    defaults = {'risk': None, 'recover': None, 'target': None, 'harm': None, 'npc': None, 'lethal': False}
    return {**defaults, **action}


def actions(round_: dict) -> dict[str, dict | None]:
    """라운드의 선언을 {캐릭터 이름: 행동} 으로 바꾼다."""
    return {declaration['character_name']: declaration['action'] for declaration in round_['declarations']}


# --- 행동을 붙여 선언한다 ---


async def test_declares_with_an_action(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await start_duo(client, me, friend)

    response = await declare(client, me, table, KICK, KICK_ACTION)

    assert response.status_code == status.HTTP_200_OK
    assert actions(response.json()) == {'엘프': stored(KICK_ACTION)}
    assert response.json()['declarations'][0]['content'] == KICK


async def test_a_declaration_without_an_action_is_still_taken(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)

    response = await declare(client, me, table, LAUGH)

    # 판정이 없는 선언이다. 대화나 둘러보기처럼 주사위를 굴릴 일이 없는 것
    assert response.status_code == status.HTTP_200_OK
    assert actions(response.json()) == {'엘프': None}


async def test_a_missing_difficulty_becomes_the_default_of_the_rules(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    table = await start_duo(client, me, friend)

    response = await declare(client, me, table, KICK, {'kind': 'check', 'ability': 'str'})

    # 저장할 때 채운다. 읽는 쪽이 "비어 있으면 기본"을 다시 따지지 않는다
    filled = {'kind': 'check', 'ability': 'str', 'difficulty': 'medium'}
    assert actions(response.json()) == {'엘프': stored(filled)}
    assert await session.scalar(text('SELECT action FROM round_declarations')) == stored(filled)


async def test_declaring_again_replaces_the_action_too(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await start_duo(client, me, friend)
    await declare(client, me, table, KICK, KICK_ACTION)

    changed = await declare(client, me, table, KICK, {'kind': 'check', 'ability': 'dex', 'difficulty': 'easy'})
    dropped = await declare(client, me, table, LAUGH)

    assert actions(changed.json()) == {'엘프': stored({'kind': 'check', 'ability': 'dex', 'difficulty': 'easy'})}
    # 선언은 통째로 바뀐다. 행동을 빼고 다시 내면 행동도 없어진다
    assert actions(dropped.json()) == {'엘프': None}


# --- 틀린 행동 ---


@pytest.mark.parametrize(
    ('action', 'field'),
    [
        ({'kind': 'check', 'ability': 'luck'}, 'ability'),
        ({'kind': 'check', 'ability': 'str', 'difficulty': 'impossible'}, 'difficulty'),
    ],
)
async def test_an_action_must_use_what_the_rules_of_the_table_have(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], action: dict, field: str
):
    table = await start_duo(client, me, friend)
    await declare(client, me, table, LAUGH)

    response = await declare(client, me, table, KICK, action)

    # 모양은 맞지만 이 테이블의 규칙에 없는 능력이나 난이도다
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert f'action.{field}' in response.json()['detail']
    # 거절된 요청은 앞의 선언을 바꾸지 않는다
    mine = (await current(client, me, table))['declarations'][0]
    assert (mine['content'], mine['action']) == (LAUGH, None)


@pytest.mark.parametrize(
    'action',
    [
        {'ability': 'str'},
        {'kind': 'attack', 'ability': 'str'},
        {'kind': 'check'},
        {'kind': 'check', 'ability': 'str', 'difficulty': 15},
        # 결과를 적어 보낼 수 없다
        {'kind': 'check', 'ability': 'str', 'roll': 20},
        {'kind': 'check', 'ability': 'str', 'success': True},
        # 행동은 하나만 붙인다
        [{'kind': 'check', 'ability': 'str'}, {'kind': 'check', 'ability': 'dex'}],
        'str',
    ],
)
async def test_rejects_an_action_with_a_bad_shape(client: AsyncClient, me: dict[str, str], friend: dict, action):
    table = await start_duo(client, me, friend)

    response = await declare(client, me, table, KICK, action)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert (await current(client, me, table))['declarations'] == []


# --- 누가 보는가 ---


async def test_others_actions_are_hidden_until_the_round_closes(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    await declare(client, me, table, KICK, KICK_ACTION)

    seen_by_friend = await client.get(rounds_url(table, '/current'), headers=friend)

    # 누가 냈는지는 보인다. 글도 행동도 보이지 않는다. 남의 행동을 보고 자기 행동을 정하지 못한다
    assert actions(seen_by_friend.json()) == {'엘프': None}
    assert 'hard' not in seen_by_friend.text
    assert actions(await current(client, me, table)) == {'엘프': stored(KICK_ACTION)}


async def test_everyone_sees_the_actions_once_the_round_is_closing(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await declare(client, me, table, KICK, KICK_ACTION)

    closing = (await declare(client, friend, table, LAUGH)).json()
    await narrated()
    closed = (await client.get(rounds_url(table, '/1'), headers=friend)).json()

    assert closing['status'] == 'closing'
    assert actions(closing) == {'엘프': stored(KICK_ACTION), '영애': None}
    assert actions(closed) == {'엘프': stored(KICK_ACTION), '영애': None}


async def test_the_action_is_recorded_when_the_round_closes(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await declare(client, me, table, KICK, KICK_ACTION)
    before = (await client.get(f'{TABLES_URL}/{table["id"]}/events', headers=friend)).json()['items']

    await declare(client, friend, table, LAUGH)
    await narrated()

    events = (await client.get(f'{TABLES_URL}/{table["id"]}/events', headers=friend)).json()['items']
    recorded = [event['payload'] for event in events if event['type'] == 'player_action']
    # 열려 있는 동안에는 적히지 않는다. 이벤트는 모두가 읽는다
    assert 'player_action' not in [event['type'] for event in before]
    assert recorded == [
        {'round': 1, 'character_name': '엘프', 'content': KICK, 'action': stored(KICK_ACTION)},
        {'round': 1, 'character_name': '영애', 'content': LAUGH, 'action': None},
    ]
