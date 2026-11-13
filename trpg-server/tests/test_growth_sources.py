# trpg-server/tests/test_growth_sources.py

"""
몬스터와 판의 사건이 주는 경험치(#286 ②, app/rounds/monster_xp.py, app/rounds/happenings.py)를 검증한다.

맵과 픽스처는 tests/test_quest_goals.py 의 것이다. 성문(시작)과 숲, 성문에 들쥐 둘(최대 HP 4).
나(기사)와 함께 앉는 사람(약사)이 성문에 선다. 룰북은 레벨표(GROWTH)를 적은 것으로 바꾼다.
주사위는 판정의 눈, 피해의 양의 눈 차례다(PASS 로 맞히고 DOWN 으로 쓰러뜨린다).

보는 것.
  - 시나리오: 몬스터 시트의 경험치, 사건의 경험치 주기, 나누는 법(xp_split, 기본 share)을 저장하고 판에 굳힌다.
    경험치를 주는데 룰북에 성장이 없으면 409 progression_missing.
    경험치 주기의 장소가 맵 밖이면 happening_place_off_map.
  - 몬스터: 쓰러뜨린 라운드에 그 장소의 죽지 않은 캐릭터가 받는다. 각자 다(each)와 나눔(share, 나머지는 버림).
    다른 장소로 간 사람은 받지 않는다. 한 마리는 한 번만 준다. 레벨이 오르면 character_leveled 가 잇는다.
  - 사건: 경험치 주기가 모두에게, 또는 한 장소에 선 사람에게 준다. 나누는 법은 시나리오의 것이다.
  - 이벤트 experience_gained: 무엇이 줬는지(source), 나누는 법(split), 받은 사람마다(gains). 행한 사람이 없다.
  - 마이그레이션: 이미 쓰러진 마리는 준 것으로 채우고, 되돌리면 경험치 주기만 남은 사건을 지운다.
"""

import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import XpSplit
from app.assets.scenarios.snapshot import read_snapshot
from app.tables.growth import share_of
from app.transcripts.markdown import render_event
from tests import test_quest_goals as quest_tests
from tests.test_quest_goals import (
    DOWN,
    PASS,
    RULEBOOKS_URL,
    SMALL,
    declare,
    load_dice,
    make_scenario,
    make_world,
    move,
    post,
    publish,
    rat_ids,
    start,
    strike,
)
from tests.test_table_items import FRIEND, ME, events_of, kill, read_table
from tests.test_transcript_markdown import LABELS, event

pytestmark = pytest.mark.usefixtures('clean_tables')

me = quest_tests.me
friend = quest_tests.friend

GROWTH = {'levels': [{'xp': 100, 'max_hp': 3, 'points': 1}, {'xp': 300, 'max_hp': 3, 'points': 1}]}


async def growing_world(client: AsyncClient, me: dict) -> dict:
    """test_quest_goals 의 세계에 레벨표를 적은 룰북을 끼운다."""
    world = await make_world(client, me)
    return {**world, 'rulebook': await post(client, RULEBOOKS_URL, me, title='자라는 룰북', progression=GROWTH)}


def rats(world: dict, xp: int) -> list[dict]:
    """경험치 xp 를 주는 들쥐의 시트."""
    return [{'monster_id': world['rat']['id'], 'sheet': SMALL, 'xp': xp}]


def giving(world: dict, amount: int, from_place: dict | None = None) -> list[dict]:
    """성문에 닿으면(처음부터 닿아 있다) 경험치를 주는 사건(숨은 비밀)."""
    effect = {'kind': 'give_xp', 'amount': amount, **({'from_place': from_place['id']} if from_place else {})}
    when = [{'kind': 'reach_place', 'target': world['gate']['id']}]
    return [{'entry_id': world['secret']['id'], 'when': when, 'effects': [effect]}]


def sheet_of(table: dict, user_id) -> dict:
    return next(member['sheet'] for member in table['members'] if member['user_id'] == str(user_id))


def gained(payload: dict) -> dict[str, int]:
    """받은 사람(캐릭터 이름)마다 받은 경험치."""
    return {gain['character_name']: gain['xp']['count'] for gain in payload['gains']}


async def kill_first_rat(
    client: AsyncClient, app: FastAPI, me: dict, table: dict, friend: dict | None = None, **theirs
):
    """내가 첫 들쥐를 쓰러뜨린다. 함께 앉은 사람은 theirs 의 행동(없으면 둘러보기)을 한다."""
    (first, _) = await rat_ids(client, me, table)
    load_dice(app, [PASS, DOWN])
    await declare(client, me, table, '쥐를 찌른다.', strike(monster=first))
    if friend is not None:
        await declare(client, friend, table, **theirs)
    return first


# --- 시나리오 ---


