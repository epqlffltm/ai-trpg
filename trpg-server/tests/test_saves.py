# trpg-server/tests/test_saves.py

"""
세이브와 관통(#276)을 검증한다. app/engine/armor.py, app/rounds/blows.py.

판: 룰북은 SRD5 템플릿에서 방어 규칙만 바꿔 만든다(세이브: 목표값 15, 관통의 기준값 10). 주사위는 d20 이다.
  물건: 볼터(손, 공격 +1, 관통력 4), 장검(손, 공격 +2), 판금 갑옷(몸, 방어 5), 역장 발생기(보조손, 불굴 3)
  캐릭터(엘프): 모든 능력치 10(보정 0), 최대 HP 10. 볼터(주손)와 판금 갑옷(몸)을 착용하고 장검을 들고 시작한다.
  몬스터(고블린, 최대 HP 30): 수로 입구에 한 마리. 시험마다 장비와 타고난 불굴 세이브와 공격을 바꾼다.
주사위의 차례: 부위(1~7, 3~6 이 몸) → 관통(무기에 관통력이 있고 그 부위에 방어가 있을 때) → 맞히기 → 세이브 → 피해.

보는 것.
  - 룰북: 만들 때와 고칠 때 방어 규칙을 고른다. 세이브 방식에는 목표값이 있어야 한다.
  - 세이브: 맞힌 뒤 맞는 쪽이 굴린다. 눈 + 그 부위의 방어가 목표값 이상이면 막고, 아무것도 바뀌지 않는다.
  - 관통: 눈 + 관통력이 그 부위의 방어 + 기준값 이상이면 관통한다. 아머로는 막지 못하고(ac 는 목표값이 오르지 않고,
    reduce 는 깎이지 않는다), 불굴 세이브만 남는다. 불굴과 아머 중 큰 값으로 한 번 굴린다.
  - 몬스터의 공격도 같다. 캐릭터가 세이브로 막으면 HP 가 그대로다.
  - 기록과 서술에 관통과 세이브가 붙는다(narration-53).
맨 아래에는 DB 를 쓰지 않는 작은 함수들의 테스트가 있다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.schemas import ItemRule, MonsterSheet
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_48
from app.engine import armor
from app.engine.armor import Pierce, Protection, Save, Worn
from app.engine.dice import ScriptedDice
from app.engine.ruleset import Armor, ArmorMode
from app.engine.templates import SRD5
from app.events.models import EventType, TableEvent
from app.main import API_PREFIX
from app.rounds import blows
from app.rounds.models import Round
from app.rounds.move_lines import describe_blow
from app.rounds.narrator import BlowNote
from app.transcripts.labels import Labels
from app.transcripts.markdown import render_event
from tests.narration_model import asset_body
from tests.sheets import SHEET, make_sheet
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
BESTIARIES_URL = f'{API_PREFIX}/bestiaries'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
HANDS = ['main_hand', 'off_hand']
SAVE = {'mode': 'save', 'save_target': 15, 'pierce_base': 10}
BODY = 4
SLASH = '고블린을 쏜다.'


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    return {'Authorization': f'Bearer {make_token(signing_key, make_access_claims(sub=str(user_id)))}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, ME)


def load_dice(app: FastAPI, rolls: list[int]) -> ScriptedDice:
    dice = ScriptedDice(rolls)
    app.state.dice = dice
    return dice


async def post(client: AsyncClient, url: str, headers: dict, **body) -> dict:
    response = await client.post(url, json=asset_body(url, body), headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def table_url(table: dict, path: str = '') -> str:
    return f'{TABLES_URL}/{table["id"]}{path}'


async def make_parts(client: AsyncClient, me: dict, armor_rule: dict | None) -> dict:
    """로어북(입구와 물건 넷), 도감(고블린), 방어 규칙을 고른 룰북."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='수로')
    url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'

    async def entry(name: str, kind: str = 'item') -> dict:
        return await post(client, url, me, name=name, keywords=[], content=f'{name}의 설정', kind=kind)

    bestiary = await post(client, BESTIARIES_URL, me, title='수로의 것들')
    return {
        'lorebook': lorebook,
        'bestiary': bestiary,
        'goblin': await post(client, f'{BESTIARIES_URL}/{bestiary["id"]}/monsters', me, name='고블린', kind='humanoid'),
        'rulebook': await post(client, RULEBOOKS_URL, me, title='룰북', armor=armor_rule),
        'gate': await entry('수로 입구', 'place'),
        'bolter': await entry('볼터'),
        'sword': await entry('장검'),
        'plate': await entry('판금 갑옷'),
        'field': await entry('역장 발생기'),
    }


