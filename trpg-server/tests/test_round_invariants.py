# trpg-server/tests/test_round_invariants.py

"""
라운드의 불변 조건을 무작위 판으로 검증한다(#812 의 DB 쪽). 엔진의 순수 함수는 tests/test_engine_invariants.py 가 본다.

Hypothesis 가 판 하나의 계획(라운드마다 둘이 무엇을 하는가, 방장이 닫기를 두 번 겹쳐 보내는가, 주사위의 씨앗)을 고르고,
시험은 그 계획대로 실제 API 와 PostgreSQL 로 판을 돈다. 라운드가 닫힐 때마다 불변 조건을 본다.
예 하나마다 새 테이블을 열어 예끼리 섞이지 않는다(DB 를 비우는 것은 시험 하나에 한 번이다).

판은 tests/test_quest_goals.py 의 것이다. 성문에 들쥐 둘(최대 HP 4, 물기)과
악역영애(최대 HP 4, 적대, 부채 후리기)가 있다.
나(기사)와 함께 앉는 사람(약사)은 최대 HP 5, 근력 18, 민첩 14 다. 민첩이 높아 늘 들쥐와 영애보다 먼저 움직인다.
그래서 같은 라운드에 먼저 죽인 들쥐와 영애가 제 차례에 치지 않는지도 본다.
주사위는 씨앗으로 정한 난수라 같은 계획이면 같은 판이 된다.

불변 조건.
  - 라운드는 한 번만 닫힌다. 닫힌 라운드마다 round_closed 가 하나이고, 지금 라운드의 번호는 닫힌 수 + 1 이다.
    방장이 닫기를 한꺼번에 두 번 보내면 하나만 받고(202) 하나는 거절한다(409).
  - 쓰러진 캐릭터는 글만 낸다. 행동을 붙이면 409 character_downed 다.
    행동을 막는 부상(기절 같은 것)을 입었으면 409 character_incapacitated 다.
  - 죽은 몬스터와 인물은 행동하지 않는다. 죽은 것이 적힌 뒤에 그것의 공격(monster_attacked, npc_attacked)이 없다.
    죽은 것을 치는 선언은 받지 않는다.
  - 캐릭터의 HP 는 0 과 최대 사이다.
"""

import asyncio
import random

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from tests.sheets import make_sheet
from tests.test_quest_goals import SMALL, make_world, start, strike
from tests.test_table_items import FRIEND, ME, bearer, read_table, table_url

pytestmark = pytest.mark.usefixtures('clean_tables')

BITE = {'name': '물기', 'ability': 'str', 'difficulty': 'medium', 'harm': 'light'}
SWIPE = {'name': '부채 후리기', 'ability': 'dex', 'difficulty': 'medium', 'harm': 'light'}
LOOK = '주위를 살핀다.'
# 한 사람이 라운드에 고르는 것. 글만 내기, 들쥐 하나나 영애를 죽이려고 치기, 다치게만 치기.
# 영애는 싸움이 붙은 다음 라운드부터 친다. 다치게 쳐서 싸움을 붙이고 다음에 죽이는 열이 자주 나오게 영애를 자주 고른다
CHOICES = ['look', 'rat-0', 'rat-1', 'lady', 'lady', 'lady-gently', 'lady-gently']
# 앉은 사람의 시트. 들쥐와 영애(민첩 10)보다 먼저 움직이고 잘 맞힌다. HP 가 적어 쓰러지는 일도 자주 생긴다
FIGHTER = make_sheet(max_hp=5, str=18, dex=14)
# 서 있는 사람의 행동을 받지 않는 까닭. 죽은 것이나 장면에 없는 것을 치거나, 행동을 막는 부상(기절 같은 것)을 입었다.
# 그때는 글로 다시 낸다
REFUSED = {'npc_dead', 'monster_dead', 'action.monster', 'action.npc', 'character_incapacitated'}


