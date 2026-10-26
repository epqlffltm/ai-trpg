# trpg-server/tests/test_item_throws.py

"""
물건을 던지는 행동(#277, app/rounds/throws.py)을 검증한다.

맵은 수로 입구(시작)와 깊은 수로다. 입구에 수로 쥐 둘(야수, 최대 HP 4), 깊은 수로에 해골 병사 하나.
악역영애(비올레타, 최대 HP 10)는 스타팅에 나오는 인물이다. 자리가 없어 어디서나 닿는다.
물건은 넷이다. 화염병은 민첩·보통으로 던지고 효과는 보통(moderate) 피해, 투척 단검은 근력·난이도 비움(기본은 보통)으로
던지고 효과는 가벼운(light) 피해다. 연막탄(효과 없는 소모품)과 밧줄(장비)은 던지는 판정이 없어 룰북의 맞히는 판정
(민첩·보통)으로 던진다(#801). 모두 화염병 둘, 투척 단검 하나, 연막탄 하나, 밧줄 하나로 시작한다.
주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다. 판정의 눈을 먼저, 피해의 눈을 그다음에 쓴다.

넷을 본다.
  - 시나리오: throw 는 능력·난이도만 적는다(장비에도 된다). 게시할 때 룰북에 맞아야 한다(item_throw_invalid).
    판 형식 63.
  - 받기: 어떤 물건이든 가지고 있으면 던진다. 맞을 쪽이 치기처럼 닿아야 한다. 판정이 물건에도 룰북에도 없으면 422.
  - 닫힐 때: 물건이나 룰북의 판정으로 굴리고, 맞으면 그 물건의 효과가 든다. 맞든 빗나가든 하나 없어진다.
    못 던졌으면 그대로다. 던지기와 쓰기가 함께 쓰는 효과의 엔진은 test_item_effects.py 가 본다.
  - 기록과 서술: item_thrown 뒤에 판정(check_rolled)과 맞은 쪽의 변화가 잇는다. 한 일의 줄에 던진 물건이 붙는다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.schemas import ItemRule
from app.assets.scenarios.snapshot import SNAPSHOT_FORMAT, read_snapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_58, upgrade_from_62
from app.engine.action import ThrowAction
from app.rounds.move_lines import describe_throw
from app.rounds.narration_request import to_throw
from app.rounds.narrator import ThrowNote
from app.tables.models import NpcStatus
from tests import test_monster_combat as combat
from tests.sheets import SHEET, make_sheet
from tests.test_npc_sheets import published, refused
from tests.test_ruleset import load_migration
from tests.test_table_items import take as take_away

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = combat.ME
FRIEND = combat.FRIEND
SCENARIOS_URL = combat.SCENARIOS_URL
RULEBOOKS_URL = combat.RULEBOOKS_URL
LOREBOOKS_URL = combat.LOREBOOKS_URL
BESTIARIES_URL = combat.BESTIARIES_URL
TABLES_URL = combat.TABLES_URL
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'

me = combat.me
friend = combat.friend
post = combat.post
table_url = combat.table_url
load_dice = combat.load_dice
send = combat.send
declare = combat.declare
monster_named = combat.monster_named
state_of = combat.state_of
events_of = combat.events_of

FAIL = combat.FAIL
PASS = combat.PASS
# 큰 타격(HP 4 중 2 이상)이나 쓰러짐이면 그다음 눈이 부상 표다(#799). 이 눈이면 아무 부상도 없다
NO_INJURY = combat.NO_INJURY

THROW = '화염병을 던진다.'
LOOK = '주위를 살핀다.'
OPENING = '물 떨어지는 소리가 난다. 악역영애가 부채를 펼친다.'
POISON = {'kind': 'injure', 'injury': 'poisoned'}
HEAL = {'kind': 'heal', 'magnitude': 'light'}


def throw(item: dict, **target) -> dict:
    """그 물건을 던지는 행동. 맞을 쪽은 monster 나 npc 다."""
    return {'kind': 'throw', 'item': item['id'], **target}


def the_items(lore: dict) -> list[dict]:
    """화염병(민첩·보통, 보통 피해), 투척 단검(근력·기본 난이도, 가벼운 피해), 연막탄(효과 없음), 밧줄(장비)."""
    return [
        {
            'entry_id': lore['firebomb']['id'],
            'kind': 'consumable',
            'throw': {'ability': 'dex', 'difficulty': 'medium'},
            'effects': [{'kind': 'damage', 'magnitude': 'moderate'}],
        },
        {
            'entry_id': lore['dagger']['id'],
            'kind': 'consumable',
            'throw': {'ability': 'str'},
            'effects': [{'kind': 'damage', 'magnitude': 'light'}],
        },
        {'entry_id': lore['smoke']['id'], 'kind': 'consumable'},
        {'entry_id': lore['rope']['id'], 'kind': 'gear'},
    ]


async def make_world(client: AsyncClient, me: dict) -> dict:
    """로어북(장소 둘, 인물 하나, 물건 넷)과 도감(쥐, 해골)과 룰북을 만든다. 시나리오는 아직 없다."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='지하 수로')
    entries = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'

    async def entry(name: str, kind: str, keywords: list[str] | None = None) -> dict:
        return await post(client, entries, me, name=name, kind=kind, keywords=keywords or [], content=f'{name}의 글')

    bestiary = await post(client, BESTIARIES_URL, me, title='지하 수로의 것들')
    monsters = f'{BESTIARIES_URL}/{bestiary["id"]}/monsters'
    return {
        'lorebook': lorebook,
        'bestiary': bestiary,
        'rulebook': await post(client, RULEBOOKS_URL, me, title='룰북'),
        'gate': await entry('수로 입구', 'place'),
        'deep': await entry('깊은 수로', 'place'),
        'lady': await entry('비올레타', 'person', ['악역영애']),
        'firebomb': await entry('화염병', 'item'),
        'dagger': await entry('투척 단검', 'item'),
        'smoke': await entry('연막탄', 'item'),
        'rope': await entry('밧줄', 'item'),
        'rat': await post(client, monsters, me, name='수로 쥐', kind='beast', content='개만 한 쥐'),
        'skeleton': await post(client, monsters, me, name='해골 병사', kind='undead', content='녹슨 창'),
    }