def item_rules(parts: dict) -> list[dict]:
    return [
        {'entry_id': parts['bolter']['id'], 'slots': HANDS, 'attack': 1, 'ap': 4},
        {'entry_id': parts['sword']['id'], 'slots': HANDS, 'attack': 2},
        {'entry_id': parts['plate']['id'], 'slots': ['body'], 'defense': 5},
        {'entry_id': parts['field']['id'], 'slots': ['off_hand'], 'ward': 3},
    ]


def starting(parts: dict) -> list[dict]:
    return [
        {'entry_id': parts['bolter']['id'], 'count': 1, 'wear': ['main_hand']},
        {'entry_id': parts['plate']['id'], 'count': 1, 'wear': ['body']},
        {'entry_id': parts['sword']['id'], 'count': 1},
    ]


def plate_on_body(parts: dict) -> list[dict]:
    return [{'entry_id': parts['plate']['id'], 'wear': ['body']}]


async def start(
    client: AsyncClient, me: dict, armor_rule: dict | None = SAVE, equipment=None, **sheet_fields
) -> tuple[dict, dict]:
    """판을 게시하고 테이블을 시작한다. 엘프 혼자 앉는다. 고블린의 장비는 equipment(부품을 받는 함수)다."""
    parts = await make_parts(client, me, armor_rule)
    goblin = {'monster_id': parts['goblin']['id'], 'sheet': make_sheet(max_hp=30), **sheet_fields}
    if equipment is not None:
        goblin['equipment'] = equipment(parts)
    body = {
        'title': '수로',
        'rulebook_id': parts['rulebook']['id'],
        'lorebook_ids': [parts['lorebook']['id']],
        'bestiary_ids': [parts['bestiary']['id']],
        'openings': ['물 떨어지는 소리가 난다.'],
        'default_sheet': SHEET,
        'items': item_rules(parts),
        'starting_items': starting(parts),
        'monster_sheets': [goblin],
        'start_place': parts['gate']['id'],
        'encounters': [{'place_id': parts['gate']['id'], 'monster_id': parts['goblin']['id'], 'count': 1}],
    }
    scenario = await post(client, SCENARIOS_URL, me, **body)
    published = await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)
    assert published.status_code == status.HTTP_201_CREATED, published.text
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return parts, table


async def goblin_id(client: AsyncClient, me: dict, table: dict) -> str:
    response = await client.get(table_url(table, '/rounds/current/people'), headers=me)
    (goblin,) = response.json()['monsters']
    return goblin['id']


def shot(goblin: str, **fields) -> dict:
    """근력으로 보통(15)에 도전한다. 성공하면 고블린이 1d8 만큼 다친다."""
    return {'kind': 'check', 'ability': 'str', 'difficulty': 'medium', 'harm': 'moderate', 'monster': goblin, **fields}


async def outcome_of(client: AsyncClient, me: dict, table: dict, action: dict) -> dict:
    body = {'content': SLASH, 'action': action}
    response = await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=me)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()['declarations'][0]['outcome']


# --- 룰북에서 고른다 ---


async def test_a_rulebook_picks_and_changes_its_armor(client: AsyncClient, me: dict):
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북', armor=SAVE)
    url = f'{RULEBOOKS_URL}/{rulebook["id"]}'

    assert rulebook['rules']['armor'] == SAVE
    changed = await client.patch(url, json={'armor': {'mode': 'reduce'}}, headers=me)
    assert changed.json()['rules']['armor'] == {'mode': 'reduce', 'save_target': None, 'pierce_base': 10}
    renamed = await client.patch(url, json={'title': '새 룰북'}, headers=me)
    assert (renamed.json()['title'], renamed.json()['rules']['armor']['mode']) == ('새 룰북', 'reduce')
    cleared = await client.patch(url, json={'armor': None}, headers=me)
    assert cleared.json()['rules']['armor'] is None
    # 다른 규칙은 그대로다
    assert cleared.json()['rules']['abilities'] == SRD5.model_dump(mode='json')['abilities']


async def test_without_a_choice_the_template_armor_is_used(client: AsyncClient, me: dict):
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북')

    assert rulebook['rules']['armor'] == {'mode': 'ac', 'save_target': None, 'pierce_base': 10}


