# trpg-server/tests/test_wander_rolls.py

"""
무작위 조우(#283)를 테이블이 굴리는 것을 검증한다. 표를 적고 게시하는 것은 tests/test_wanders.py 가 본다.

혼자 앉은 테이블이다. 수로 입구에서 시작하고, 깊은 수로로 가는 길(한 시간)과 우물로 가는 길(시간이 안 든다)이 있다.
몬스터는 쥐와 해골이다. 둘 다 공격이 없어 차례를 받지 않는다(주사위는 조우의 굴림만 쓴다). 혼자라 선언하면 닫힌다.

보는 것.
  - 길: 걸리는 시간이 있는 길로 와서 닿으면 그 장소의 표로 굴린다. 확률 이하면 줄을 몫대로 뽑아 몬스터를 놓는다.
    시간이 안 드는 길과 가지 못한 길은 굴리지 않는다.
  - 쉬기: 길게 쉬면 굴린다. 나오면 쉬기가 깨지고(ambushed) 몬스터가 기습한다. 짧게 쉬면 굴리지 않는다.
  - 표 고르기: 그 장소의 표가 있으면 그것(확률 0 이면 안전), 없으면 판의 기본 표. 하루의 때가 맞아야 한다.
  - 살아 있는 몬스터가 있는 곳에는 더 오지 않는다. 번호는 같은 몬스터 뒤로 잇는다.
  - 기록: monsters_appeared 이벤트, 서술의 한 일의 줄, 기록의 글, 다음 라운드의 장면.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Surprise
from app.rounds import initiative, prompt
from app.rounds.move_lines import REST_BREAKS, describe_move, describe_wander
from app.rounds.narrator import Move, WanderNote
from app.tables.models import TableMonster
from app.transcripts.labels import Labels
from app.transcripts.markdown import render_event
from tests import test_monster_turns as turns
from tests.sheets import SHEET, make_sheet
from tests.test_table_map import put_at
from tests.test_transcript_markdown import event
from tests.transcript_samples import SAMPLES

pytestmark = pytest.mark.usefixtures('clean_tables')

me = turns.me
friend = turns.friend
ME = turns.ME
FRIEND = turns.FRIEND
post = turns.post
table_url = turns.table_url
load_dice = turns.load_dice
LOREBOOKS_URL = turns.LOREBOOKS_URL
BESTIARIES_URL = turns.BESTIARIES_URL
RULEBOOKS_URL = turns.RULEBOOKS_URL
SCENARIOS_URL = turns.SCENARIOS_URL
TABLES_URL = turns.TABLES_URL

HOUR = 60
NIGHT = {'start_day': 1, 'start_hour': 22, 'round_minutes': 10}


@pytest.fixture
async def world(client: AsyncClient, me: dict) -> dict:
    """장소 셋(수로 입구, 깊은 수로, 우물)과 몬스터 둘(쥐, 해골)."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='지하 수로')
    entries = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'
    bestiary = await post(client, BESTIARIES_URL, me, title='지하 수로의 것들')
    monsters = f'{BESTIARIES_URL}/{bestiary["id"]}/monsters'
    return {
        'lorebook': lorebook,
        'bestiary': bestiary,
        'gate': await post(client, entries, me, name='수로 입구', kind='place'),
        'deep': await post(client, entries, me, name='깊은 수로', kind='place'),
        'well': await post(client, entries, me, name='우물', kind='place'),
        'rat': await post(client, monsters, me, name='수로 쥐', kind='beast'),
        'skeleton': await post(client, monsters, me, name='해골 병사', kind='undead'),
    }


def line(monster: dict, count: int = 1, weight: int = 1, surprise: str = 'none') -> dict:
    return {'monster_id': monster['id'], 'count': count, 'weight': weight, 'surprise': surprise}


def table(place: dict | None, chance: int, *lines: dict, times: list[str] | None = None) -> dict:
    return {
        'place_id': None if place is None else place['id'],
        'times': times or [],
        'chance': chance,
        'monsters': list(lines),
    }


