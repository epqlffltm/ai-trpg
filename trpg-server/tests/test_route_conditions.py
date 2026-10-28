# trpg-server/tests/test_route_conditions.py

"""
길의 조건(#281)을 검증한다. 열쇠로 여는 자물쇠와, 지날 때마다 굴리는 넘기 판정이다.

맵과 픽스처는 tests/test_table_map.py 의 것이다. 방장(기사)과 함께 앉는 사람(약사), 시작은 성문.
여기에 물건 둘(탑 열쇠, 대장간 열쇠)을 더하고 길을 이렇게 놓는다.
  - 성문-광장: 탑 열쇠의 자물쇠. 잠긴 채 시작한다.
  - 성문-숲: 넘기 판정(근력, 난이도는 비워 규칙의 기본인 보통 15). 실패하면 가볍게(1d4) 다친다.
  - 광장-탑: 대장간 열쇠의 자물쇠. 열린 채 시작한다.
시트의 근력은 10(보정 0)이다. 주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다.

보는 것.
  - 시나리오: 조건을 저장하고 판에 굳힌다. 잘못 둔 것은 422, 게시할 수 없는 것은 409 의 문제다.
    옛 판은 조건이 없는 것으로 읽는다.
  - 맵: 자물쇠의 지금 상태와 넘기 판정이 보인다. 무슨 열쇠인지와 실패의 피해는 보이지 않는다.
  - 자물쇠: 열쇠가 없으면 가지 못한다. 맞는 열쇠를 지닌 사람은 열고 지나가고, 연 문은 열린 채다.
  - 넘기: 성공하면 지나가고, 실패하면 남고 판에 적힌 만큼 다친다. 판정은 check_rolled 로 남는다.
  - 서술: 맵의 나가는 길과 가기의 줄에 조건이 붙는다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import CrossSnapshot, Snapshot, read_snapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_51
from app.engine.dice import ScriptedDice
from app.engine.templates import SRD5
from app.rounds import map_actions, prompt
from app.rounds.move_lines import describe_travel
from app.rounds.narration_request import cross_ability_name, to_travel
from app.rounds.narrator import TravelNote
from tests import test_table_map as map_tables
from tests.narration_model import asset_body
from tests.test_character_death import load_dice
from tests.test_map_actions import going, outcome_of, play
from tests.test_table_items import FRIEND, ME, SCENARIOS_URL, events_of, give, held, post, read_table, table_url
from tests.test_table_map import open_duo, place_of, route
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

me = map_tables.me
friend = map_tables.friend
lore = map_tables.lore

# 난이도를 비웠다. 규칙의 기본 난이도(보통 15)로 굴린다
CLIMB = {'ability': 'str', 'harm': 'light'}


@pytest.fixture
async def keys(client: AsyncClient, me: dict, lore: dict) -> dict:
    """같은 로어북에 열쇠 둘(탑 열쇠, 대장간 열쇠)을 더한다."""
    url = f'{map_tables.LOREBOOKS_URL}/{lore["lorebook"]["id"]}/entries'

    async def entry(name: str) -> dict:
        return await post(client, url, me, name=name, keywords=[], content=f'{name}의 설명', kind='item')

    return {**lore, 'tower_key': await entry('탑 열쇠'), 'forge_key': await entry('대장간 열쇠')}


def locking(key: dict, locked: bool = True) -> dict:
    return {'key': key['id'], 'locked': locked}


def the_map(keys: dict, **fields) -> dict:
    """성문에서 시작한다. 성문-광장은 잠긴 문, 성문-숲은 오를 길, 광장-탑은 열린 문이다."""
    return {
        'start_place': keys['gate']['id'],
        'routes': [
            route(keys['gate'], keys['square'], lock=locking(keys['tower_key'])),
            route(keys['gate'], keys['forest'], cross=CLIMB),
            route(keys['square'], keys['tower'], lock=locking(keys['forge_key'], locked=False)),
        ],
        **fields,
    }


async def draft(client: AsyncClient, me: dict, keys: dict, **fields) -> dict:
    """길의 조건을 적은 시나리오. 게시하지 않았다."""
    rulebook = await post(client, map_tables.RULEBOOKS_URL, me, title='룰북')
    body = {
        'title': '성의 모험',
        'rulebook_id': rulebook['id'],
        'openings': ['성문 앞이다.'],
        'default_sheet': map_tables.SHEET,
        'lorebook_ids': [keys['lorebook']['id']],
        **the_map(keys),
        **fields,
    }
    return await post(client, SCENARIOS_URL, me, **body)


async def publish(client: AsyncClient, me: dict, scenario: dict):
    return await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)


async def start(client: AsyncClient, me: dict, friend: dict, keys: dict) -> dict:
    """길의 조건을 적은 판으로 둘이 앉아 시작한 테이블."""
    table = await open_duo(client, me, friend, keys, **the_map(keys))
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


def route_out(table: dict, start: dict, end: dict) -> dict:
    """테이블이 아는 맵에서 그 두 끝의 길."""
    return next(
        item for item in table['map']['routes'] if (item['from_place'], item['to_place']) == (start['id'], end['id'])
    )


def hp_of(table: dict, user_id: uuid.UUID) -> int:
    member = next(member for member in table['members'] if member['user_id'] == str(user_id))
    return member['sheet']['hp']


# --- 시나리오 ---


async def test_conditions_are_saved_and_published(client: AsyncClient, me: dict, keys: dict):
    scenario = await draft(client, me, keys)

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    gate_square, gate_forest, square_tower = scenario['routes']
    assert gate_square['lock'] == {'key': keys['tower_key']['id'], 'locked': True, 'pick': None}
    assert gate_square['cross'] is None
    assert (gate_forest['lock'], gate_forest['cross']) == (None, {**CLIMB, 'difficulty': None})
    assert square_tower['lock'] == {'key': keys['forge_key']['id'], 'locked': False, 'pick': None}
    routes = read_snapshot(response.json()['snapshot']).routes
    assert routes[0].lock.key == uuid.UUID(keys['tower_key']['id'])
    assert (routes[1].cross.ability, routes[1].cross.difficulty, routes[1].cross.harm) == ('str', None, 'light')


@pytest.mark.parametrize(
    'condition',
    [
        {'cross': {'ability': 'str', 'height': 3}},
        {'cross': {'difficulty': 'medium'}},
        {'lock': {'locked': True}},
        {'lock': {'key': 'not-an-id'}},
    ],
)
async def test_a_misshaped_condition_is_refused(client: AsyncClient, me: dict, keys: dict, condition: dict):
    body = {'title': '성의 모험', 'routes': [route(keys['gate'], keys['square'], **condition)]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    ('case', 'problem'),
    [
        ('no-ability', 'route_cross_invalid'),
        ('no-difficulty', 'route_cross_invalid'),
        ('no-harm', 'route_cross_invalid'),
        ('key-twice', 'route_key_repeated'),
        ('key-missing', 'item_entry_missing'),
        ('key-not-item', 'item_not_item'),
    ],
)
async def test_a_condition_must_fit_the_rules(client: AsyncClient, me: dict, keys: dict, case: str, problem: str):
    nowhere = {'id': str(uuid.uuid4())}
    conditions = {
        'no-ability': {'cross': {**CLIMB, 'ability': 'luck'}},
        'no-difficulty': {'cross': {**CLIMB, 'difficulty': 'impossible'}},
        'no-harm': {'cross': {**CLIMB, 'harm': 'deadly'}},
        # 광장-탑의 자물쇠와 같은 열쇠다
        'key-twice': {'lock': locking(keys['forge_key'])},
        'key-missing': {'lock': locking(nowhere)},
        'key-not-item': {'lock': locking(keys['hut'])},
    }
    routes = [
        route(keys['gate'], keys['forest'], **conditions[case]),
        route(keys['square'], keys['tower'], lock=locking(keys['forge_key'])),
    ]
    scenario = await draft(client, me, keys, routes=routes)

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == [problem]


async def test_the_snapshot_refuses_a_wrong_key(client: AsyncClient, me: dict, keys: dict):
    document = (await publish(client, me, await draft(client, me, keys))).json()['snapshot']
    first, *rest = document['routes']
    not_item = {**first, 'lock': {'key': keys['hut']['id'], 'locked': True}}
    twice = {**first, 'lock': {'key': keys['forge_key']['id'], 'locked': True}}

    for routes in ([not_item, *rest], [twice, *rest]):
        with pytest.raises(ValidationError):
            Snapshot.model_validate({**document, 'routes': routes})
    Snapshot.model_validate(document)


def test_an_old_snapshot_reads_as_no_conditions():
    document = {'format': 51, 'routes': [{'from_place': 'a', 'to_place': 'b'}]}

    upgraded = upgrade_from_51(document)

    assert upgraded['format'] == 52
    assert upgraded['routes'] == [{'from_place': 'a', 'to_place': 'b', 'cross': None, 'lock': None}]
    assert 'cross' not in document['routes'][0]
    assert UPGRADES[51] is upgrade_from_51
    assert upgrade_from_51({'format': 51})['routes'] == []


# --- 맵 ---


async def test_the_map_shows_locks_and_climbs_but_not_keys(client: AsyncClient, me: dict, friend: dict, keys: dict):
    table = await start(client, me, friend, keys)

    assert route_out(table, keys['gate'], keys['square']) == {
        'from_place': keys['gate']['id'],
        'to_place': keys['square']['id'],
        'two_way': True,
        'travel_minutes': None,
        'locked': True,
        'cross': None,
        'barred': None,
        'bar_side': None,
        'broken': False,
        'pick': None,
        'force': None,
        'repair': None,
    }
    # 판에 난이도를 비워도 규칙의 기본 난이도로 보인다. 실패의 피해는 보이지 않는다
    assert route_out(table, keys['gate'], keys['forest'])['cross'] == {'ability': 'str', 'difficulty': 'medium'}
    assert route_out(table, keys['gate'], keys['forest'])['locked'] is None
    assert route_out(table, keys['square'], keys['tower'])['locked'] is False


# --- 자물쇠 ---


async def test_without_the_key_the_door_stays_shut(client: AsyncClient, me: dict, friend: dict, keys: dict, narrated):
    table = await start(client, me, friend, keys)

    await play(client, me, friend, table, narrated, mine=going(keys['square']))

    move = (await outcome_of(client, me, table, 1, ME))['move']
    assert (move['moved'], move['reason'], move['unlocked']) == (False, 'locked', False)
    assert place_of(await read_table(client, me, table), ME) == keys['gate']['id']
    assert await events_of(client, me, table, 'character_moved') == []


async def test_another_key_does_not_fit(
    client: AsyncClient, me: dict, friend: dict, keys: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, keys)
    await give(session, table, ME, keys['forge_key'])

    await play(client, me, friend, table, narrated, mine=going(keys['square']))

    assert (await outcome_of(client, me, table, 1, ME))['move']['reason'] == 'locked'


async def test_the_right_key_opens_the_door_for_good(
    client: AsyncClient, me: dict, friend: dict, keys: dict, session: AsyncSession, narrated
):
    table = await start(client, me, friend, keys)
    await give(session, table, ME, keys['tower_key'])

    await play(client, me, friend, table, narrated, mine=going(keys['square']))
    # 열쇠가 없는 약사도 연 문으로는 지나간다
    await play(client, me, friend, table, narrated, theirs=going(keys['square']))

    seen = await read_table(client, friend, table)
    assert place_of(seen, ME) == place_of(seen, FRIEND) == keys['square']['id']
    assert route_out(seen, keys['gate'], keys['square'])['locked'] is False
    assert (await outcome_of(client, me, table, 1, ME))['move']['unlocked'] is True
    assert (await outcome_of(client, me, table, 2, FRIEND))['move']['unlocked'] is False
    # 연 사람의 이동에만 unlocked 가 붙는다. 열쇠는 그대로 지닌다
    opened, passed = await events_of(client, me, table, 'character_moved')
    assert (opened['payload']['unlocked'], 'unlocked' in passed['payload']) == (True, False)
    assert ('탑 열쇠', 1) in held(seen, ME)


# --- 넘기 ---


async def test_a_good_climb_gets_across(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, keys: dict, narrated
):
    table = await start(client, me, friend, keys)
    load_dice(app, [15])

    await play(client, me, friend, table, narrated, mine=going(keys['forest']))

    move = (await outcome_of(client, me, table, 1, ME))['move']
    assert (move['moved'], move['reason'], move['effect']) == (True, None, None)
    assert move['cross'] == {
        'ability': 'str',
        'difficulty': 'medium',
        'roll': 15,
        'modifier': 0,
        'total': 15,
        'target': 15,
        'success': True,
        'hindrance': None,
    }
    (rolled,) = await events_of(client, me, table, 'check_rolled')
    assert (rolled['payload']['ability'], rolled['payload']['success']) == ('str', True)
    assert place_of(await read_table(client, me, table), ME) == keys['forest']['id']


async def test_a_bad_climb_hurts_and_stays(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, keys: dict, narrated
):
    table = await start(client, me, friend, keys)
    # 판정의 눈 3(실패), 피해의 눈 2
    load_dice(app, [3, 2])

    await play(client, me, friend, table, narrated, mine=going(keys['forest']))

    move = (await outcome_of(client, me, table, 1, ME))['move']
    assert (move['moved'], move['reason'], move['cross']['success']) == (False, 'cross_failed', False)
    assert (move['effect']['kind'], move['effect']['amount'], move['effect']['after']) == ('damage', 2, 8)
    seen = await read_table(client, me, table)
    assert (place_of(seen, ME), hp_of(seen, ME)) == (keys['gate']['id'], 8)
    (rolled,) = await events_of(client, me, table, 'check_rolled')
    (changed,) = await events_of(client, me, table, 'hp_changed')
    assert changed['caused_by_sequence'] == rolled['sequence']
    assert await events_of(client, me, table, 'character_moved') == []


# --- 서술 ---


async def test_the_narrator_hears_the_conditions(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, keys: dict, narrated
):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    table = await start(client, me, friend, keys)
    load_dice(app, [3, 2])

    await play(client, me, friend, table, narrated, mine=going(keys['forest']))

    (request,) = narrator.requests
    knight = next(move for move in request.moves if move.character_name == '기사')
    assert knight.place.exits == ['광장(잠긴 문)', '숲(넘기: 근력)']
    assert knight.travel == TravelNote(
        from_place='성문', to_place='숲', moved=False, reason='cross_failed', cross='근력', hurt=True
    )


def test_the_travel_line_tells_the_conditions():
    opened = TravelNote(from_place='성문', to_place='광장', moved=True, unlocked=True, cross='근력')
    shut = TravelNote(from_place='성문', to_place='광장', moved=False, reason='locked')
    slipped = TravelNote(from_place='성문', to_place='숲', moved=False, reason='cross_failed', cross='근력')

    assert describe_travel(opened) == '(간 곳: 성문 → 광장, 열쇠로 문을 열고, 근력 판정에 성공해 넘어)'
    assert describe_travel(shut) == '(가려던 곳: 광장. 문이 잠겨 있었고 맞는 열쇠가 없었다)'
    assert describe_travel(slipped) == '(가려던 곳: 숲. 근력 판정에 실패해 넘지 못했다)'
    fell = TravelNote(from_place='성문', to_place='숲', moved=False, reason='cross_failed', cross='근력', hurt=True)
    assert describe_travel(fell) == '(가려던 곳: 숲. 근력 판정에 실패해 넘지 못했다. 실패해 다쳤다)'


def test_the_narrator_hears_a_door_opened():
    move = {
        'user_id': str(ME),
        'character_name': '기사',
        'from': {'entry_id': str(uuid.uuid4()), 'name': '성문'},
        'to': {'entry_id': str(uuid.uuid4()), 'name': '광장'},
        'moved': True,
        'reason': None,
        'unlocked': True,
        'cross': None,
        'effect': None,
    }

    note = to_travel(SimpleNamespace(outcome={'move': move}), SRD5)

    assert (note.unlocked, note.cross, note.hurt) == (True, None, False)


def test_a_climb_without_harm_hurts_no_one():
    assert map_actions.fall(SimpleNamespace(), SimpleNamespace(), CrossSnapshot(ability='str')) is None


def test_the_cross_is_named_by_the_rules():
    assert cross_ability_name(SRD5, {'ability': 'str'}) == '근력'
    assert cross_ability_name(SRD5, {'ability': 'luck'}) == 'luck'
    assert cross_ability_name(None, {'ability': 'str'}) == 'str'
    assert cross_ability_name(SRD5, None) is None


def test_the_map_note_forbids_opening_by_words():
    assert '잠긴 문' in prompt.MAP_NOTE
    assert prompt.PROMPT_VERSION == 'narration-78'


def test_the_climb_feels_the_injuries_on_its_ability(monkeypatch: pytest.MonkeyPatch):
    asked = []
    hindrance_for = map_actions.round_injuries.hindrance_for

    def spy(ruleset, injuries, ability):
        asked.append(ability)
        return hindrance_for(ruleset, injuries, ability)

    monkeypatch.setattr(map_actions.round_injuries, 'hindrance_for', spy)
    judging = SimpleNamespace(ruleset=SRD5, dice=ScriptedDice([20]))
    member = SimpleNamespace(sheet=SimpleNamespace(abilities={'str': 10, 'dex': 10}, injuries=[]))

    rolled = map_actions.roll_terms(judging, member, CrossSnapshot(ability='str'))

    assert (asked, rolled.check.success) == (['str'], True)