async def make_scenario(client: AsyncClient, me: dict, world: dict, items: list[dict]) -> dict:
    """그 아이템 규칙을 적은 수로의 시나리오. 모두 화염병 둘, 투척 단검, 연막탄, 밧줄 하나씩으로 시작한다."""
    starting = [
        {'entry_id': world['firebomb']['id'], 'count': 2},
        {'entry_id': world['dagger']['id'], 'count': 1},
        {'entry_id': world['smoke']['id'], 'count': 1},
        {'entry_id': world['rope']['id'], 'count': 1},
    ]
    return await post(
        client,
        SCENARIOS_URL,
        me,
        title='지하 수로',
        rulebook_id=world['rulebook']['id'],
        lorebook_ids=[world['lorebook']['id']],
        bestiary_ids=[world['bestiary']['id']],
        openings=[OPENING],
        default_sheet=SHEET,
        default_npc_sheet=SHEET,
        npc_sheets=[{'entry_id': world['lady']['id'], 'sheet': make_sheet(max_hp=10)}],
        monster_sheets=[
            {'monster_id': world['rat']['id'], 'sheet': make_sheet(max_hp=4)},
            {'monster_id': world['skeleton']['id'], 'sheet': make_sheet(max_hp=6)},
        ],
        start_place=world['gate']['id'],
        routes=[{'from_place': world['gate']['id'], 'to_place': world['deep']['id']}],
        encounters=[
            {'place_id': world['gate']['id'], 'monster_id': world['rat']['id'], 'count': 2},
            {'place_id': world['deep']['id'], 'monster_id': world['skeleton']['id'], 'count': 1},
        ],
        starting_items=starting,
        items=items,
    )


async def start_table(client: AsyncClient, me: dict, *others: dict) -> dict:
    """수로의 시나리오로 테이블을 시작한다. 나(엘프)와 others(드워프 기사)가 앉는다. 모두 수로 입구에 선다."""
    world = await make_world(client, me)
    scenario = await make_scenario(client, me, world, the_items(world))
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1 + len(others))
    for headers, name in zip([me, *others], ['엘프', '드워프 기사'], strict=False):
        if headers is not me:
            await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=headers)
        await client.put(table_url(table, '/character'), json={'name': name}, headers=headers)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return {**world, 'table': started.json()}


