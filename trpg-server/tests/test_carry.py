# trpg-server/tests/test_carry.py

"""
쓰러진 동료를 업고 가기(#367, app/rounds/map_actions.py 의 carry)를 검증한다.

쓰러진 사람은 선언을 못 하니 일행이 가면 혼자 남았다. 방장이 옮겨 주던 것을 가기의 행동이 대신한다.
맵과 픽스처는 tests/test_table_map.py 의 것이다. 방장(기사)과 함께 앉는 사람(약사), 성문(시작)-광장 큰길.

보는 것.
  - 업고 가기: 업은 사람과 업힌 사람이 함께 옮겨 간다. 이벤트가 둘이고 둘째에 업은 사람이 적힌다.
  - 받을 때의 거절: 자기 자신, 서 있는 사람, 죽은 사람, 다른 곳의 사람, 앉지 않은 사람은 모두 422 carry 다.
  - 차례가 왔을 때: 그사이 일어났거나 죽었거나 다른 곳에 있거나 업은 사람이 못 갔으면 업지 않는다.
  - 서술: 간 곳의 줄에 업고 간 사람이 붙는다. 업지 않는 가기의 결과와 저장 모양은 예전과 같다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.rounds import map_actions, move_lines
from app.rounds.narrator import TravelNote
from tests import test_table_map as map_tables
from tests.test_map_actions import going, outcome_of
from tests.test_table_items import FRIEND, ME, events_of, read_table, table_url
from tests.test_table_map import place_of, start_duo

pytestmark = pytest.mark.usefixtures('clean_tables')

me = map_tables.me
friend = map_tables.friend
lore = map_tables.lore


def carrying(place: dict, user_id: uuid.UUID) -> dict:
    """그 사람을 업고 그 장소로 가는 행동."""
    return {**going(place), 'carry': str(user_id)}


async def knock_down(session: AsyncSession, user_id: uuid.UUID = FRIEND) -> None:
    """그 사람을 쓰러뜨린다. 고비는 넘겼다(죽음의 굴림을 굴리지 않는다)."""
    query = 'UPDATE table_sheets SET hp = 0, death_successes = 3 WHERE user_id = :user_id'
    await session.execute(text(query), {'user_id': user_id})
    await session.commit()


async def kill(session: AsyncSession, user_id: uuid.UUID = FRIEND) -> None:
    """그 사람의 캐릭터가 죽은 것으로 한다."""
    query = 'UPDATE table_sheets SET hp = 0, died_at = now() WHERE user_id = :user_id'
    await session.execute(text(query), {'user_id': user_id})
    await session.commit()


async def put_at(session: AsyncSession, place: dict, user_id: uuid.UUID = FRIEND) -> None:
    """그 사람의 캐릭터를 그 장소에 세운다."""
    query = 'UPDATE table_sheets SET place_id = :place WHERE user_id = :user_id'
    await session.execute(text(query), {'place': place['id'], 'user_id': user_id})
    await session.commit()


async def send(client: AsyncClient, headers: dict, table: dict, action: dict):
    """업고 가는 선언을 보내는 요청. 응답을 그대로 돌려준다."""
    body = {'content': '동료를 업고 간다.', 'action': action}
    return await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=headers)


# --- 업고 가기 ---


async def test_a_downed_friend_is_carried_along(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession, narrated
):
    table = await start_duo(client, me, friend, lore)
    await knock_down(session)

    # 쓰러진 약사는 기다리지 않으므로 기사 혼자 내면 닫힌다
    response = await send(client, me, table, carrying(lore['square'], FRIEND))
    assert response.status_code == status.HTTP_200_OK, response.text
    await narrated()

    seen = await read_table(client, me, table)
    assert place_of(seen, ME) == place_of(seen, FRIEND) == lore['square']['id']
    move = (await outcome_of(client, me, table, 1, ME))['move']
    assert move['carry'] == {'user_id': str(FRIEND), 'character_name': '약사', 'carried': True, 'reason': None}
    mine, carried = await events_of(client, friend, table, 'character_moved')
    assert (carried['actor_id'], carried['caused_by_sequence']) == (None, mine['sequence'])
    assert carried['payload']['user_id'] == str(FRIEND)
    assert carried['payload']['carried_by'] == str(ME)
    assert carried['payload']['to'] == mine['payload']['to']
    # 업힌 사람도 그곳이 서 본 곳이 된다. 맵에 광장이 보인다
    assert '광장' in map_tables.known_places(seen)


async def test_a_plain_move_is_saved_as_before(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)

    response = await send(client, me, table, going(lore['square']))

    assert response.status_code == status.HTTP_200_OK, response.text
    # 업지 않으면 저장한 행동에 carry 가 없다(업고 가기가 생기기 전과 같은 모양)
    query = text('SELECT action FROM round_declarations')
    assert (await session.execute(query)).scalars().all() == [{'kind': 'move', 'place': lore['square']['id']}]


# --- 받을 때의 거절 ---


@pytest.mark.parametrize('case', ['self', 'standing', 'dead', 'elsewhere', 'stranger'])
async def test_only_a_downed_friend_beside_you_is_carried(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession, case: str
):
    table = await start_duo(client, me, friend, lore)
    if case == 'dead':
        await kill(session)
    elif case == 'elsewhere':
        await knock_down(session)
        await put_at(session, lore['square'])
    elif case != 'standing':
        await knock_down(session)
    target = {'self': ME, 'stranger': uuid.uuid4()}.get(case, FRIEND)

    response = await send(client, me, table, carrying(lore['square'], target))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {'detail': 'action.carry 가 같은 장소에 쓰러져 있는(죽지 않은) 다른 사람이 아닙니다.'}


# --- 차례가 왔을 때 ---


def member(user_id: uuid.UUID, place: uuid.UUID, hp: int = 0, dead: bool = False) -> SimpleNamespace:
    """map_actions 가 보는 만큼만 있는 앉은 사람."""
    sheet = SimpleNamespace(hp=hp, place_id=place, died_at=object() if dead else None)
    return SimpleNamespace(user_id=user_id, character_name='약사', sheet=sheet)


HERE = uuid.uuid4()
THERE = uuid.uuid4()


@pytest.mark.parametrize(
    ('carried', 'to', 'reason'),
    [
        (member(FRIEND, HERE), THERE, None),
        (member(FRIEND, HERE), None, 'not_moved'),
        (member(FRIEND, HERE, hp=3), THERE, 'standing'),
        (member(FRIEND, HERE, dead=True), THERE, 'dead'),
        (member(FRIEND, THERE), THERE, 'elsewhere'),
        (None, THERE, 'elsewhere'),
    ],
    ids=['carried', 'carrier-stuck', 'got-up', 'died', 'taken-first', 'left-the-table'],
)
def test_what_stops_a_carry(carried, to, reason):
    assert map_actions.carry_problem(carried, HERE, to) == reason


# --- 서술 ---


@pytest.mark.parametrize(
    ('note', 'line'),
    [
        (
            TravelNote('성문', '숲', True, travel_minutes=180, carried='약사'),
            '(간 곳: 성문 → 숲, 3시간 걸림, 약사을(를) 업고)',
        ),
        (
            TravelNote('성문', '숲', True, carried='약사', carry_reason='dead'),
            '(간 곳: 성문 → 숲. 약사은(는) 숨을 거두어 쓰러진 곳에 남았다)',
        ),
        (
            TravelNote('성문', '숲', False, reason='not_adjacent', carried='약사', carry_reason='not_moved'),
            '(가려던 곳: 숲. 그쪽으로 이어진 길이 없었다)',
        ),
        (TravelNote('성문', '숲', True), '(간 곳: 성문 → 숲)'),
    ],
    ids=['carried', 'died', 'carrier-stuck', 'alone'],
)
def test_the_carry_is_on_the_travel_line(note: TravelNote, line: str):
    assert move_lines.describe_travel(note) == line