async def test_experience_is_saved_and_frozen(client: AsyncClient, me: dict):
    world = await growing_world(client, me)
    scenario = await make_scenario(
        client, me, world, [], monster_sheets=rats(world, 40), happenings=giving(world, 10), xp_split='each'
    )

    response = await publish(client, me, scenario)

    assert (scenario['xp_split'], scenario['monster_sheets'][0]['xp']) == ('each', 40)
    assert scenario['happenings'][0]['effects'] == [{'kind': 'give_xp', 'amount': 10, 'from_place': None}]
    snapshot = read_snapshot(response.json()['snapshot'])
    assert (snapshot.xp_split, snapshot.monsters[0].xp, snapshot.happenings[0].effects[0].amount) == (
        XpSplit.EACH,
        40,
        10,
    )


async def test_the_split_defaults_to_sharing(client: AsyncClient, me: dict):
    world = await growing_world(client, me)

    scenario = await make_scenario(client, me, world, [])

    assert scenario['xp_split'] == 'share'


@pytest.mark.parametrize('case', ['monster', 'happening'])
async def test_experience_needs_a_level_table(client: AsyncClient, me: dict, case: str):
    world = await make_world(client, me)
    fields = {'monster_sheets': rats(world, 10)} if case == 'monster' else {'happenings': giving(world, 10)}
    scenario = await make_scenario(client, me, world, [], **fields)

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == ['progression_missing']


async def test_giving_at_a_place_off_the_map_is_refused(client: AsyncClient, me: dict):
    world = await growing_world(client, me)
    scenario = await make_scenario(client, me, world, [], happenings=giving(world, 10, world['island']))

    response = await publish(client, me, scenario)

    assert response.json()['problems'] == ['happening_place_off_map']


