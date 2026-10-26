# trpg-server/tests/test_item_aids.py

"""
물건이 다른 행동을 거드는 것(#802, 거들기)을 검증한다. 치료는 tests/test_treat_aids.py 가 본다.

맵과 물건은 tests/test_route_doors.py 의 것이다. 시작은 성문이다. 여기에 물건 둘(쇠지렛대, 밧줄)과 길 하나를 더한다.
  - 락픽: 따기를 +2 로 거든다. 실패하면 부러진다. 성문-광장의 자물쇠는 도구가 있어야 딴다(민첩, 보통 15).
  - 쇠지렛대: 부수기를 +3 으로 거든다. 없어지지 않는다. 성문-광장은 근력·어려움(20)으로 부순다.
  - 밧줄: 넘기를 +5 로 거든다. 없어지지 않는다. 더한 길 성문-탑은 근력으로 넘는다(보통 15).
시트의 능력치는 모두 10(보정 0)이다. 주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다.

보는 것.
  - 모양: 행동, 보정(0~10), 방식(always, on_fail, never). 한 물건에 같은 행동은 한 번. 장비에도 적는다.
  - 판 형식 64: 옛 치료 보정과 문의 도구가 거들기가 된다. 시나리오 초안은 마이그레이션이 옮긴다.
  - 받기: 그 행동을 거드는 판의 물건을 지녀야 한다. 넘기는 넘기 판정이 있는 길에만 붙인다.
  - 닫힐 때: 보정을 더하고, 굴린 뒤 방식대로 없어진다. 결과(aid), 이벤트(aid_used), 서술의 줄에 남는다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.schemas import ItemRule
from app.assets.scenarios.snapshot import SNAPSHOT_FORMAT, ItemRuleSnapshot, read_snapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_63
from app.engine.item_aids import AidWear, is_lost
from app.rounds.move_lines import describe_door, describe_travel
from app.rounds.narration_request import to_aid
from app.rounds.narrator import AidNote, DoorNote, TravelNote
from tests import test_route_doors as route_doors
from tests import test_table_map as map_tables
from tests.test_character_death import load_dice
from tests.test_map_actions import going, outcome_of, play
from tests.test_ruleset import load_migration
from tests.test_table_items import ME, events_of, give, post, read_table, table_url
from tests.test_table_items import take as take_away
from tests.test_table_map import open_duo, route

pytestmark = pytest.mark.usefixtures('clean_tables')

me = map_tables.me
friend = map_tables.friend
lore = map_tables.lore
gear = route_doors.gear
declare = route_doors.declare
door = route_doors.door
door_outcome = route_doors.door_outcome

LOCKPICK_BONUS = 2
CROWBAR_BONUS = 3
ROPE_BONUS = 5
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'


@pytest.fixture
async def kit(client: AsyncClient, me: dict, gear: dict) -> dict:
    """같은 로어북에 물건 둘(쇠지렛대, 밧줄)을 더한다."""
    url = f'{map_tables.LOREBOOKS_URL}/{gear["lorebook"]["id"]}/entries'

    async def entry(name: str) -> dict:
        return await post(client, url, me, name=name, keywords=[], content=f'{name}의 설명', kind='item')

    return {**gear, 'crowbar': await entry('쇠지렛대'), 'rope': await entry('밧줄')}


def the_items(kit: dict) -> list[dict]:
    """락픽(따기 +2, 실패하면 부러짐), 쇠지렛대(부수기 +3), 밧줄(넘기 +5)."""
    return [
        {'entry_id': kit['lockpick']['id'], 'aids': [{'act': 'pick', 'bonus': LOCKPICK_BONUS, 'wear': 'on_fail'}]},
        {'entry_id': kit['crowbar']['id'], 'aids': [{'act': 'force', 'bonus': CROWBAR_BONUS}]},
        {'entry_id': kit['rope']['id'], 'aids': [{'act': 'cross', 'bonus': ROPE_BONUS, 'wear': 'never'}]},
    ]


def the_map(kit: dict) -> dict:
    """route_doors 의 길에 성문-탑의 오를 길을 더한다."""
    climb = route(kit['gate'], kit['tower'], cross={'ability': 'str'})
    return {
        'start_place': kit['gate']['id'],
        'routes': [*route_doors.the_routes(kit), climb],
        'items': the_items(kit),
    }


async def start(client: AsyncClient, me: dict, friend: dict, kit: dict) -> dict:
    """거드는 물건을 적은 판으로 둘이 앉아 시작한 테이블."""
    table = await open_duo(client, me, friend, kit, **the_map(kit))
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


def held(table: dict, user_id: uuid.UUID) -> dict[str, int]:
    member = next(one for one in table['members'] if one['user_id'] == str(user_id))
    return {item['name']: item['count'] for item in member['sheet']['items']}


def climbing(kit: dict, item: dict | None = None) -> dict:
    action = going(kit['tower'])
    return action if item is None else {**action, 'item': item['id']}


# --- 모양 ---


def test_an_aid_takes_an_act_a_bonus_and_a_wear():
    rule = ItemRule.model_validate(
        {'entry_id': NO_SUCH_ID, 'kind': 'gear', 'aids': [{'act': 'pick', 'bonus': 10, 'wear': 'on_fail'}]}
    )

    # 장비에도 적는다. 비운 보정은 0, 비운 방식은 없어지지 않음이다
    assert (rule.aids[0].act, rule.aids[0].bonus, rule.aids[0].wear) == ('pick', 10, 'on_fail')
    plain = ItemRule.model_validate({'entry_id': NO_SUCH_ID, 'aids': [{'act': 'cross'}]})
    assert (plain.aids[0].bonus, plain.aids[0].wear) == (0, 'never')


@pytest.mark.parametrize(
    'aids',
    [
        [{'act': 'pick'}, {'act': 'pick', 'bonus': 1}],
        [{'act': 'sing'}],
        [{'act': 'pick', 'wear': 'sometimes'}],
        [{'act': 'pick', 'bonus': 11}],
        [{'act': 'pick', 'noise': 1}],
    ],
    ids=['repeated-act', 'unknown-act', 'unknown-wear', 'over-max', 'unknown-field'],
)
def test_a_misshaped_aid_is_refused(aids: list):
    with pytest.raises(ValidationError):
        ItemRule.model_validate({'entry_id': NO_SUCH_ID, 'aids': aids})


@pytest.mark.parametrize(
    ('wear', 'success', 'lost'),
    [
        (AidWear.ALWAYS, True, True),
        (AidWear.ALWAYS, False, True),
        (AidWear.ON_FAIL, True, False),
        (AidWear.ON_FAIL, False, True),
        (AidWear.NEVER, False, False),
    ],
)
def test_what_is_lost_after_the_roll(wear: AidWear, success: bool, lost: bool):
    assert is_lost(wear, success) is lost


async def test_the_table_lists_the_aids(client: AsyncClient, me: dict, friend: dict, kit: dict):
    table = await start(client, me, friend, kit)

    listed = {item['name']: item['aids'] for item in (await read_table(client, me, table))['items']}

    assert listed['락픽'] == [{'act': 'pick', 'bonus': LOCKPICK_BONUS, 'wear': 'on_fail'}]
    assert listed['밧줄'] == [{'act': 'cross', 'bonus': ROPE_BONUS, 'wear': 'never'}]
    assert listed['탑 열쇠'] == []


# --- 옛 판과 초안 ---


def old_document() -> dict:
    """형식 63 의 판. 의료 키트의 치료 보정, 길의 따는 도구(락픽, 규칙이 있다)와 고치는 도구(망치, 규칙이 없다)."""
    return {
        'format': 63,
        'items': [
            {'entry_id': 'kit', 'kind': 'consumable', 'treat_bonus': 2},
            {'entry_id': 'pick', 'kind': 'gear', 'treat_bonus': None},
        ],
        'routes': [
            {
                'from_place': 'a',
                'to_place': 'b',
                'lock': {'key': 'k', 'pick': {'ability': 'dex', 'difficulty': None, 'tool': 'pick'}},
                'repair': {'ability': 'str', 'difficulty': None, 'tool': 'hammer'},
            },
            {'from_place': 'b', 'to_place': 'c', 'lock': None, 'repair': None},
        ],
    }


def test_an_old_version_moves_its_bonuses_and_tools_into_aids():
    old = old_document()

    upgraded = upgrade_from_63(old)

    assert (upgraded['format'], SNAPSHOT_FORMAT, UPGRADES[63]) == (64, 64, upgrade_from_63)
    kit, pick, hammer = upgraded['items']
    assert kit == {'entry_id': 'kit', 'kind': 'consumable', 'aids': [{'act': 'treat', 'bonus': 2, 'wear': 'always'}]}
    # 그때의 도구는 보정이 없고 없어지지 않았다. 규칙이 없던 망치는 장비의 규칙이 새로 생긴다
    assert pick['aids'] == [{'act': 'pick', 'bonus': 0, 'wear': 'never'}]
    assert hammer == {'entry_id': 'hammer', 'kind': 'gear', 'aids': [{'act': 'repair', 'bonus': 0, 'wear': 'never'}]}
    first, second = upgraded['routes']
    assert first['lock']['pick'] == {'ability': 'dex', 'difficulty': None, 'needs_tool': True}
    assert first['repair'] == {'ability': 'str', 'difficulty': None, 'needs_tool': True}
    assert second == old['routes'][1]
    assert 'treat_bonus' in old['items'][0]


def test_an_old_check_without_a_tool_needs_none_and_an_aid_is_not_repeated():
    old = old_document()
    pick = {'entry_id': 'pick', 'kind': 'gear', 'aids': [{'act': 'pick', 'bonus': 3, 'wear': 'on_fail'}]}
    plain = {
        'from_place': 'c',
        'to_place': 'd',
        'lock': {'key': 'q', 'pick': {'ability': 'dex', 'tool': None}},
        'repair': None,
    }

    upgraded = upgrade_from_63({**old, 'items': [old['items'][0], pick], 'routes': [*old['routes'], plain]})

    assert upgraded['routes'][2]['lock']['pick'] == {'ability': 'dex', 'needs_tool': False}
    # 이미 따기를 거들던 물건의 거들기는 그대로다
    assert upgraded['items'][1]['aids'] == [{'act': 'pick', 'bonus': 3, 'wear': 'on_fail'}]


def test_an_upgraded_version_is_read():
    document = upgrade_from_63(old_document())

    # 읽을 수 있는 모양이다(물건 항목이 판에 있는지는 보지 않는 부분만 쓴다)
    assert [aid.act for aid in read_aids(document)] == ['treat', 'pick', 'repair']


def read_aids(document: dict) -> list:
    rules = [ItemRuleSnapshot.model_validate({**rule, 'entry_id': str(uuid.uuid4())}) for rule in document['items']]
    return [aid for rule in rules for aid in rule.aids]


def test_the_migration_moves_the_draft_and_takes_it_back():
    migration = load_migration('item_aids')
    old = old_document()

    routes, rules = migration.upgraded(old['routes'], old['items'])

    assert (routes, rules) == (upgrade_from_63(old)['routes'], upgrade_from_63(old)['items'])
    back_routes, back_rules = migration.downgraded(routes, rules)
    assert back_routes == old['routes']
    # 새로 생긴 망치의 규칙은 남는다(되돌릴 때 거들기만 뺀다)
    assert back_rules == [*old['items'], {'entry_id': 'hammer', 'kind': 'gear', 'treat_bonus': None}]


def test_the_migration_takes_back_only_what_a_treat_bonus_could_be():
    migration = load_migration('item_aids')
    gear = {'entry_id': 'splint', 'kind': 'gear', 'aids': [{'act': 'treat', 'bonus': 2, 'wear': 'never'}]}
    plain = {'entry_id': 'gauze', 'kind': 'consumable', 'aids': [{'act': 'treat', 'bonus': 0, 'wear': 'always'}]}

    _, rules = migration.downgraded([], [gear, plain])

    # 그때 치료 보정은 소모품에만, 1 이상이었다
    assert [rule['treat_bonus'] for rule in rules] == [None, None]


def test_the_migration_adds_no_rule_past_the_limit():
    migration = load_migration('item_aids')
    full = [{'entry_id': f'item-{number}', 'kind': 'gear'} for number in range(migration.MAX_ITEM_RULES)]
    routes = [{'from_place': 'a', 'to_place': 'b', 'lock': None, 'repair': {'ability': 'str', 'tool': 'hammer'}}]

    moved_routes, moved_rules = migration.upgraded(routes, full)

    assert len(moved_rules) == migration.MAX_ITEM_RULES
    assert moved_routes[0]['repair'] == {'ability': 'str', 'needs_tool': True}


async def test_a_published_version_keeps_the_aids(client: AsyncClient, me: dict, kit: dict):
    scenario = await route_doors.draft(client, me, kit, **the_map(kit))

    response = await route_doors.publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    rules = read_snapshot(response.json()['snapshot']).items
    assert [(rule.aids[0].act, rule.aids[0].bonus) for rule in rules] == [('pick', 2), ('force', 3), ('cross', 5)]


# --- 받기 ---


@pytest.mark.parametrize(
    ('name', 'action', 'code'),
    [
        ('rope', 'pick', status.HTTP_422_UNPROCESSABLE_CONTENT),
        ('lockpick', 'force', status.HTTP_422_UNPROCESSABLE_CONTENT),
        ('crowbar', 'force', status.HTTP_409_CONFLICT),
    ],
    ids=['does-not-aid-picking', 'does-not-aid-forcing', 'not-held'],
)
async def test_a_door_takes_only_a_held_thing_that_aids_it(
    client: AsyncClient, me: dict, friend: dict, kit: dict, session: AsyncSession, name: str, action: str, code: int
):
    table = await start(client, me, friend, kit)
    if code != status.HTTP_409_CONFLICT:
        await give(session, table, ME, kit[name])

    response = await declare(client, me, table, door(action, kit['square'], item=kit[name]))

    assert response.status_code == code, response.text


async def test_forcing_needs_no_tool_but_takes_one(client: AsyncClient, me: dict, friend: dict, kit: dict):
    table = await start(client, me, friend, kit)

    response = await declare(client, me, table, door('force', kit['square']))

    assert response.status_code == status.HTTP_200_OK, response.text


@pytest.mark.parametrize(
    ('name', 'place', 'code'),
    [
        ('rope', 'square', status.HTTP_422_UNPROCESSABLE_CONTENT),
        ('lockpick', 'tower', status.HTTP_422_UNPROCESSABLE_CONTENT),
    ],
    ids=['no-climb-on-the-way', 'does-not-aid-climbing'],
)
async def test_a_climb_takes_only_a_thing_that_aids_it(
    client: AsyncClient, me: dict, friend: dict, kit: dict, session: AsyncSession, name: str, place: str, code: int
):
    table = await start(client, me, friend, kit)
    await give(session, table, ME, kit[name])

    response = await declare(client, me, table, {**going(kit[place]), 'item': kit[name]['id']})

    assert response.status_code == code, response.text


async def test_a_climb_with_a_rope_is_saved_with_it(
    client: AsyncClient, me: dict, friend: dict, kit: dict, session: AsyncSession
):
    table = await start(client, me, friend, kit)
    await give(session, table, ME, kit['rope'])

    await declare(client, me, table, climbing(kit, kit['rope']))
    plain = await declare(client, friend, table, climbing(kit))

    rounds = (await client.get(table_url(table, '/rounds/1'), headers=me)).json()
    saved = {one['user_id']: one['action'] for one in rounds['declarations']}
    assert plain.status_code == status.HTTP_200_OK
    assert (saved[str(ME)]['place'], saved[str(ME)]['item']) == (kit['tower']['id'], kit['rope']['id'])
    assert next(action for user, action in saved.items() if user != str(ME))['item'] is None


# --- 닫힐 때 ---


async def test_a_lockpick_adds_its_bonus_and_stays_on_success(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, kit: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, kit)
    await give(session, table, ME, kit['lockpick'])
    load_dice(app, [13])

    await play(client, me, friend, table, narrated, mine=door('pick', kit['square'], item=kit['lockpick']))

    outcome = await door_outcome(client, me, table)
    assert (outcome['done'], outcome['check']['modifier'], outcome['check']['total']) == (True, 2, 15)
    assert outcome['aid'] == {
        'entry_id': kit['lockpick']['id'],
        'name': '락픽',
        'act': 'pick',
        'bonus': LOCKPICK_BONUS,
        'used': True,
        'lost': False,
        'broken': False,
        'reason': None,
        'remaining': 1,
    }
    assert held(await read_table(client, me, table), ME)['락픽'] == 1


async def test_a_lockpick_breaks_on_a_failed_pick(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, kit: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, kit)
    await give(session, table, ME, kit['lockpick'])
    load_dice(app, [12])

    await play(client, me, friend, table, narrated, mine=door('pick', kit['square'], item=kit['lockpick']))

    outcome = await door_outcome(client, me, table)
    assert (outcome['done'], outcome['reason']) == (False, 'failed')
    assert (outcome['aid']['lost'], outcome['aid']['broken'], outcome['aid']['remaining']) == (True, True, 0)
    assert '락픽' not in held(await read_table(client, me, table), ME)
    (rolled,) = await events_of(client, me, table, 'check_rolled')
    (aided,) = await events_of(client, me, table, 'aid_used')
    assert aided['caused_by_sequence'] == rolled['sequence']
    assert aided['payload'] == {
        'round': 1,
        'character_name': '기사',
        'act': 'pick',
        'entry_id': kit['lockpick']['id'],
        'name': '락픽',
        'bonus': LOCKPICK_BONUS,
        'lost': True,
        'broken': True,
        'remaining': 0,
    }
    # 서술자도 부러진 것을 안다
    second = (await client.get(table_url(table, '/rounds/current'), headers=me)).json()
    assert '(쓴 물건: 락픽 +2, 부러짐)' in second['scene']


async def test_a_crowbar_aids_forcing_and_is_kept(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, kit: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, kit)
    await give(session, table, ME, kit['crowbar'])
    load_dice(app, [17])

    await play(client, me, friend, table, narrated, mine=door('force', kit['square'], item=kit['crowbar']))

    outcome = await door_outcome(client, me, table)
    assert (outcome['done'], outcome['check']['total'], outcome['check']['target']) == (True, 20, 20)
    assert (outcome['aid']['used'], outcome['aid']['lost']) == (True, False)
    assert held(await read_table(client, me, table), ME)['쇠지렛대'] == 1


async def test_a_door_without_an_aid_has_no_aid_in_its_outcome(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, kit: dict, narrated
):
    table = await start(client, me, friend, kit)
    load_dice(app, [20])

    await play(client, me, friend, table, narrated, mine=door('force', kit['square']))

    assert (await door_outcome(client, me, table))['aid'] is None
    assert await events_of(client, me, table, 'aid_used') == []


async def test_a_rope_aids_a_climb(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, kit: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, kit)
    await give(session, table, ME, kit['rope'])
    load_dice(app, [10])

    await play(client, me, friend, table, narrated, mine=climbing(kit, kit['rope']))

    move = (await outcome_of(client, me, table, 1, ME))['move']
    assert (move['moved'], move['cross']['modifier'], move['cross']['total']) == (True, ROPE_BONUS, 15)
    assert (move['aid']['act'], move['aid']['used'], move['aid']['remaining']) == ('cross', True, 1)
    (rolled,) = await events_of(client, me, table, 'check_rolled')
    (aided,) = await events_of(client, me, table, 'aid_used')
    assert (aided['caused_by_sequence'], aided['payload']['act']) == (rolled['sequence'], 'cross')
    second = (await client.get(table_url(table, '/rounds/current'), headers=me)).json()
    assert '(쓴 물건: 밧줄 +5)' in second['scene']


async def test_a_rope_is_not_used_when_the_way_was_blocked_first(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, kit: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, kit)
    await give(session, table, ME, kit['rope'])
    await declare(client, me, table, climbing(kit, kit['rope']))
    # 받은 뒤 차례가 오기 전에 다른 곳으로 옮겨졌다. 이어진 길이 없어 넘기를 굴리지 않는다
    await map_tables.put_at(session, table, ME, kit['hut'])
    await declare(client, friend, table, None)
    await narrated()

    move = (await outcome_of(client, me, table, 1, ME))['move']
    assert (move['moved'], move['reason']) == (False, 'not_adjacent')
    assert (move['aid']['used'], move['aid']['lost'], move['aid']['reason']) == (False, False, None)
    assert await events_of(client, me, table, 'aid_used') == []


async def test_a_tool_lost_before_its_turn_leaves_the_lock_unpicked(
    client: AsyncClient, me: dict, friend: dict, kit: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, kit)
    await give(session, table, ME, kit['lockpick'])
    await declare(client, me, table, door('pick', kit['square'], item=kit['lockpick']))
    # 받은 뒤 차례가 오기 전에 락픽을 잃었다
    await take_away(session, table, ME, kit['lockpick'])
    await declare(client, friend, table, None)
    await narrated()

    outcome = await door_outcome(client, me, table)
    assert (outcome['done'], outcome['reason'], outcome['check']) == (False, 'no_tool', None)
    assert (outcome['aid']['used'], outcome['aid']['reason']) == (False, 'not_held')


async def test_a_crowbar_lost_before_its_turn_is_not_used(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, kit: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, kit)
    await give(session, table, ME, kit['crowbar'])
    load_dice(app, [17])
    await declare(client, me, table, door('force', kit['square'], item=kit['crowbar']))
    await take_away(session, table, ME, kit['crowbar'])
    await declare(client, friend, table, None)
    await narrated()

    outcome = await door_outcome(client, me, table)
    # 부수기는 맨손으로도 굴린다. 보정이 없어 17 은 어려움(20)에 못 닿는다
    assert (outcome['done'], outcome['check']['modifier'], outcome['aid']['used']) == (False, 0, False)
    assert len(await events_of(client, me, table, 'check_rolled')) == 1
    assert await events_of(client, me, table, 'aid_used') == []


# --- 서술 ---


def test_the_door_and_travel_lines_name_what_aided():
    broke = DoorNote(
        act='pick', other_end='광장', done=False, reason='failed', check='민첩', aid=AidNote('락픽', 2, True)
    )
    forced = DoorNote(act='force', other_end='광장', done=True, check='근력', aid=AidNote('쇠지렛대', 3))
    climbed = TravelNote(from_place='성문', to_place='탑', moved=True, cross='근력', aid=AidNote('밧줄'))

    assert describe_door(broke) == '(문: 광장 쪽 문을 따려 했다. 민첩 판정에 실패했다)(쓴 물건: 락픽 +2, 부러짐)'
    assert describe_door(forced) == '(문: 광장 쪽 문. 근력 판정에 성공해 문을 부숴 열었다)(쓴 물건: 쇠지렛대 +3)'
    assert describe_travel(climbed) == '(간 곳: 성문 → 탑, 근력 판정에 성공해 넘어)(쓴 물건: 밧줄)'


def test_the_narrator_hears_only_what_was_used():
    used = {'name': '락픽', 'bonus': 2, 'used': True, 'broken': True}

    assert to_aid(used) == AidNote('락픽', 2, True)
    assert to_aid({**used, 'used': False}) is None
    assert to_aid(None) is None