@pytest.mark.parametrize(
    'armor_rule', [{'mode': 'save'}, {'mode': 'ac', 'save_target': 15}, {'mode': 'save', 'save_target': 0}]
)
async def test_a_wrong_armor_rule_is_refused(client: AsyncClient, me: dict, armor_rule: dict):
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북')

    created = await client.post(RULEBOOKS_URL, json={'title': '룰북', 'armor': armor_rule}, headers=me)
    changed = await client.patch(f'{RULEBOOKS_URL}/{rulebook["id"]}', json={'armor': armor_rule}, headers=me)

    assert (created.status_code, changed.status_code) == (422, 422)


# --- 세이브 ---


async def test_a_save_stops_the_blow(client: AsyncClient, app: FastAPI, me: dict):
    parts, table = await start(client, me, equipment=plate_on_body)
    goblin = await goblin_id(client, me, table)
    # 몸에 맞음(판금 5). 장검이 없어 관통이 없다. 맞히기 15(목표 그대로 15). 세이브 10 + 5 = 15 → 막음
    dice = load_dice(app, [BODY, 15, 10])

    outcome = await outcome_of(client, me, table, shot(goblin))

    assert (outcome['success'], outcome['target'], outcome['monster_effect']) == (True, 15, None)
    assert outcome['blow']['save'] == {'kind': 'armor', 'value': 5, 'roll': 10, 'target': 15, 'saved': True}
    assert outcome['blow']['pierce'] is None
    assert dice.remaining == 0


async def test_a_failed_save_lets_the_damage_in(client: AsyncClient, app: FastAPI, me: dict):
    _, table = await start(client, me, equipment=plate_on_body)
    goblin = await goblin_id(client, me, table)
    load_dice(app, [BODY, 15, 9, 6])

    outcome = await outcome_of(client, me, table, shot(goblin))

    assert outcome['blow']['save']['saved'] is False
    assert outcome['monster_effect']['amount'] == 6


async def test_nothing_to_save_with_rolls_no_save(client: AsyncClient, app: FastAPI, me: dict):
    _, table = await start(client, me)
    goblin = await goblin_id(client, me, table)
    dice = load_dice(app, [15, 6])

    outcome = await outcome_of(client, me, table, shot(goblin))

    assert outcome['blow'] is None
    assert dice.remaining == 0


# --- 관통 ---


@pytest.mark.parametrize(
    ('armor_rule', 'rolls', 'target', 'amount'),
    [
        # 관통 11 + 4 = 15 ≥ 5 + 10. 세이브할 것이 없다. 피해 6
        (SAVE, [BODY, 11, 15, 6], 15, 6),
        # ac: 관통해서 목표값이 오르지 않는다
        (None, [BODY, 11, 15, 6], 15, 6),
        # reduce: 관통해서 깎이지 않는다
        ({'mode': 'reduce'}, [BODY, 11, 15, 6], 15, 6),
    ],
)
async def test_a_piercing_weapon_goes_through_armor(
    client: AsyncClient, app: FastAPI, me: dict, armor_rule, rolls: list[int], target: int, amount: int
):
    parts, table = await start(client, me, armor_rule=armor_rule or {'mode': 'ac'}, equipment=plate_on_body)
    goblin = await goblin_id(client, me, table)
    dice = load_dice(app, rolls)

    outcome = await outcome_of(client, me, table, shot(goblin, weapon=parts['bolter']['id']))

    assert outcome['blow']['pierce'] == {'roll': 11, 'ap': 4, 'target': 15, 'pierced': True}
    assert (outcome['target'], outcome['total']) == (target, 16)
    assert outcome['monster_effect']['amount'] == amount
    assert outcome['blow']['save'] is None
    assert dice.remaining == 0


@pytest.mark.parametrize(
    ('armor_rule', 'rolls', 'target', 'amount'),
    [({'mode': 'ac'}, [BODY, 10, 19, 6], 20, 6), ({'mode': 'reduce'}, [BODY, 10, 15, 6], 15, 1)],
)
async def test_a_failed_pierce_leaves_the_armor(
    client: AsyncClient, app: FastAPI, me: dict, armor_rule, rolls: list[int], target: int, amount: int
):
    parts, table = await start(client, me, armor_rule=armor_rule, equipment=plate_on_body)
    goblin = await goblin_id(client, me, table)
    load_dice(app, rolls)

    outcome = await outcome_of(client, me, table, shot(goblin, weapon=parts['bolter']['id']))

    assert outcome['blow']['pierce']['pierced'] is False
    assert outcome['target'] == target
    assert outcome['monster_effect']['amount'] == amount


