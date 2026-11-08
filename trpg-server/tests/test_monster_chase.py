# trpg-server/tests/test_monster_chase.py

"""
쫓아오는 몬스터(#254, app/rounds/monster_chase.py)를 검증한다.

판은 여기서 만든다. 장소는 수로 입구(시작), 배수로, 구덩이다.
입구–배수로는 그냥 가는 길, 입구–구덩이는 넘기 판정(근력)이 있는 길이다.
입구에 들개 한 마리가 있다(야수, 최대 HP 4, 물기: 근력 보통 가벼움). 들개의 시트에 쫓아온다고 적는다
(쫓지 않는 판은 적지 않는다). 캐릭터와 들개의 능력치는 모두 10(보정 0)이다.
주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다. 차례가 같은 점수면 앉은 사람, 몬스터의 순서로 차례의 주사위를 굴린다.

보는 것.
  - 엘프가 먼저 입구를 떠나면 들개가 그 차례에 배수로로 따라온다. 치지 않는다. monster_chased 가 적힌다
  - 다음 라운드에는 같은 장소라 들개가 친다
  - 쫓지 않는 몬스터는 그 자리에 남는다(칠 사람이 없다)
  - 들개의 차례가 먼저 오면 그 자리에서 치고, 엘프가 떠난 뒤에도 따라가지 않는다
  - 넘기 판정이 있는 길로 도망치면 따라가지 못한다
  - 서술의 줄과 기록의 글
  - 흩어져 도망치면 마지막으로 싸운 사람을 쫓는다(DB 를 쓰지 않는 작은 함수)
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.dice import ScriptedDice
from app.rounds import monster_chase
from app.rounds.move_lines import describe_monster_turn
from app.rounds.narration_request import to_monster_turn
from app.tables.models import TableMonster
from app.transcripts.story import chased
from tests.sheets import SHEET, make_sheet
from tests.test_monster_turns import (
    BESTIARIES_URL,
    LOREBOOKS_URL,
    ME,
    RULEBOOKS_URL,
    SCENARIOS_URL,
    TABLES_URL,
    bearer,
    declare,
    events_of,
    load_dice,
    post,
    table_url,
    turns_of,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

BITE = {'name': '물기', 'ability': 'str', 'difficulty': 'medium', 'harm': 'light'}
CLIMB = {'ability': 'str'}
# 차례의 주사위. 큰 눈이 먼저다
EARLY, LATE = 20, 1
# 들개의 물기(빗나감), 넘기 판정(넘음), 판정하는 행동의 눈(아무거나)
MISS, CLIMBED, ANY = 1, 20, 10
CHECK = {'kind': 'check', 'ability': 'dex', 'difficulty': 'medium'}


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    return bearer(signing_key, ME)


async def make_world(client: AsyncClient, me: dict) -> dict:
    """수로 입구, 배수로, 구덩이가 든 로어북. 들개가 든 도감. 룰북."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='지하 수로')
    url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'
    bestiary = await post(client, BESTIARIES_URL, me, title='지하 수로의 것들')
    return {
        'lorebook': lorebook,
        'bestiary': bestiary,
        'gate': await post(client, url, me, name='수로 입구', kind='place'),
        'drain': await post(client, url, me, name='배수로', kind='place'),
        'pit': await post(client, url, me, name='구덩이', kind='place'),
        'dog': await post(client, f'{BESTIARIES_URL}/{bestiary["id"]}/monsters', me, name='들개', kind='beast'),
        'rulebook': await post(client, RULEBOOKS_URL, me, title='룰북'),
    }


async def dog_table(client: AsyncClient, me: dict, chases: bool = True) -> dict:
    """입구에 들개 한 마리가 있는 테이블. 나 혼자 앉는다."""
    world = await make_world(client, me)
    gate, drain, pit = world['gate']['id'], world['drain']['id'], world['pit']['id']
    dog = {'monster_id': world['dog']['id'], 'sheet': make_sheet(max_hp=4), 'attacks': [BITE], 'chases': chases}
    body = {
        'title': '지하 수로',
        'rulebook_id': world['rulebook']['id'],
        'lorebook_ids': [world['lorebook']['id']],
        'bestiary_ids': [world['bestiary']['id']],
        'openings': ['물 떨어지는 소리가 난다.'],
        'default_sheet': SHEET,
        'start_place': gate,
        'routes': [{'from_place': gate, 'to_place': drain}, {'from_place': gate, 'to_place': pit, 'cross': CLIMB}],
        'monster_sheets': [dog],
        'encounters': [{'place_id': gate, 'monster_id': world['dog']['id'], 'count': 1}],
    }
    scenario = await post(client, SCENARIOS_URL, me, **body)
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return {**world, 'table': table}


async def act(client: AsyncClient, me: dict, world: dict, narrated, action: dict) -> None:
    """나 혼자 앉은 테이블에서 선언해 라운드를 닫고 서술을 기다린다."""
    await declare(client, me, world['table'], '움직인다.', action)
    await narrated()


def go(world: dict, place: str) -> dict:
    return {'kind': 'move', 'place': world[place]['id']}


def dog_turn(turns: list[dict]) -> dict:
    return next(turn for turn in turns if turn['kind'] == 'monster')


async def dog_place(session: AsyncSession) -> str:
    row = await session.scalar(select(TableMonster).execution_options(populate_existing=True))
    return str(row.place_id)