class SeededDice:
    """씨앗으로 정한 난수의 주사위. 같은 씨앗이면 같은 눈을 같은 차례로 낸다."""

    def __init__(self, seed: int) -> None:
        self._random = random.Random(seed)

    def roll(self, sides: int) -> int:
        return self._random.randint(1, sides)


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key) -> dict[str, str]:
    return bearer(signing_key, FRIEND)


plans = st.lists(st.tuples(st.sampled_from(CHOICES), st.sampled_from(CHOICES), st.booleans()), min_size=1, max_size=6)


async def fighting_table(client: AsyncClient, me: dict, friend: dict) -> tuple[dict, dict]:
    """들쥐 둘이 물고 악역영애가 치는 판으로 둘이 앉아 시작한 테이블."""
    world = await make_world(client, me)
    fields = {
        'default_sheet': FIGHTER,
        'monster_sheets': [{'monster_id': world['rat']['id'], 'sheet': SMALL, 'attacks': [BITE]}],
        'npc_sheets': [{'entry_id': world['lady']['id'], 'sheet': SMALL, 'attitude': 'hostile', 'attacks': [SWIPE]}],
    }
    table = await start(client, me, world, [], friend, **fields)
    return world, table


async def events(client: AsyncClient, me: dict, table: dict) -> list[dict]:
    """테이블의 이벤트를 모두 적힌 차례로."""
    found, after = [], None
    while True:
        params = {'limit': 100} if after is None else {'limit': 100, 'after': after}
        response = await client.get(table_url(table, '/events'), params=params, headers=me)
        assert response.status_code == status.HTTP_200_OK, response.text
        page = response.json()['items']
        found.extend(page)
        if len(page) < 100:
            return found
        after = page[-1]['sequence']


async def scene_monsters(client: AsyncClient, me: dict, table: dict) -> list[str]:
    response = await client.get(table_url(table, '/rounds/current/people'), headers=me)
    assert response.status_code == status.HTTP_200_OK, response.text
    return [monster['id'] for monster in response.json()['monsters']]


def action_for(choice: str, world: dict, rats: list[str]) -> dict | None:
    """고른 것의 행동. 글만 내면 None 이다."""
    if choice == 'look':
        return None
    if choice.startswith('rat-'):
        index = int(choice.removeprefix('rat-'))
        return strike(monster=rats[index]) if index < len(rats) else None
    return {**strike(npc=world['lady']['id']), 'lethal': choice == 'lady'}


def reason_of(response) -> str:
    """거절의 까닭. 409 는 reason, 422 는 틀린 칸(detail 의 첫 낱말)이다."""
    body = response.json()
    return body['reason'] if response.status_code == status.HTTP_409_CONFLICT else body['detail'].split()[0]


async def send(client: AsyncClient, headers: dict, table: dict, action: dict | None):
    body = {'content': LOOK} if action is None else {'content': '친다.', 'action': action}
    return await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=headers)


async def declare(client: AsyncClient, headers: dict, table: dict, member: dict, action: dict | None) -> None:
    """
    한 사람의 선언. 쓰러졌으면 행동은 막히고 글만 받는다. 죽은 것을 치는 행동과, 행동을 막는 부상을 입은 사람의 행동도
    받지 않는다. 그때는 글로 다시 낸다.
    """
    if action is not None:
        response = await send(client, headers, table, action)
        if member['sheet']['hp'] == 0:
            assert (response.status_code, reason_of(response)) == (status.HTTP_409_CONFLICT, 'character_downed')
        elif response.status_code != status.HTTP_200_OK:
            assert reason_of(response) in REFUSED, response.text
        else:
            return
    response = await send(client, headers, table, None)
    assert response.status_code == status.HTTP_200_OK, response.text


def members_of(seen: dict) -> dict[str, dict]:
    return {member['user_id']: member for member in seen['members']}


async def close_twice(client: AsyncClient, me: dict, table: dict) -> None:
    """방장이 닫기를 한꺼번에 두 번 보낸다. 하나만 받는다."""
    url = table_url(table, '/rounds/current/close')
    first, second = await asyncio.gather(client.post(url, headers=me), client.post(url, headers=me))
    assert sorted([first.status_code, second.status_code]) == [status.HTTP_202_ACCEPTED, status.HTTP_409_CONFLICT]