@pytest.mark.parametrize('effect', [{'kind': 'give_xp', 'amount': 0}, {'kind': 'give_xp', 'amount': 100_001}])
async def test_a_misshaped_gift_is_refused(client: AsyncClient, me: dict, effect: dict):
    world = await growing_world(client, me)
    rule = {**giving(world, 1)[0], 'effects': [effect]}
    scenario = await make_scenario(client, me, world, [])

    response = await client.patch(
        f'{quest_tests.SCENARIOS_URL}/{scenario["id"]}', json={'happenings': [rule]}, headers=me
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 몬스터 ---


@pytest.mark.parametrize(('split', 'each'), [('each', 30), ('share', 15)])
async def test_a_fallen_monster_gives_experience_to_those_there(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated, split: str, each: int
):
    world = await growing_world(client, me)
    table = await start(client, me, world, [], friend, monster_sheets=rats(world, 30), xp_split=split)

    rat = await kill_first_rat(client, app, me, table, friend)
    await narrated()

    (given,) = await events_of(client, me, table, 'experience_gained')
    assert given['actor_id'] is None
    assert (given['payload']['source']['kind'], given['payload']['source']['id']) == ('monster', rat)
    assert given['payload']['source']['name'].startswith('들쥐')
    assert (given['payload']['split'], gained(given['payload'])) == (split, {'기사': each, '약사': each})
    after = await read_table(client, me, table)
    assert (sheet_of(after, ME)['xp'], sheet_of(after, FRIEND)['xp']) == (each, each)


async def test_sharing_drops_the_remainder(client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated):
    world = await growing_world(client, me)
    table = await start(client, me, world, [], friend, monster_sheets=rats(world, 25))

    await kill_first_rat(client, app, me, table, friend)
    await narrated()

    (given,) = await events_of(client, me, table, 'experience_gained')
    assert gained(given['payload']) == {'기사': 12, '약사': 12}


async def test_one_who_went_elsewhere_gets_nothing(client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated):
    world = await growing_world(client, me)
    table = await start(client, me, world, [], friend, monster_sheets=rats(world, 30), xp_split='share')

    await kill_first_rat(client, app, me, table, friend, content='숲으로 간다.', action=move(world['forest']))
    await narrated()

    # 약사는 숲으로 가서 그 자리에 없었다. 혼자 남은 기사가 나누지 않고 다 받는다
    (given,) = await events_of(client, me, table, 'experience_gained')
    assert gained(given['payload']) == {'기사': 30}


async def test_the_dead_get_no_share(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession, narrated
):
    world = await growing_world(client, me)
    table = await start(client, me, world, [], friend, monster_sheets=rats(world, 30))
    await kill(session, FRIEND)
    await session.commit()

    await kill_first_rat(client, app, me, table)
    await narrated()

    # 죽은 약사는 그 자리에 있어도 받지 않고, 몫을 나누지도 않는다
    (given,) = await events_of(client, me, table, 'experience_gained')
    assert gained(given['payload']) == {'기사': 30}


async def test_a_monster_gives_once_and_can_raise_the_level(client: AsyncClient, app: FastAPI, me: dict, narrated):
    world = await growing_world(client, me)
    table = await start(client, me, world, [], monster_sheets=rats(world, 150))

    await kill_first_rat(client, app, me, table)
    await narrated()
    await declare(client, me, table, '주위를 살핀다.')
    await narrated()

    (given,) = await events_of(client, me, table, 'experience_gained')
    (leveled,) = await events_of(client, me, table, 'character_leveled')
    assert leveled['caused_by_sequence'] == given['sequence']
    assert (leveled['payload']['previous_level'], leveled['payload']['level']) == (1, 2)
    sheet = sheet_of(await read_table(client, me, table), ME)
    assert (sheet['xp'], sheet['level'], sheet['max_hp']) == (150, 2, 13)


async def test_a_monster_without_experience_gives_nothing(client: AsyncClient, app: FastAPI, me: dict, narrated):
    world = await growing_world(client, me)
    table = await start(client, me, world, [])

    await kill_first_rat(client, app, me, table)
    await narrated()

    assert await events_of(client, me, table, 'experience_gained') == []


# --- 사건 ---


@pytest.mark.parametrize(('split', 'each'), [('each', 40), ('share', 20)])
async def test_a_happening_gives_experience_to_all(
    client: AsyncClient, me: dict, friend: dict, narrated, split: str, each: int
):
    world = await growing_world(client, me)
    table = await start(client, me, world, [], friend, happenings=giving(world, 40), xp_split=split)

    await declare(client, me, table)
    await declare(client, friend, table)
    await narrated()

    (happened,) = await events_of(client, me, table, 'happening_occurred')
    (given,) = await events_of(client, me, table, 'experience_gained')
    assert 'experience' not in happened['payload']
    assert given['caused_by_sequence'] == happened['sequence']
    assert given['payload']['source'] == {'kind': 'happening', 'id': world['secret']['id'], 'name': '숨은 비밀'}
    assert gained(given['payload']) == {'기사': each, '약사': each}


async def test_a_happening_can_raise_the_level_and_keeps_its_own_record(
    client: AsyncClient, me: dict, session: AsyncSession, narrated
):
    world = await growing_world(client, me)
    table = await start(client, me, world, [], happenings=giving(world, 150))

    await declare(client, me, table)
    await narrated()

    (given,) = await events_of(client, me, table, 'experience_gained')
    (leveled,) = await events_of(client, me, table, 'character_leveled')
    assert leveled['caused_by_sequence'] == given['sequence']
    # 사건의 이벤트에는 준 경험치를 적지 않는다(뒤의 experience_gained 에 적는다)
    stored = await session.scalar(text("SELECT payload FROM table_events WHERE type = 'happening_occurred'"))
    assert 'experience' not in stored


async def test_a_happening_gives_only_to_those_standing_there(client: AsyncClient, me: dict, friend: dict, narrated):
    world = await growing_world(client, me)
    table = await start(client, me, world, [], friend, happenings=giving(world, 40, world['gate']), xp_split='each')

    await declare(client, me, table)
    await declare(client, friend, table, '숲으로 간다.', move(world['forest']))
    await narrated()

    (given,) = await events_of(client, me, table, 'experience_gained')
    assert gained(given['payload']) == {'기사': 40}


# --- 순수 함수와 기록 ---


def test_the_share_of_one():
    assert [share_of(25, n, XpSplit.SHARE) for n in (0, 1, 2, 3)] == [0, 25, 12, 8]
    assert [share_of(25, n, XpSplit.EACH) for n in (0, 1, 3)] == [0, 25, 25]


def test_the_transcript_names_who_gained():
    payload = {
        'source': {'kind': 'monster', 'name': '들쥐 1'},
        'gains': [{'character_name': '기사', 'xp': {'count': 12}}, {'character_name': '약사', 'xp': {'count': 12}}],
    }

    assert '경험치: 들쥐 1 · 기사 +12, 약사 +12' in render_event(event('experience_gained', payload), LABELS)


def load_migration():
    path = next(Path('tests/legacy_migrations').glob('*_monster_xp.py'))
    spec = importlib.util.spec_from_file_location('monster_xp_migration', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_undoing_the_migration_drops_the_gifts():
    migration = load_migration()
    only_gift = {'entry_id': 'a', 'effects': [{'kind': 'give_xp', 'amount': 5}]}
    mixed = {'entry_id': 'b', 'effects': [{'kind': 'give_xp', 'amount': 5}, {'kind': 'move', 'to_place': 'p'}]}

    assert migration.happenings_without_xp([only_gift, mixed]) == [
        {'entry_id': 'b', 'effects': [{'kind': 'move', 'to_place': 'p'}]}
    ]
    assert migration.sheet_without_xp({'monster_id': 'm', 'xp': 3}) == {'monster_id': 'm'}