async def start(client: AsyncClient, me: dict, world: dict, wanders: list[dict], *others: dict, **fields) -> dict:
    """그 표들을 둔 시나리오로 나와 others 가 앉아 시작한 테이블. 모두 수로 입구에 선다."""
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북')
    body = {
        'title': '지하 수로',
        'rulebook_id': rulebook['id'],
        'lorebook_ids': [world['lorebook']['id']],
        'bestiary_ids': [world['bestiary']['id']],
        'openings': ['물 떨어지는 소리가 난다.'],
        'default_sheet': SHEET,
        'monster_sheets': [
            {'monster_id': world['rat']['id'], 'sheet': make_sheet(max_hp=4), 'attacks': []},
            {'monster_id': world['skeleton']['id'], 'sheet': make_sheet(max_hp=13), 'attacks': []},
        ],
        'start_place': world['gate']['id'],
        'routes': [
            {'from_place': world['gate']['id'], 'to_place': world['deep']['id'], 'travel_minutes': HOUR},
            {'from_place': world['gate']['id'], 'to_place': world['well']['id']},
        ],
        'wanders': wanders,
        **fields,
    }
    scenario = await post(client, SCENARIOS_URL, me, **body)
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)
    made = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1 + len(others))
    for headers, name in zip([me, *others], ['엘프', '드워프 기사'], strict=False):
        if headers is not me:
            await client.post(f'{TABLES_URL}/join', json={'invite_code': made['invite_code']}, headers=headers)
        await client.put(table_url(made, '/character'), json={'name': name}, headers=headers)
    started = await client.post(table_url(made, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return made


def going(place: dict) -> dict:
    return {'kind': 'move', 'place': place['id']}


def resting(length: str = 'long') -> dict:
    return {'kind': 'rest', 'length': length}


async def act(client: AsyncClient, me: dict, the_table: dict, action: dict, narrated) -> None:
    """혼자라 선언하면 라운드가 닫힌다. 서술까지 기다린다."""
    await turns.declare(client, me, the_table, '간다.', action)
    await narrated()


async def monsters_at(session: AsyncSession, the_table: dict) -> list[tuple[str, int, str, str | None]]:
    """테이블의 몬스터들. (장소, 번호, 몬스터, 기습)이다. 몬스터와 번호의 순서다."""
    query = (
        select(TableMonster)
        .where(TableMonster.table_id == uuid.UUID(the_table['id']))
        .order_by(TableMonster.monster_id, TableMonster.number)
        .execution_options(populate_existing=True)
    )
    return [(str(row.place_id), row.number, str(row.monster_id), row.surprise) for row in await session.scalars(query)]


async def appeared(client: AsyncClient, me: dict, the_table: dict) -> list[dict]:
    return [
        item['payload'] for item in await turns.events_of(client, me, the_table) if item['type'] == 'monsters_appeared'
    ]


async def round_of(client: AsyncClient, me: dict, the_table: dict, number: int = 1) -> dict:
    response = await client.get(table_url(the_table, f'/rounds/{number}'), headers=me)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


# --- 길 ---


async def test_arriving_by_a_long_road_may_meet_monsters(
    client: AsyncClient, app: FastAPI, me: dict, world: dict, session: AsyncSession, narrated
):
    the_table = await start(client, me, world, [table(world['deep'], 40, line(world['rat'], 3))])
    dice = load_dice(app, [40, 1])

    await act(client, me, the_table, going(world['deep']), narrated)

    deep, rat = world['deep']['id'], world['rat']['id']
    assert await monsters_at(session, the_table) == [(deep, n, rat, 'none') for n in (1, 2, 3)]
    assert dice.remaining == 0
    (payload,) = await appeared(client, me, the_table)
    assert payload == {
        'round': 1,
        'place': {'entry_id': deep, 'name': '깊은 수로'},
        'monster': {'id': rat, 'name': '수로 쥐'},
        'count': 3,
        'cause': 'arrive',
        'surprise': 'none',
    }
    (move,) = await turns.moves_of(session, the_table)
    assert move['wander'] == {'monster': '수로 쥐', 'count': 3, 'cause': 'arrive'}
    # 다음 라운드의 장면에 나온다
    assert [monster['name'] for monster in await turns.monsters_of(client, me, the_table)] == [
        '수로 쥐 1',
        '수로 쥐 2',
        '수로 쥐 3',
    ]


async def test_a_roll_over_the_chance_meets_nothing(
    client: AsyncClient, app: FastAPI, me: dict, world: dict, session: AsyncSession, narrated
):
    the_table = await start(client, me, world, [table(world['deep'], 40, line(world['rat'], 3))])
    dice = load_dice(app, [41])

    await act(client, me, the_table, going(world['deep']), narrated)

    assert await monsters_at(session, the_table) == []
    assert dice.remaining == 0
    assert await appeared(client, me, the_table) == []
    (move,) = await turns.moves_of(session, the_table)
    assert move['wander'] is None


@pytest.mark.parametrize('case', ['road-without-time', 'staying'])
async def test_nothing_is_rolled_without_a_long_road_or_a_long_rest(
    client: AsyncClient, app: FastAPI, me: dict, world: dict, session: AsyncSession, narrated, case: str
):
    the_table = await start(client, me, world, [table(None, 100, line(world['rat']))])
    dice = load_dice(app, [1, 1, 1])
    action = going(world['well']) if case == 'road-without-time' else resting('short')

    await act(client, me, the_table, action, narrated)

    # 짧은 휴식은 회복의 주사위 하나만 굴린다
    assert dice.remaining == (3 if case == 'road-without-time' else 2)
    assert await monsters_at(session, the_table) == []


@pytest.mark.parametrize(('roll', 'picked'), [(2, 'rat'), (3, 'skeleton')])
async def test_the_lines_are_picked_by_weight(
    client: AsyncClient, app: FastAPI, me: dict, world: dict, session: AsyncSession, narrated, roll: int, picked: str
):
    lines = [line(world['rat'], 2, weight=2), line(world['skeleton'], 1, weight=1, surprise='party')]
    the_table = await start(client, me, world, [table(world['deep'], 100, *lines)])
    # 몫의 합은 3 이다. 1~2 는 쥐, 3 은 해골이다
    load_dice(app, [100, roll])

    await act(client, me, the_table, going(world['deep']), narrated)

    expected = {
        'rat': [(world['deep']['id'], n, world['rat']['id'], 'none') for n in (1, 2)],
        'skeleton': [(world['deep']['id'], 1, world['skeleton']['id'], 'party')],
    }[picked]
    assert await monsters_at(session, the_table) == expected


async def test_a_place_is_rolled_once_even_when_one_rests_and_one_arrives(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, world: dict, session: AsyncSession, narrated
):
    the_table = await start(client, me, world, [table(world['deep'], 50, line(world['rat']))], friend)
    await put_at(session, the_table, FRIEND, world['deep'])
    # 쉬기로 한 번만 굴린다. 빗나가면 닿은 것으로 다시 굴리지 않는다
    dice = load_dice(app, [99])

    await turns.declare(client, me, the_table, '간다.', going(world['deep']))
    await turns.declare(client, friend, the_table, '잔다.', resting())
    await narrated()

    assert dice.remaining == 0
    assert await monsters_at(session, the_table) == []


async def test_only_those_at_the_place_hear_of_the_wanderers(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, world: dict, session: AsyncSession, narrated
):
    the_table = await start(client, me, world, [table(world['deep'], 100, line(world['rat']))], friend)
    load_dice(app, [100, 1])

    await turns.declare(client, me, the_table, '간다.', going(world['deep']))
    await turns.declare(client, friend, the_table, '남는다.')
    await narrated()

    mine, theirs = await turns.moves_of(session, the_table)
    assert (mine['wander']['monster'], theirs['wander']) == ('수로 쥐', None)
    line_of_mine = describe_move(Move(character_name='엘프', content='간다.', wander=WanderNote(**mine['wander'])))
    assert '(조우: 수로 쥐 1마리가 나타났다)' in line_of_mine


# --- 쉬기 ---


async def test_a_long_rest_may_be_broken_by_monsters_that_ambush(
    client: AsyncClient, app: FastAPI, me: dict, world: dict, session: AsyncSession, narrated
):
    the_table = await start(client, me, world, [table(None, 30, line(world['skeleton'], surprise='party'))])
    await session.execute(
        text('UPDATE table_sheets SET hp = 3 WHERE table_id = :table_id'), {'table_id': the_table['id']}
    )
    await session.commit()
    load_dice(app, [30, 1])

    await act(client, me, the_table, resting(), narrated)

    # 줄에 일행의 기습을 적었어도 쉬는 중에 나온 것은 몬스터가 기습한다
    assert await monsters_at(session, the_table) == [(world['gate']['id'], 1, world['skeleton']['id'], 'monsters')]
    rest = next(item for item in (await round_of(client, me, the_table))['declarations'])['outcome']['rest']
    assert (rest['rested'], rest['reason'], rest['after']) == (False, 'ambushed', 3)
    (payload,) = await appeared(client, me, the_table)
    assert (payload['cause'], payload['surprise']) == ('rest', 'monsters')
    (move,) = await turns.moves_of(session, the_table)
    assert move['wander']['cause'] == 'rest'


async def test_an_undisturbed_long_rest_recovers(
    client: AsyncClient, app: FastAPI, me: dict, world: dict, session: AsyncSession, narrated
):
    the_table = await start(client, me, world, [table(None, 30, line(world['skeleton']))])
    await session.execute(
        text('UPDATE table_sheets SET hp = 3 WHERE table_id = :table_id'), {'table_id': the_table['id']}
    )
    await session.commit()
    load_dice(app, [31])

    await act(client, me, the_table, resting(), narrated)

    rest = next(item for item in (await round_of(client, me, the_table))['declarations'])['outcome']['rest']
    assert (rest['rested'], rest['reason'], rest['after']) == (True, None, SHEET['max_hp'])


# --- 표 고르기 ---


async def test_a_place_with_its_own_safe_table_does_not_fall_back_to_the_default(
    client: AsyncClient, app: FastAPI, me: dict, world: dict, session: AsyncSession, narrated
):
    wanders = [table(world['gate'], 0), table(None, 100, line(world['rat']))]
    the_table = await start(client, me, world, wanders)
    dice = load_dice(app, [1, 1])

    await act(client, me, the_table, resting(), narrated)

    assert dice.remaining == 2
    assert await monsters_at(session, the_table) == []


async def test_the_default_table_serves_places_without_one(
    client: AsyncClient, app: FastAPI, me: dict, world: dict, session: AsyncSession, narrated
):
    wanders = [table(world['gate'], 0), table(None, 100, line(world['rat']))]
    the_table = await start(client, me, world, wanders)
    load_dice(app, [100, 1])

    await act(client, me, the_table, going(world['deep']), narrated)

    assert [place for place, *_ in await monsters_at(session, the_table)] == [world['deep']['id']]


async def test_a_place_with_tables_only_for_some_times_does_not_fall_back_to_the_default(
    client: AsyncClient, app: FastAPI, me: dict, world: dict, session: AsyncSession, narrated
):
    # 깊은 수로에는 밤의 표만 있다. 아침에 닿으면 기본 표로 내려가지 않고 조우가 없다
    wanders = [
        table(world['deep'], 100, line(world['rat']), times=['night']),
        table(None, 100, line(world['skeleton'])),
    ]
    the_table = await start(client, me, world, wanders)
    dice = load_dice(app, [100, 1])

    await act(client, me, the_table, going(world['deep']), narrated)

    assert dice.remaining == 2
    assert await monsters_at(session, the_table) == []


@pytest.mark.parametrize(('clock', 'met'), [(None, False), (NIGHT, True)])
async def test_a_table_is_used_only_at_its_time_of_day(
    client: AsyncClient, app: FastAPI, me: dict, world: dict, session: AsyncSession, narrated, clock, met: bool
):
    # 기본 시계는 아침 8시다. 한 시간 길을 와도 아침이다. 밤 10시에 떠나면 밤 11시에 닿는다
    fields = {} if clock is None else {'clock': clock}
    wanders = [table(world['deep'], 100, line(world['rat']), times=['night'])]
    the_table = await start(client, me, world, wanders, **fields)
    dice = load_dice(app, [100, 1])

    await act(client, me, the_table, going(world['deep']), narrated)

    assert bool(await monsters_at(session, the_table)) is met
    assert dice.remaining == (0 if met else 2)


async def test_the_arrival_time_decides_the_time_of_day(
    client: AsyncClient, app: FastAPI, me: dict, world: dict, session: AsyncSession, narrated
):
    # 밤 8시 반에 떠나 한 시간 걸려 9시 반(밤)에 닿는다. 떠날 때는 저녁이다
    wanders = [table(world['deep'], 100, line(world['rat']), times=['night'])]
    clock = {'start_day': 1, 'start_hour': 20, 'round_minutes': 10}
    the_table = await start(client, me, world, wanders, clock=clock)
    await session.execute(
        text('UPDATE table_clocks SET minutes = minutes + 30 WHERE table_id = :table_id'), {'table_id': the_table['id']}
    )
    await session.commit()
    load_dice(app, [100, 1])

    await act(client, me, the_table, going(world['deep']), narrated)

    assert len(await monsters_at(session, the_table)) == 1


# --- 이미 있는 몬스터 ---


async def test_no_more_come_where_monsters_are_alive_and_numbers_go_on(
    client: AsyncClient, app: FastAPI, me: dict, world: dict, session: AsyncSession, narrated
):
    encounters = [{'place_id': world['deep']['id'], 'monster_id': world['rat']['id'], 'count': 2}]
    wanders = [table(world['deep'], 100, line(world['rat'], 2))]
    the_table = await start(client, me, world, wanders, encounters=encounters)
    dice = load_dice(app, [100, 1])

    await act(client, me, the_table, going(world['deep']), narrated)

    # 쥐 둘이 살아 있어 굴리지 않았다
    assert dice.remaining == 2
    assert len(await monsters_at(session, the_table)) == 2


async def test_numbers_go_on_after_the_dead(
    client: AsyncClient, app: FastAPI, me: dict, world: dict, session: AsyncSession, narrated
):
    encounters = [{'place_id': world['deep']['id'], 'monster_id': world['rat']['id'], 'count': 2}]
    wanders = [table(world['deep'], 100, line(world['rat'], 2))]
    the_table = await start(client, me, world, wanders, encounters=encounters)
    await session.execute(
        text("UPDATE table_monsters SET status = 'dead', hp = 0 WHERE table_id = :table_id"),
        {'table_id': the_table['id']},
    )
    await session.commit()
    load_dice(app, [100, 1])

    await act(client, me, the_table, going(world['deep']), narrated)

    found = await monsters_at(session, the_table)
    assert [(number, surprise) for _, number, _, surprise in found] == [(1, None), (2, None), (3, 'none'), (4, 'none')]


# --- 기습과 서술과 기록 ---


def test_a_wandering_monster_uses_its_own_surprise():
    snapshot = SimpleNamespace(encounters=[SimpleNamespace(place_id='p', monster_id='m', surprise=Surprise.PARTY)])
    own = SimpleNamespace(state=SimpleNamespace(engaged_round=2, surprise='monsters', place_id='p', monster_id='m'))
    placed = SimpleNamespace(state=SimpleNamespace(engaged_round=2, surprise=None, place_id='p', monster_id='m'))

    assert initiative.surprise_of(snapshot, own, 2) == Surprise.MONSTERS
    assert initiative.surprise_of(snapshot, placed, 2) == Surprise.PARTY
    # 만난 첫 라운드가 지나면 기습이 없다
    assert initiative.surprise_of(snapshot, own, 3) == Surprise.NONE


def test_the_wander_lines():
    assert describe_wander(WanderNote(monster='수로 쥐', count=3, cause='arrive')) == '(조우: 수로 쥐 3마리가 나타났다)'
    assert describe_wander(WanderNote(monster='해골 병사', count=1, cause='rest')) == (
        '(조우: 쉬는 중에 해골 병사 1마리가 덮쳤다)'
    )
    assert REST_BREAKS['ambushed'] == '몬스터가 덮쳐 쉬지 못했다'


def test_the_monster_note_says_how_the_wanderers_came():
    assert "'조우'가 있으면 그 무리는 이번 라운드가 끝날 무렵 그 자리에 나타난 것이다" in prompt.MONSTER_NOTE
    assert prompt.PROMPT_VERSION == 'narration-81'


def test_the_transcript_says_the_monsters_appeared():
    assert render_event(event('monsters_appeared', SAMPLES['monsters_appeared']), Labels()) == (
        '- 조우: 깊은 수로 · 쉬는 중에 수로 쥐 3마리\n'
    )


async def test_the_event_carries_no_numbers_of_the_monsters(
    client: AsyncClient, app: FastAPI, me: dict, world: dict, session: AsyncSession, narrated
):
    the_table = await start(client, me, world, [table(world['deep'], 100, line(world['rat']))])
    load_dice(app, [100, 1])

    await act(client, me, the_table, going(world['deep']), narrated)

    # 마리의 숫자(HP, 능력치)는 싣지 않는다
    (payload,) = await appeared(client, me, the_table)
    assert set(payload) == {'round', 'place', 'monster', 'count', 'cause', 'surprise'}