async def read_table(client: AsyncClient, headers: dict, table: dict) -> dict:
    return (await client.get(table_url(table), headers=headers)).json()


def held(table: dict, user_id: uuid.UUID) -> dict[str, int]:
    member = next(member for member in table['members'] if member['user_id'] == str(user_id))
    return {item['name']: item['count'] for item in member['sheet']['items']}


def outcome_of(round_: dict, user_id: uuid.UUID) -> dict:
    return next(d for d in round_['declarations'] if d['user_id'] == str(user_id))['outcome']


async def first_round(client: AsyncClient, headers: dict, table: dict) -> dict:
    return (await client.get(table_url(table, '/rounds/1'), headers=headers)).json()


async def kill(session: AsyncSession, monster_id: str) -> None:
    """서비스를 거치지 않고 그 마리를 죽인다. 같은 라운드에 앞사람이 죽인 것과 같다."""
    await session.execute(
        text("UPDATE table_monsters SET hp = 0, status = 'dead' WHERE id = :id"), {'id': uuid.UUID(monster_id)}
    )
    await session.commit()


# --- 시나리오 ---


def rule(**fields) -> dict:
    return {'entry_id': NO_SUCH_ID, 'kind': 'consumable', **fields}


@pytest.mark.parametrize(
    'fields',
    [
        {'throw': {'ability': 'dex', 'harm': 'light'}},
        {'throw': {'difficulty': 'medium'}},
        {'throw': {'ability': 'dex', 'noise': 1}},
        {'throw': {'ability': 'Not A Key'}},
    ],
    ids=['old-harm', 'no-ability', 'unknown-field', 'bad-key'],
)
def test_rejects_misshaped_throws(fields: dict):
    with pytest.raises(ValidationError):
        ItemRule.model_validate(rule(**fields))


def test_a_throw_may_leave_the_difficulty_to_the_rulebook():
    parsed = ItemRule.model_validate(rule(throw={'ability': 'dex'}))
    # 장비에도 적는다(#801, 투척 도끼)
    axe = ItemRule.model_validate(rule(kind='gear', throw={'ability': 'str', 'difficulty': 'hard'}))

    assert (parsed.throw.ability, parsed.throw.difficulty) == ('dex', None)
    assert (axe.kind, axe.throw.ability) == ('gear', 'str')


async def test_throws_are_saved_frozen_and_listed(client: AsyncClient, me: dict):
    world = await start_table(client, me)

    read = await read_table(client, me, world['table'])

    thrown = {item['name']: item['throw'] for item in read['items']}
    assert thrown == {
        '화염병': {'ability': 'dex', 'difficulty': 'medium'},
        '투척 단검': {'ability': 'str', 'difficulty': None},
        '연막탄': None,
        '밧줄': None,
    }


async def test_the_version_is_format_63(client: AsyncClient, me: dict):
    world = await make_world(client, me)
    scenario = await make_scenario(client, me, world, the_items(world))

    document = await published(client, me, scenario)

    assert document['format'] == SNAPSHOT_FORMAT >= 63
    assert [rule.throw.ability if rule.throw else None for rule in read_snapshot(document).items] == [
        'dex',
        'str',
        None,
        None,
    ]


@pytest.mark.parametrize(
    'throw_',
    [
        {'ability': 'luck'},
        {'ability': 'dex', 'difficulty': 'impossible'},
    ],
    ids=['ability', 'difficulty'],
)
async def test_a_throw_must_fit_the_rulebook(client: AsyncClient, me: dict, throw_: dict):
    world = await make_world(client, me)
    items = [{'entry_id': world['firebomb']['id'], 'kind': 'consumable', 'throw': throw_}]
    scenario = await make_scenario(client, me, world, items)

    assert 'item_throw_invalid' in await refused(client, me, scenario)


def test_an_old_snapshot_reads_as_throwing_nothing():
    document = {'format': 58, 'items': [{'entry_id': NO_SUCH_ID, 'kind': 'consumable'}]}

    upgraded = upgrade_from_58(document)

    assert (upgraded['format'], upgraded['items'][0]['throw']) == (59, None)
    assert 'throw' not in document['items'][0]
    assert UPGRADES[58] is upgrade_from_58


# --- 행동의 모양과 받기 ---