async def test_a_ward_still_saves_against_a_piercing_blow(client: AsyncClient, app: FastAPI, me: dict):
    parts, table = await start(client, me, equipment=plate_on_body, ward=3)
    goblin = await goblin_id(client, me, table)
    # 관통했다. 아머는 없고 불굴 3 이 남는다. 12 + 3 = 15 → 막음
    load_dice(app, [BODY, 11, 15, 12])

    outcome = await outcome_of(client, me, table, shot(goblin, weapon=parts['bolter']['id']))

    assert outcome['blow']['save'] == {'kind': 'ward', 'value': 3, 'roll': 12, 'target': 15, 'saved': True}
    assert outcome['monster_effect'] is None


async def test_the_better_save_is_rolled(client: AsyncClient, app: FastAPI, me: dict):
    _, table = await start(client, me, equipment=plate_on_body, ward=3)
    goblin = await goblin_id(client, me, table)
    # 관통 없음. 아머 5 가 불굴 3 보다 크다
    load_dice(app, [BODY, 15, 10])

    outcome = await outcome_of(client, me, table, shot(goblin))

    assert (outcome['blow']['save']['kind'], outcome['blow']['save']['value']) == ('armor', 5)


async def test_a_worn_ward_saves_too(client: AsyncClient, app: FastAPI, me: dict):
    def field_and_plate(parts: dict) -> list[dict]:
        return [*plate_on_body(parts), {'entry_id': parts['field']['id'], 'wear': ['off_hand']}]

    parts, table = await start(client, me, equipment=field_and_plate)
    goblin = await goblin_id(client, me, table)
    # 관통했다. 착용한 역장 발생기의 불굴 3 으로 굴린다
    load_dice(app, [BODY, 11, 15, 12])

    outcome = await outcome_of(client, me, table, shot(goblin, weapon=parts['bolter']['id']))

    assert (outcome['blow']['save']['kind'], outcome['blow']['save']['saved']) == ('ward', True)


async def test_a_miss_rolls_no_save(client: AsyncClient, app: FastAPI, me: dict):
    _, table = await start(client, me, equipment=plate_on_body)
    goblin = await goblin_id(client, me, table)
    dice = load_dice(app, [BODY, 5])

    outcome = await outcome_of(client, me, table, shot(goblin))

    assert (outcome['success'], outcome['blow']['save']) == (False, None)
    assert dice.remaining == 0


# --- 몬스터의 공격 ---


async def test_the_character_saves_against_a_monster(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    claw = [{'name': '할퀴기', 'ability': 'str', 'difficulty': 'medium', 'harm': 'light'}]
    _, table = await start(client, me, sheet=make_sheet(max_hp=30, dex=14), attacks=claw)
    # 고블린이 먼저. 엘프의 몸(판금 5)에 맞음, 맞히기 15, 세이브 10 + 5 → 막음. 엘프는 숨는다(판정 1)
    dice = load_dice(app, [BODY, 15, 10, 1])

    body = {'content': '숨는다.', 'action': {'kind': 'check', 'ability': 'dex', 'difficulty': 'medium'}}
    await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=me)

    query = select(Round).where(Round.table_id == uuid.UUID(table['id']), Round.number == 1)
    turn = (await session.scalar(query.execution_options(populate_existing=True))).turns[0]['outcome']
    assert (turn['success'], turn['effect'], turn['blow']['save']['saved']) == (True, None, True)
    assert dice.remaining == 0


async def test_a_monster_miss_rolls_no_save(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession):
    claw = [{'name': '할퀴기', 'ability': 'str', 'difficulty': 'medium', 'harm': 'light'}]
    _, table = await start(client, me, sheet=make_sheet(max_hp=30, dex=14), attacks=claw)
    dice = load_dice(app, [BODY, 5, 1])

    body = {'content': '숨는다.', 'action': {'kind': 'check', 'ability': 'dex', 'difficulty': 'medium'}}
    await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=me)

    query = select(Round).where(Round.table_id == uuid.UUID(table['id']), Round.number == 1)
    turn = (await session.scalar(query.execution_options(populate_existing=True))).turns[0]['outcome']
    assert (turn['success'], turn['blow']['save']) == (False, None)
    assert dice.remaining == 0