async def test_a_chasing_monster_follows_one_step_and_does_not_strike(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await dog_table(client, me)
    # 차례의 주사위(엘프가 먼저, 들개). 엘프는 굴리지 않고 가고, 들개는 따라오기만 한다
    dice = load_dice(app, [EARLY, LATE])

    await act(client, me, world, narrated, go(world, 'drain'))

    assert dice.remaining == 0
    outcome = dog_turn(await turns_of(session, world['table']))['outcome']
    assert outcome == {
        'chased': {
            'user_id': str(ME),
            'character_name': '엘프',
            'from_place': {'entry_id': world['gate']['id'], 'name': '수로 입구'},
            'to_place': {'entry_id': world['drain']['id'], 'name': '배수로'},
        }
    }
    assert await dog_place(session) == world['drain']['id']
    seen = await events_of(client, me, world['table'])
    assert not any(event['type'] == 'monster_attacked' for event in seen)
    followed = next(event for event in seen if event['type'] == 'monster_chased')
    assert followed['payload']['name'] == '들개'
    assert followed['payload']['to_place'] == {'entry_id': world['drain']['id'], 'name': '배수로'}
    assert followed['caused_by_sequence'] is None


async def test_the_next_round_it_strikes_where_it_followed(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await dog_table(client, me)
    load_dice(app, [EARLY, LATE])
    await act(client, me, world, narrated, go(world, 'drain'))
    # 차례의 주사위(엘프, 들개), 엘프의 판정, 들개의 물기(빗나감)
    dice = load_dice(app, [EARLY, LATE, ANY, MISS])

    await act(client, me, world, narrated, CHECK)

    assert dice.remaining == 0
    outcome = dog_turn(await turns_of(session, world['table'], number=2))['outcome']
    assert (outcome['attack']['name'], outcome['success']) == ('물기', False)


async def test_a_monster_that_does_not_chase_stays(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await dog_table(client, me, chases=False)
    load_dice(app, [EARLY, LATE])

    await act(client, me, world, narrated, go(world, 'drain'))

    assert dog_turn(await turns_of(session, world['table']))['outcome'] == {'skipped': 'no_target'}
    assert await dog_place(session) == world['gate']['id']


async def test_a_monster_whose_turn_comes_first_strikes_and_stays(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await dog_table(client, me)
    # 차례의 주사위(엘프가 나중, 들개가 먼저), 들개의 물기(빗나감)
    dice = load_dice(app, [LATE, EARLY, MISS])

    await act(client, me, world, narrated, go(world, 'drain'))

    assert dice.remaining == 0
    outcome = dog_turn(await turns_of(session, world['table']))['outcome']
    assert 'chased' not in outcome and outcome['success'] is False
    assert await dog_place(session) == world['gate']['id']
    # 다음 라운드에는 엘프가 처음부터 다른 곳에 있다. 쫓지 않는다(장면에 들개가 없어 차례도 없다)
    load_dice(app, [ANY])
    await act(client, me, world, narrated, CHECK)
    assert await dog_place(session) == world['gate']['id']


async def test_it_cannot_follow_over_a_climb(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await dog_table(client, me)
    # 차례의 주사위(엘프, 들개), 엘프의 넘기(넘음)
    dice = load_dice(app, [EARLY, LATE, CLIMBED])

    await act(client, me, world, narrated, go(world, 'pit'))

    assert dice.remaining == 0
    assert dog_turn(await turns_of(session, world['table']))['outcome'] == {'skipped': 'no_target'}
    assert await dog_place(session) == world['gate']['id']


async def test_a_new_monster_sheet_does_not_chase(client: AsyncClient, me: dict):
    world = await make_world(client, me)
    sheet = {'monster_id': world['dog']['id'], 'sheet': make_sheet(max_hp=4)}
    scenario = await post(client, SCENARIOS_URL, me, title='수로', monster_sheets=[sheet])

    assert scenario['monster_sheets'][0]['chases'] is False


# --- 서술과 기록 ---


CHASE_TURN = {
    'kind': 'monster',
    'monster_id': str(uuid.uuid4()),
    'name': '들개',
    'outcome': {
        'chased': {
            'user_id': str(ME),
            'character_name': '엘프',
            'from_place': {'entry_id': str(uuid.uuid4()), 'name': '수로 입구'},
            'to_place': {'entry_id': str(uuid.uuid4()), 'name': '배수로'},
        }
    },
}


def test_the_turn_line_tells_the_chase():
    note = to_monster_turn(CHASE_TURN)

    assert (note.chased, note.target, note.hit) == ('배수로', '엘프', False)
    assert describe_monster_turn(note) == '들개: 엘프을(를) 쫓아 배수로까지 따라옴 (치지 않음)'


def test_the_record_tells_who_and_where():
    payload = {'name': '들개', **CHASE_TURN['outcome']['chased']}

    [note] = chased(payload, labels=None)

    assert note.text == '들개: 엘프을(를) 쫓아옴 · 수로 입구 → 배수로'


# --- 쫓을 사람 ---


def runaway(user_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(user_id=user_id)


def monster_with(last_foe: uuid.UUID | None) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(last_foe=last_foe))


def test_it_chases_the_last_foe_among_those_who_fled():
    first, last = runaway(uuid.uuid4()), runaway(uuid.uuid4())
    judging = SimpleNamespace(dice=ScriptedDice([]))

    assert monster_chase.pick_quarry(judging, monster_with(last.user_id), [first, last]) is last


def test_without_a_last_foe_among_them_the_dice_pick():
    first, second = runaway(uuid.uuid4()), runaway(uuid.uuid4())
    judging = SimpleNamespace(dice=ScriptedDice([2]))

    assert monster_chase.pick_quarry(judging, monster_with(uuid.uuid4()), [first, second]) is second
    assert judging.dice.remaining == 0