@pytest.mark.parametrize(
    'target',
    [{}, {'npc': NO_SUCH_ID, 'monster': NO_SUCH_ID}],
    ids=['nothing', 'both'],
)
def test_a_throw_aims_at_one_thing(target: dict):
    with pytest.raises(ValidationError):
        ThrowAction.model_validate({'kind': 'throw', 'item': NO_SUCH_ID, **target})


async def test_only_a_thing_can_be_thrown(client: AsyncClient, me: dict):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')

    response = await send(client, me, world['table'], THROW, throw(world['lady'], monster=rat['id']))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'item' in response.text


async def test_lethal_needs_a_damaging_thing(client: AsyncClient, me: dict):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')

    response = await send(client, me, world['table'], THROW, throw(world['smoke'], monster=rat['id'], lethal=True))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'action.lethal' in response.text


async def test_only_what_is_held_can_be_thrown(client: AsyncClient, me: dict, session: AsyncSession):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    await take_away(session, world['table'], ME, world['firebomb'])

    response = await send(client, me, world['table'], THROW, throw(world['firebomb'], monster=rat['id']))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert 'item_not_held' in response.text


async def test_a_monster_elsewhere_cannot_be_hit(client: AsyncClient, me: dict):
    world = await start_table(client, me)
    response = await client.get(table_url(world['table'], '/rounds/current/people'), headers=me)
    assert all(monster['name'] != '해골 병사' for monster in response.json()['monsters'])

    response = await send(client, me, world['table'], THROW, throw(world['firebomb'], monster=NO_SUCH_ID))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'monster' in response.text


async def test_a_dead_monster_cannot_be_aimed_at(client: AsyncClient, me: dict, session: AsyncSession):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    await kill(session, rat['id'])

    response = await send(client, me, world['table'], THROW, throw(world['firebomb'], monster=rat['id']))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert 'monster_dead' in response.text


async def test_a_person_not_in_the_scene_cannot_be_hit(client: AsyncClient, me: dict):
    world = await start_table(client, me)

    response = await send(client, me, world['table'], THROW, throw(world['firebomb'], npc=NO_SUCH_ID))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'npc' in response.text


# --- 닫힐 때 ---