async def current_round(client: AsyncClient, me: dict, table: dict) -> dict:
    response = await client.get(table_url(table, '/rounds/current'), headers=me)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def current_number(client: AsyncClient, me: dict, table: dict) -> int:
    return (await current_round(client, me, table))['number']


async def is_open(client: AsyncClient, me: dict, table: dict) -> bool:
    """지금 라운드가 아직 선언을 받는가."""
    return (await current_round(client, me, table))['status'] == 'open'


def check_rounds_closed_once(log: list[dict], played: int, current: int) -> None:
    numbers = [event['payload']['number'] for event in log if event['type'] == 'round_closed']
    assert numbers == list(range(1, played + 1))
    assert current == played + 1


def check_the_dead_do_not_act(log: list[dict]) -> None:
    """죽은 것이 적힌 뒤에 그것의 공격이 없다. 몬스터는 마리의 id, 인물은 항목의 id 로 가른다."""
    died: dict[str, int] = {}
    for event in log:
        payload = event['payload']
        if event['type'] in ('monster_changed', 'npc_changed') and payload['status'] == 'dead':
            key = payload.get('monster_id') or payload['entry_id']
            died.setdefault(key, event['sequence'])
        if event['type'] in ('monster_attacked', 'npc_attacked'):
            key = payload.get('monster_id') or payload['entry_id']
            assert key not in died, f'죽은 {payload["name"]} 가 쳤다: {event}'


def check_hp_in_range(seen: dict) -> None:
    for member in seen['members']:
        sheet = member['sheet']
        assert 0 <= sheet['hp'] <= sheet['max_hp']


@given(plan=plans, seed=st.integers(min_value=0, max_value=2**32 - 1))
# 늘 도는 판 둘. 무작위로는 드물게만 닿는 갈래를 매번 지나게 한다
# 라운드 4 에 쓰러진 기사가 들쥐를 치려 한다(글만 받는다)
@example(
    plan=[('look', 'rat-0', False), ('look', 'look', False), ('look', 'look', False), ('rat-0', 'look', False)],
    seed=156522,
)
# 라운드 1 에 약사가 쓰러진다. 라운드 2 는 내 선언만으로 닫힌다
@example(plan=[('look', 'rat-0', False), ('look', 'look', True)], seed=0)
# 라운드 1 에 들쥐 하나가 먼저 죽고 제 차례를 맞는다(치지 않는다)
@example(plan=[('rat-0', 'rat-0', False)], seed=0)
# 라운드 2 에 영애가 먼저 죽고 제 차례를 맞는다(치지 않는다)
@example(plan=[('rat-0', 'lady', False), ('look', 'lady', False)], seed=989)
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
async def test_a_random_game_keeps_the_round_invariants(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated, plan, seed: int
):
    app.state.dice = SeededDice(seed)
    world, table = await fighting_table(client, me, friend)
    for played, (mine, theirs, twice) in enumerate(plan, start=1):
        seen = await read_table(client, me, table)
        members = members_of(seen)
        if any(member['sheet']['dead'] for member in members.values()):
            # 죽은 캐릭터는 새 캐릭터를 들여야 선언한다. 이 판은 여기까지다
            break
        rats = await scene_monsters(client, me, table)
        await declare(client, me, table, members[str(ME)], action_for(mine, world, rats))
        # 쓰러진 사람은 기다리지 않는다. 약사가 쓰러져 있으면 내 선언으로 라운드가 닫힌다
        if await is_open(client, me, table):
            if twice:
                await close_twice(client, me, table)
            else:
                await declare(client, friend, table, members[str(FRIEND)], action_for(theirs, world, rats))
        await narrated()

        seen = await read_table(client, me, table)
        log = await events(client, me, table)
        check_rounds_closed_once(log, played, await current_number(client, me, table))
        check_the_dead_do_not_act(log)
        check_hp_in_range(seen)