# --- 기록과 서술 ---


async def test_the_save_is_recorded_and_narrated(client: AsyncClient, app: FastAPI, me: dict, narrated):
    parts, table = await start(client, me, equipment=plate_on_body)
    goblin = await goblin_id(client, me, table)
    # 관통 못 함(10 + 4 < 15), 맞힘(15 + 1), 세이브 6 + 5 < 15 → 못 막음, 피해 4
    load_dice(app, [BODY, 10, 15, 6, 4])

    await outcome_of(client, me, table, shot(goblin, weapon=parts['bolter']['id']))
    await narrated()

    response = await client.get(table_url(table, '/events'), params={'limit': 100}, headers=me)
    (rolled,) = [event for event in response.json()['items'] if event['type'] == 'check_rolled']
    assert rolled['payload']['blow']['pierce']['pierced'] is False
    scene = (await client.get(table_url(table, '/rounds/current'), headers=me)).json()['scene']
    assert '방어 5(세이브) · 관통 못 함 · 아머 세이브 5: 못 막음' in scene


async def test_the_catalog_shows_the_pierce_and_the_ward(client: AsyncClient, me: dict):
    _, table = await start(client, me)

    detail = (await client.get(table_url(table), headers=me)).json()

    numbers = {item['name']: (item['ap'], item['ward']) for item in detail['items']}
    assert (numbers['볼터'], numbers['역장 발생기'], numbers['장검']) == ((4, None), (None, 3), (None, None))
    assert detail['rules']['armor'] == SAVE


# --- DB 를 쓰지 않는 것 ---


@pytest.mark.parametrize(
    'body',
    [
        {'slots': ['main_hand'], 'ap': 3},
        {'ward': 2},
        {'slots': ['main_hand'], 'attack': 1, 'ap': 11},
    ],
)
def test_wrong_pierce_or_ward_is_refused(body: dict):
    with pytest.raises(ValidationError):
        ItemRule.model_validate({'entry_id': str(ME), **body})


def test_a_monster_ward_is_one_to_ten():
    with pytest.raises(ValidationError):
        MonsterSheet.model_validate({'monster_id': str(ME), 'sheet': SHEET, 'ward': 0})


@pytest.mark.parametrize(
    'body',
    [{'mode': 'save'}, {'mode': 'reduce', 'save_target': 10}, {'mode': 'ac', 'pierce_base': -1}],
)
def test_a_wrong_armor_is_refused(body: dict):
    with pytest.raises(ValidationError):
        Armor.model_validate(body)


SAVE_RULES = SRD5.model_copy(update={'armor': Armor(mode=ArmorMode.SAVE, save_target=15)})


def test_the_ward_is_the_best_not_the_sum():
    protection = armor.protection_of([Worn(('off_hand',), ward=3), Worn(('head',), ward=2)], {}, natural_ward=1)

    assert protection.ward == 3
    assert armor.protection_of([], {}, natural_ward=4).ward == 4


@pytest.mark.parametrize(
    ('rules', 'ap', 'defense', 'expected'),
    [
        (SRD5, 0, 5, None),
        (SRD5, 4, 0, None),
        (SRD5.model_copy(update={'armor': None}), 4, 5, None),
        (SRD5, 4, 5, Pierce(roll=11, ap=4, target=15, pierced=True)),
        (SRD5, 3, 5, Pierce(roll=11, ap=3, target=15, pierced=False)),
    ],
)
def test_a_pierce_is_rolled_only_against_armor(rules, ap: int, defense: int, expected):
    assert armor.roll_pierce(rules, ScriptedDice([11]), ap, defense) == expected


def test_holding_drops_to_zero_when_pierced():
    assert armor.holding(5, None) == 5
    assert armor.holding(5, Pierce(1, 1, 1, True)) == 0
    assert armor.holding(5, Pierce(1, 1, 99, False)) == 5


@pytest.mark.parametrize(
    ('defense', 'ward', 'expected'),
    [(0, 0, None), (5, 3, ('armor', 5)), (3, 3, ('armor', 3)), (2, 3, ('ward', 3)), (0, 1, ('ward', 1))],
)
def test_the_better_save_is_chosen(defense: int, ward: int, expected):
    assert armor.save_terms(defense, ward) == expected