async def test_a_hit_hurts_the_monster_and_uses_the_thing_up(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    load_dice(app, [PASS, 3, NO_INJURY])

    closing = await declare(client, me, world['table'], THROW, throw(world['firebomb'], monster=rat['id']))

    outcome = outcome_of(closing, ME)
    assert outcome['item_throw'] == {
        'entry_id': world['firebomb']['id'],
        'name': '화염병',
        'thrown': True,
        'reason': None,
        'ability': 'dex',
        'difficulty': 'medium',
        'target': {'monster_id': rat['id'], 'entry_id': None, 'user_id': None, 'name': '수로 쥐 1'},
        'remaining': 1,
        'cured': [],
        'injured': [],
    }
    assert (outcome['success'], outcome['target'], outcome['monster_effect']['amount']) == (True, 15, 3)
    assert await state_of(session, rat['id']) == (1, NpcStatus.ALIVE)
    assert held(await read_table(client, me, world['table']), ME)['화염병'] == 1


async def test_a_miss_still_uses_the_thing_up(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    load_dice(app, [FAIL])

    closing = await declare(client, me, world['table'], THROW, throw(world['firebomb'], monster=rat['id']))

    outcome = outcome_of(closing, ME)
    assert (outcome['success'], outcome['monster_effect'], outcome['item_throw']['remaining']) == (False, None, 1)
    assert await state_of(session, rat['id']) == (4, NpcStatus.ALIVE)


async def test_the_rulebook_s_difficulty_fills_an_empty_one(client: AsyncClient, app: FastAPI, me: dict):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    load_dice(app, [PASS, 2, NO_INJURY])

    closing = await declare(client, me, world['table'], THROW, throw(world['dagger'], monster=rat['id']))

    outcome = outcome_of(closing, ME)
    assert (outcome['item_throw']['ability'], outcome['item_throw']['difficulty']) == ('str', 'medium')
    assert (outcome['target'], outcome['monster_effect']['magnitude']) == (15, 'light')
    assert '투척 단검' not in held(await read_table(client, me, world['table']), ME)


@pytest.mark.parametrize(('lethal', 'expected'), [(False, NpcStatus.DOWNED), (True, NpcStatus.DEAD)])
async def test_a_throw_may_be_lethal(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, lethal: bool, expected: NpcStatus
):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    load_dice(app, [PASS, 8, NO_INJURY])

    await declare(client, me, world['table'], THROW, throw(world['firebomb'], monster=rat['id'], lethal=lethal))

    assert await state_of(session, rat['id']) == (0, expected)


async def test_a_person_can_be_hit(client: AsyncClient, app: FastAPI, me: dict):
    world = await start_table(client, me)
    load_dice(app, [PASS, 4])

    closing = await declare(client, me, world['table'], THROW, throw(world['firebomb'], npc=world['lady']['id']))

    outcome = outcome_of(closing, ME)
    assert (outcome['npc_effect']['name'], outcome['npc_effect']['amount']) == ('악역영애', 4)
    assert outcome['item_throw']['target'] == {
        'monster_id': None,
        'entry_id': world['lady']['id'],
        'user_id': None,
        'name': '악역영애',
    }


async def test_a_monster_killed_meanwhile_is_not_thrown_at(
    client: AsyncClient, me: dict, friend: dict, session: AsyncSession, narrated
):
    world = await start_table(client, me, friend)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    await declare(client, friend, world['table'], THROW, throw(world['firebomb'], monster=rat['id']))
    # 선언한 뒤 차례가 오기 전에 그 쥐가 죽었다(앞사람이 죽인 것과 같다)
    await kill(session, rat['id'])
    await declare(client, me, world['table'], LOOK)
    await narrated()

    outcome = outcome_of(await first_round(client, me, world['table']), FRIEND)
    assert (outcome['item_throw']['thrown'], outcome['item_throw']['reason']) == (False, 'target_gone')
    assert outcome['target_gone']['reason'] == 'dead'
    assert 'roll' not in outcome
    assert held(await read_table(client, me, world['table']), FRIEND)['화염병'] == 2


async def test_what_was_taken_meanwhile_is_not_thrown(
    client: AsyncClient, me: dict, friend: dict, session: AsyncSession, narrated
):
    world = await start_table(client, me, friend)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    await declare(client, friend, world['table'], THROW, throw(world['firebomb'], monster=rat['id']))
    await take_away(session, world['table'], FRIEND, world['firebomb'])
    await declare(client, me, world['table'], LOOK)
    await narrated()

    outcome = outcome_of(await first_round(client, me, world['table']), FRIEND)
    assert outcome['item_throw'] == {
        'entry_id': world['firebomb']['id'],
        'name': '화염병',
        'thrown': False,
        'reason': 'not_held',
        'ability': 'dex',
        'difficulty': 'medium',
        'target': {'monster_id': rat['id'], 'entry_id': None, 'user_id': None, 'name': '수로 쥐 1'},
        'remaining': 0,
        'cured': [],
        'injured': [],
    }
    assert await state_of(session, rat['id']) == (4, NpcStatus.ALIVE)


# --- 기록과 서술 ---


async def test_the_throw_is_recorded_before_its_check(client: AsyncClient, app: FastAPI, me: dict, narrated):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    load_dice(app, [PASS, 3, NO_INJURY])
    await declare(client, me, world['table'], THROW, throw(world['firebomb'], monster=rat['id']))
    await narrated()

    (acted,) = await events_of(client, me, world['table'], 'player_action')
    (thrown,) = await events_of(client, me, world['table'], 'item_thrown')
    (rolled,) = await events_of(client, me, world['table'], 'check_rolled')
    (changed,) = await events_of(client, me, world['table'], 'monster_changed')
    assert thrown['caused_by_sequence'] == acted['sequence']
    assert rolled['caused_by_sequence'] == thrown['sequence']
    assert changed['caused_by_sequence'] == rolled['sequence']
    assert thrown['actor_id'] is None
    assert thrown['payload'] == {
        'round': 1,
        'character_name': '엘프',
        'entry_id': world['firebomb']['id'],
        'name': '화염병',
        'thrown': True,
        'reason': None,
        'target': {'monster_id': rat['id'], 'name': '수로 쥐 1'},
        'remaining': 1,
        'cured': [],
        'injured': [],
    }
    assert (rolled['payload']['ability'], rolled['payload']['difficulty']) == ('dex', 'medium')


async def test_a_throw_that_did_not_happen_rolls_nothing(
    client: AsyncClient, me: dict, friend: dict, session: AsyncSession, narrated
):
    world = await start_table(client, me, friend)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    await declare(client, friend, world['table'], THROW, throw(world['firebomb'], monster=rat['id']))
    await take_away(session, world['table'], FRIEND, world['firebomb'])
    await declare(client, me, world['table'], LOOK)
    await narrated()

    (thrown,) = await events_of(client, me, world['table'], 'item_thrown')
    assert (thrown['payload']['thrown'], thrown['payload']['reason']) == (False, 'not_held')
    assert await events_of(client, me, world['table'], 'check_rolled') == []


async def test_the_narrator_hears_what_was_thrown(client: AsyncClient, app: FastAPI, me: dict, narrated):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    load_dice(app, [PASS, 3, NO_INJURY])
    await declare(client, me, world['table'], THROW, throw(world['firebomb'], monster=rat['id']))
    await narrated()

    second = (await client.get(table_url(world['table'], '/rounds/current'), headers=me)).json()
    assert f'엘프: {THROW} (던진 물건: 화염병 → 수로 쥐 1) (민첩 판정 성공' in second['scene']


@pytest.mark.parametrize(
    ('note', 'line'),
    [
        (ThrowNote(name='화염병', target='수로 쥐 1', done=True), '(던진 물건: 화염병 → 수로 쥐 1)'),
        (
            ThrowNote(name='화염병', target='수로 쥐 1', done=False, reason='not_held'),
            '(던지려던 물건: 화염병 → 수로 쥐 1. 가지고 있지 않았다)',
        ),
        (
            ThrowNote(name='화염병', target='수로 쥐 1', done=False, reason='target_gone'),
            '(던지려던 물건: 화염병 → 수로 쥐 1)',
        ),
        (ThrowNote(name='화염병', target=None, done=True), '(던진 물건: 화염병)'),
        (
            ThrowNote(name='독 병', target='해골 병사', done=True, injured=['기절'], resisted=['중독']),
            '(던진 물건: 독 병 → 해골 병사) [입힌 부상: 기절] [면역이라 입지 않은 부상: 중독]',
        ),
    ],
    ids=['thrown', 'not-held', 'target-gone', 'no-name', 'effects'],
)
def test_the_line_names_what_was_thrown(note: ThrowNote, line: str):
    assert describe_throw(note) == line


# --- 모든 물건(#801) ---


@pytest.mark.parametrize(('name', 'label'), [('smoke', '연막탄'), ('rope', '밧줄')])
async def test_a_thing_without_a_throw_is_thrown_with_the_rulebook_s_check(
    client: AsyncClient, app: FastAPI, me: dict, name: str, label: str
):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    dice = load_dice(app, [PASS])

    closing = await declare(client, me, world['table'], THROW, throw(world[name], monster=rat['id']))

    outcome = outcome_of(closing, ME)
    # 룰북의 맞히는 판정(민첩·보통)이다. 효과가 없어 맞아도 아무 일이 없다
    assert (outcome['item_throw']['ability'], outcome['item_throw']['difficulty']) == ('dex', 'medium')
    assert (outcome['success'], outcome['monster_effect']) == (True, None)
    assert dice.remaining == 0
    assert label not in held(await read_table(client, me, world['table']), ME)


async def table_with_item_check(client: AsyncClient, me: dict, session: AsyncSession, check: str) -> dict:
    """룰북의 맞히는 판정(item_check)을 check(JSON)로 바꾼 뒤 수로의 판으로 테이블을 시작한다."""
    world = await make_world(client, me)
    await session.execute(
        text(
            "UPDATE rulebooks SET rules = jsonb_set(rules, '{item_check}', CAST(:check AS jsonb)) WHERE asset_id = :id"
        ),
        {'check': check, 'id': uuid.UUID(world['rulebook']['id'])},
    )
    await session.commit()
    scenario = await make_scenario(client, me, world, the_items(world))
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    await client.post(table_url(table, '/start'), headers=me)
    return {**world, 'table': table}


async def test_the_rulebook_s_check_is_the_one_its_table_was_published_with(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    world = await table_with_item_check(client, me, session, '{"ability": "str", "difficulty": "hard"}')
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    load_dice(app, [PASS])

    closing = await declare(client, me, world['table'], THROW, throw(world['smoke'], monster=rat['id']))

    thrown = outcome_of(closing, ME)['item_throw']
    assert (thrown['ability'], thrown['difficulty']) == ('str', 'hard')


async def test_a_rulebook_without_the_check_throws_only_what_has_a_throw(
    client: AsyncClient, me: dict, session: AsyncSession
):
    world = await table_with_item_check(client, me, session, 'null')
    table = world['table']
    rat = await monster_named(client, me, table, '수로 쥐 1')

    smoke = await send(client, me, table, THROW, throw(world['smoke'], monster=rat['id']))
    firebomb = await send(client, me, table, THROW, throw(world['firebomb'], monster=rat['id']))

    assert smoke.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'action.item' in smoke.text
    assert firebomb.status_code == status.HTTP_200_OK, firebomb.text


def test_an_old_version_moves_the_throw_s_harm_into_the_effects():
    old = {
        'format': 62,
        'items': [
            {'entry_id': 'a', 'kind': 'consumable', 'throw': {'ability': 'dex', 'harm': 'light'}, 'effects': [POISON]},
            {
                'entry_id': 'b',
                'kind': 'consumable',
                'throw': {'ability': 'dex', 'difficulty': None, 'harm': 'light'},
                'effects': [{'kind': 'heal', 'magnitude': 'light'}],
            },
            {'entry_id': 'c', 'kind': 'gear', 'throw': None, 'effects': []},
        ],
    }

    upgraded = upgrade_from_62(old)

    assert upgraded['format'] == 63
    assert upgraded['items'][0] == {
        'entry_id': 'a',
        'kind': 'consumable',
        'throw': {'ability': 'dex'},
        'effects': [{'kind': 'damage', 'magnitude': 'light'}, POISON],
    }
    # 이미 HP 를 바꾸는 효과가 있으면 던진 피해는 버린다(HP 의 변화는 하나다)
    assert upgraded['items'][1]['effects'] == [{'kind': 'heal', 'magnitude': 'light'}]
    assert upgraded['items'][1]['throw'] == {'ability': 'dex', 'difficulty': None}
    assert upgraded['items'][2] == old['items'][2]
    assert 'harm' in old['items'][0]['throw']
    assert UPGRADES[62] is upgrade_from_62


def test_the_narrator_hears_what_a_throw_did():
    thrown = {
        'name': '독병',
        'target': {'monster_id': 'm', 'name': '해골 병사'},
        'thrown': True,
        'reason': None,
        'cured': [{'injury': 'stunned', 'name': '기절'}],
        'injured': [
            {'injury': 'bleeding', 'name': '출혈', 'immune': None},
            {'injury': None, 'name': '중독', 'immune': 'poisoned'},
        ],
    }

    note = to_throw(SimpleNamespace(outcome={'item_throw': thrown}))

    assert (note.cured, note.injured, note.resisted) == (['기절'], ['출혈'], ['중독'])


def test_the_migration_moves_the_harm_and_takes_it_back():
    migration = load_migration('thrown_effects')
    old = {'entry_id': 'a', 'kind': 'consumable', 'throw': {'ability': 'dex', 'harm': 'light'}, 'effects': [POISON]}

    moved = migration.with_throw_damage(old)

    assert moved == {
        'entry_id': 'a',
        'kind': 'consumable',
        'throw': {'ability': 'dex'},
        'effects': [{'kind': 'damage', 'magnitude': 'light'}, POISON],
    }
    assert migration.with_throw_damage(moved) == moved
    assert migration.without_throw_damage(moved) == old
    # 그때는 소모품만, 피해와 함께 던졌다. 아니면 던지는 판정을 버린다
    axe = {'entry_id': 'b', 'kind': 'gear', 'throw': {'ability': 'str'}, 'effects': []}
    assert migration.without_throw_damage(axe)['throw'] is None
    # 이미 회복이 있으면 던진 피해는 버린다
    tonic = {'entry_id': 'c', 'kind': 'consumable', 'throw': {'ability': 'dex', 'harm': 'light'}, 'effects': [HEAL]}
    assert migration.with_throw_damage(tonic) == {**tonic, 'throw': {'ability': 'dex'}}
    assert migration.without_throw_damage({**old, 'throw': None}) == {**old, 'throw': None}