def test_a_save_is_rolled_only_in_the_save_mode():
    assert armor.roll_save(SRD5, ScriptedDice([]), 5, 3) is None
    assert armor.roll_save(SAVE_RULES, ScriptedDice([]), 0, 0) is None
    assert armor.roll_save(SAVE_RULES, ScriptedDice([10]), 5, 0) == Save('armor', 5, 10, 15, True)
    assert armor.roll_save(SAVE_RULES, ScriptedDice([9]), 5, 0) == Save('armor', 5, 9, 15, False)


def judging_with(ruleset, rolls) -> SimpleNamespace:
    return SimpleNamespace(ruleset=ruleset, dice=ScriptedDice(list(rolls)), items={})


def test_a_blow_rolls_the_part_then_the_pierce():
    weapon = blows.Weapon(ME, '볼터', 1, ap=4)

    blow = blows.plan_blow(judging_with(SRD5, [BODY, 11]), weapon, Protection(by_slot={'body': 5}, ward=2), None)

    assert (blow.location, blow.defense, blow.raise_by, blow.cut, blow.ward) == ('body', 5, 0, 0, 2)
    assert blow.pierce.pierced is True


def test_a_save_after_a_pierce_has_only_the_ward():
    blow = blows.Blow(None, 'body', False, 5, 0, 0, pierce=Pierce(11, 4, 15, True), ward=2)

    save = blows.roll_blow_save(judging_with(SAVE_RULES, [13]), blow)

    assert save == Save('ward', 2, 13, 15, True)
    assert blows.is_saved(save) and not blows.is_saved(None)


def test_a_save_alone_makes_a_document():
    blow = blows.Blow(None, None, False, 0, 0, 0, ward=3)
    save = Save('ward', 3, 12, 15, True)

    document = blows.blow_document(SAVE_RULES, blow, save)

    assert document['save'] == {'kind': 'ward', 'value': 3, 'roll': 12, 'target': 15, 'saved': True}
    assert blows.blow_document(SAVE_RULES, blow) is None


def test_an_old_snapshot_has_no_pierce():
    rules = {**SRD5.model_dump(mode='json'), 'armor': {'mode': 'ac'}}
    document = {
        'format': 48,
        'rulebook': {'id': 'r', 'title': '룰북', 'gm_guide': '', 'rules': rules},
        'items': [{'entry_id': str(ME), 'kind': 'gear'}],
        'monsters': [{'id': str(ME)}],
    }
    no_armor = {**document, 'rulebook': {**document['rulebook'], 'rules': {**rules, 'armor': None}}}

    upgraded = upgrade_from_48(document)

    assert upgraded['format'] == 49
    assert upgraded['rulebook']['rules']['armor'] == {'mode': 'ac', 'save_target': None, 'pierce_base': 10}
    assert upgraded['items'] == [{'entry_id': str(ME), 'kind': 'gear', 'ap': None, 'ward': None}]
    assert upgraded['monsters'] == [{'id': str(ME), 'ward': None}]
    assert upgrade_from_48(no_armor)['rulebook']['rules']['armor'] is None
    assert UPGRADES[48] is upgrade_from_48


def test_the_pierce_and_the_save_are_in_the_line():
    note = BlowNote(weapon='볼터', weapon_bonus=1, location='몸', defense=5, mode='save', pierced=True)

    assert describe_blow(note) == '무기: 볼터 +1 · 맞은 곳: 몸 · 방어 5(세이브) · 관통함'
    saved = BlowNote(defense=0, mode='save', save_kind='ward', save_value=3, saved=True)
    assert describe_blow(saved) == '방어 0(세이브) · 불굴 세이브 3: 막음'


def test_the_pierce_and_the_save_are_in_the_record():
    blow = {
        'weapon': {'name': '볼터', 'bonus': 1},
        'location_name': '몸',
        'mode': 'save',
        'defense': 5,
        'pierce': {'pierced': False},
        'save': {'roll': 10, 'value': 5, 'saved': True},
    }
    payload = {'character_name': '엘프', 'ability': 'str', 'difficulty': 'medium', 'roll': 15, 'modifier': 1}
    payload |= {'total': 16, 'target': 15, 'success': True, 'blow': blow}

    line = render_event(TableEvent(type=EventType.CHECK_ROLLED, payload=payload), Labels())

    assert '(볼터 +1 · 몸 · 방어 5 · 관통 못 함 · 세이브 10 + 5 → 막음)' in line
