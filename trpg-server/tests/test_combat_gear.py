# trpg-server/tests/test_combat_gear.py

"""
장비가 공격과 방어에 드는 것(#276)을 검증한다. app/engine/armor.py, app/rounds/blows.py.

판: 룰북은 SRD5 템플릿이다(방어 방식 ac, 칸: 주손 1, 보조손 1, 몸 4, 머리 1 의 가중치, 노려 치기는 목표값 +5).
피해를 깎는 판(reduce)은 룰북의 방어 방식만 바꿔 게시한다.
  물건: 장검(손, 공격 +2), 판금 갑옷(몸, 방어 5), 방패(보조손, 모든 부위 +2), 투구(머리, 방어 3), 등불(규칙 없음),
        녹슨 칼(손, 공격 +1)
  캐릭터(엘프): 모든 능력치 10(보정 0), 최대 HP 10. 장검(주손)과 판금 갑옷(몸)을 착용하고, 투구와 방패를 들고 시작한다.
  몬스터(고블린, 최대 HP 30): 수로 입구에 한 마리. 시험마다 장비와 공격과 타고난 방어를 바꾼다.
주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다. 부위(1~7: 1 주손, 2 보조손, 3~6 몸, 7 머리) → 판정 → 피해의 차례다.

보는 것.
  - 무기: 착용한 무기를 선언하면 공격 보정이 판정의 보정에 든다. 착용하지 않았거나 무기가 아니면 받지 않는다.
  - 부위와 방어: 맞는 쪽이 부위에 방어가 있으면 부위를 굴린다. ac 는 목표값을 올리고 reduce 는 피해를 깎는다.
    방어가 없는 상대면 굴리지 않고, 장비가 들지 않은 타격의 결과는 그 전과 같다.
  - 노려 치기: 부위를 노리면 굴리지 않고 노려 치기의 대가를 치른다. 노릴 수 없는 부위는 받지 않는다.
  - 몬스터의 공격: 공격의 무기가 판정에 들고, 캐릭터의 착용이 막는다. 몬스터의 타고난 방어도 막는다.
  - 게시: NPC·몬스터의 장비 착용, 타고난 방어의 부위, 공격의 무기가 맞지 않으면 게시하지 않는다.
  - 기록과 서술: 판정의 이벤트와 기록, 서술의 줄에 무기, 맞은 부위, 방어가 붙는다(narration-52).
맨 아래에는 DB 를 쓰지 않는 작은 함수들의 테스트가 있다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.schemas import ItemRule, MonsterSheet, NpcSheet
from app.assets.scenarios.snapshot import AttackSnapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_47
from app.engine import armor, health
from app.engine.action import CheckAction
from app.engine.armor import Protection, Worn
from app.engine.dice import ScriptedDice
from app.engine.health import ChangeKind
from app.engine.ruleset import Armor, ArmorMode, Magnitude
from app.engine.templates import SRD5
from app.events.models import EventType, TableEvent
from app.main import API_PREFIX
from app.rounds import blows, npc_attacks
from app.rounds.models import Round
from app.rounds.move_lines import describe_blow
from app.rounds.narrator import BlowNote
from app.tables.carried import Carried
from app.tables.items import CatalogItem
from app.transcripts.labels import Labels
from app.transcripts.markdown import render_event
from tests.narration_model import asset_body
from tests.sheets import SHEET, make_sheet

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
BESTIARIES_URL = f'{API_PREFIX}/bestiaries'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
HANDS = ['main_hand', 'off_hand']
GOBLIN_SHEET = make_sheet(max_hp=30)

# 부위의 눈(가중치의 합 7). 판정의 눈. 보통의 목표는 15 다
MAIN_HAND, BODY, HEAD = 1, 4, 7
SLASH = '고블린을 벤다.'


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


async def make_parts(client: AsyncClient, me: dict, session: AsyncSession, mode: str = 'ac') -> dict:
    """로어북(입구와 물건 다섯), 도감(고블린), 룰북. 룰북의 방어 방식은 mode 다."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='수로')
    url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'

    async def entry(name: str, kind: str = 'item') -> dict:
        return await post(client, url, me, name=name, keywords=[], content=f'{name}의 설정', kind=kind)

    bestiary = await post(client, BESTIARIES_URL, me, title='수로의 것들')
    goblin = await post(client, f'{BESTIARIES_URL}/{bestiary["id"]}/monsters', me, name='고블린', kind='humanoid')
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북')
    if mode != 'ac':
        await session.execute(
            text(
                "UPDATE rulebooks SET rules = jsonb_set(rules, '{armor}', CAST(:armor AS JSONB)) WHERE asset_id = :id"
            ),
            {'armor': f'{{"mode": "{mode}"}}', 'id': uuid.UUID(rulebook['id'])},
        )
        await session.commit()
    return {
        'lorebook': lorebook,
        'bestiary': bestiary,
        'goblin': goblin,
        'rulebook': rulebook,
        'gate': await entry('수로 입구', 'place'),
        'sword': await entry('장검'),
        'plate': await entry('판금 갑옷'),
        'shield': await entry('방패'),
        'helm': await entry('투구'),
        'lamp': await entry('등불'),
        'blade': await entry('녹슨 칼'),
    }


def item_rules(parts: dict) -> list[dict]:
    return [
        {'entry_id': parts['sword']['id'], 'slots': HANDS, 'attack': 2},
        {'entry_id': parts['plate']['id'], 'slots': ['body'], 'defense': 5},
        {'entry_id': parts['shield']['id'], 'slots': ['off_hand'], 'guard': 2},
        {'entry_id': parts['helm']['id'], 'slots': ['head'], 'defense': 3},
        {'entry_id': parts['blade']['id'], 'slots': HANDS, 'attack': 1},
    ]


def starting(parts: dict) -> list[dict]:
    return [
        {'entry_id': parts['sword']['id'], 'count': 1, 'wear': ['main_hand']},
        {'entry_id': parts['plate']['id'], 'count': 1, 'wear': ['body']},
        {'entry_id': parts['shield']['id'], 'count': 1},
        {'entry_id': parts['helm']['id'], 'count': 1},
        {'entry_id': parts['lamp']['id'], 'count': 1},
    ]


def goblin_sheet(parts: dict, **fields) -> dict:
    """고블린의 시트. 공격이 없으면 차례가 없다(앉은 사람의 판정만 본다)."""
    return {'monster_id': parts['goblin']['id'], 'sheet': GOBLIN_SHEET, **fields}


def scenario_body(parts: dict, **fields) -> dict:
    body = {
        'title': '수로',
        'rulebook_id': parts['rulebook']['id'],
        'lorebook_ids': [parts['lorebook']['id']],
        'bestiary_ids': [parts['bestiary']['id']],
        'openings': ['물 떨어지는 소리가 난다.'],
        'default_sheet': SHEET,
        'items': item_rules(parts),
        'starting_items': starting(parts),
        'monster_sheets': [goblin_sheet(parts)],
        'start_place': parts['gate']['id'],
        'encounters': [{'place_id': parts['gate']['id'], 'monster_id': parts['goblin']['id'], 'count': 1}],
    }
    return {**body, **fields}


async def publish(client: AsyncClient, me: dict, parts: dict, **fields):
    scenario = await post(client, SCENARIOS_URL, me, **scenario_body(parts, **fields))
    return scenario, await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)


async def start(client: AsyncClient, me: dict, session: AsyncSession, mode: str = 'ac', **fields) -> tuple[dict, dict]:
    """판을 게시하고 테이블을 시작한다. 엘프 혼자 앉는다. (부품들, 테이블)을 돌려준다."""
    parts = await make_parts(client, me, session, mode)
    scenario, published = await publish(client, me, parts, **fields)
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


def slash(goblin: str, **fields) -> dict:
    """근력으로 보통(15)에 도전한다. 성공하면 고블린이 1d8 만큼 다친다."""
    return {'kind': 'check', 'ability': 'str', 'difficulty': 'medium', 'harm': 'moderate', 'monster': goblin, **fields}


async def send(client: AsyncClient, me: dict, table: dict, action: dict, content: str = SLASH):
    body = {'content': content, 'action': action}
    return await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=me)


async def outcome_of(client: AsyncClient, me: dict, table: dict, action: dict) -> dict:
    response = await send(client, me, table, action)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()['declarations'][0]['outcome']


async def turns_of(session: AsyncSession, table: dict) -> list[dict]:
    query = select(Round).where(Round.table_id == uuid.UUID(table['id']), Round.number == 1)
    return (await session.scalar(query.execution_options(populate_existing=True))).turns


async def events_of(client: AsyncClient, me: dict, table: dict, type_: str) -> list[dict]:
    response = await client.get(table_url(table, '/events'), params={'limit': 100}, headers=me)
    return [event for event in response.json()['items'] if event['type'] == type_]


# --- 앉은 사람의 타격 ---


async def test_a_worn_weapon_adds_its_bonus(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession):
    parts, table = await start(client, me, session)
    goblin = await goblin_id(client, me, table)
    # 방어가 없는 고블린이다. 부위를 굴리지 않는다. 판정 13 + 2 = 15, 피해 6
    dice = load_dice(app, [13, 6])

    outcome = await outcome_of(client, me, table, slash(goblin, weapon=parts['sword']['id']))

    assert (outcome['modifier'], outcome['total'], outcome['target'], outcome['success']) == (2, 15, 15, True)
    assert outcome['blow'] == {
        'weapon': {'entry_id': parts['sword']['id'], 'name': '장검', 'bonus': 2, 'ap': 0},
        'location': None,
        'location_name': None,
        'aimed': False,
        'defense': 0,
        'mode': 'ac',
        'pierce': None,
        'save': None,
    }
    assert outcome['monster_effect']['amount'] == 6
    assert dice.remaining == 0


async def test_a_plain_blow_is_as_before(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession):
    _, table = await start(client, me, session)
    goblin = await goblin_id(client, me, table)
    load_dice(app, [15, 6])

    outcome = await outcome_of(client, me, table, slash(goblin))

    assert outcome['blow'] is None
    assert (outcome['modifier'], outcome['target']) == (0, 15)


@pytest.mark.parametrize(
    ('location', 'name', 'defense', 'target'), [(BODY, '몸', 5, 20), (HEAD, '머리', 0, 15), (MAIN_HAND, '주손', 0, 15)]
)
async def test_armor_on_the_struck_part_raises_the_target(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, location, name, defense, target
):
    _, table = await start_with_goblin(client, me, session, equipment=plate_on_body)
    goblin = await goblin_id(client, me, table)
    load_dice(app, [location, 15, 6])

    outcome = await outcome_of(client, me, table, slash(goblin))

    assert outcome['target'] == target
    assert outcome['success'] is (target <= 15)
    assert (outcome['blow']['location_name'], outcome['blow']['defense']) == (name, defense)


def plate_on_body(parts: dict) -> list[dict]:
    """고블린의 장비: 몸에 판금 갑옷."""
    return [{'entry_id': parts['plate']['id'], 'wear': ['body']}]


async def start_with_goblin(
    client: AsyncClient, me: dict, session: AsyncSession, mode: str = 'ac', **sheet_fields
) -> tuple[dict, dict]:
    """고블린의 시트를 바꿔 시작한다. 값이 함수면 부품을 받아 그 칸을 만든다."""
    parts = await make_parts(client, me, session, mode)
    fields = {key: value(parts) if callable(value) else value for key, value in sheet_fields.items()}
    scenario, published = await publish(client, me, parts, monster_sheets=[goblin_sheet(parts, **fields)])
    assert published.status_code == status.HTTP_201_CREATED, published.text
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return parts, table


async def test_armor_cuts_the_damage_when_the_rule_reduces(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    _, table = await start_with_goblin(client, me, session, mode='reduce', equipment=plate_on_body)
    goblin = await goblin_id(client, me, table)
    # 몸에 맞았다. 목표는 그대로 15, 피해 7 에서 방어 5 를 빼 2
    load_dice(app, [BODY, 15, 7])

    outcome = await outcome_of(client, me, table, slash(goblin))

    assert outcome['target'] == 15
    assert (outcome['monster_effect']['rolls'], outcome['monster_effect']['amount']) == ([7], 2)
    assert (outcome['blow']['defense'], outcome['blow']['mode']) == (5, 'reduce')


async def test_armor_never_heals(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession):
    _, table = await start_with_goblin(client, me, session, mode='reduce', equipment=plate_on_body)
    goblin = await goblin_id(client, me, table)
    load_dice(app, [BODY, 15, 3])

    outcome = await outcome_of(client, me, table, slash(goblin))

    assert (outcome['monster_effect']['amount'], outcome['monster_effect']['status']) == (0, 'alive')


async def test_natural_armor_and_a_guard_add_up(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession):
    def equipment(parts):
        return [{'entry_id': parts['shield']['id'], 'wear': ['off_hand']}]

    _, table = await start_with_goblin(
        client, me, session, equipment=equipment, natural_armor=[{'slot': 'body', 'defense': 1}]
    )
    goblin = await goblin_id(client, me, table)
    # 몸: 가죽 1 + 방패 2. 목표 18
    load_dice(app, [BODY, 18, 6])

    outcome = await outcome_of(client, me, table, slash(goblin))

    assert (outcome['target'], outcome['blow']['defense']) == (18, 3)


async def test_a_struck_part_is_aimed_at_a_cost(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession):
    _, table = await start_with_goblin(client, me, session, equipment=plate_on_body)
    goblin = await goblin_id(client, me, table)
    # 머리를 노린다. 부위를 굴리지 않는다. 목표 15 + 노려 치기 5 + 머리의 방어 0
    dice = load_dice(app, [20, 6])

    outcome = await outcome_of(client, me, table, slash(goblin, strike='head'))

    assert outcome['target'] == 20
    assert (outcome['blow']['location'], outcome['blow']['aimed']) == ('head', True)
    assert dice.remaining == 0


@pytest.mark.parametrize(
    ('fields', 'code', 'text_'),
    [
        ({'strike': 'wings'}, 422, 'strike'),
        ({'weapon': 'lamp'}, 422, 'weapon'),
        ({'weapon': 'plate'}, 422, 'weapon'),
        ({'weapon': 'blade'}, 409, 'weapon_not_worn'),
        # 몬스터에게는 노려 칠 곳(aim)을 적지 않는다. 까닭은 action.check 칸에 온다
        ({'strike': 'head', 'aim': 'lost_eye'}, 422, 'aim'),
    ],
)
async def test_what_cannot_be_used_is_refused(
    client: AsyncClient, me: dict, session: AsyncSession, fields: dict, code: int, text_: str
):
    parts, table = await start(client, me, session)
    goblin = await goblin_id(client, me, table)
    action = slash(goblin, **{key: parts[value]['id'] if key == 'weapon' else value for key, value in fields.items()})

    response = await send(client, me, table, action)

    assert response.status_code == code
    assert text_ in response.text


# --- 몬스터의 공격 ---


async def test_a_monster_weapon_and_the_character_armor(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    def equipment(parts):
        return [{'entry_id': parts['blade']['id'], 'wear': ['main_hand']}]

    def attacks(parts):
        return [
            {'name': '베기', 'ability': 'str', 'difficulty': 'medium', 'harm': 'light', 'weapon': parts['blade']['id']}
        ]

    # 고블린이 먼저(민첩 14). 엘프의 몸에 맞았다: 목표 15 + 판금 5 = 20, 판정 19 + 1 = 20 → 맞음, 피해 3.
    # 엘프는 쉰다(판정 1)
    parts = await make_parts(client, me, session)
    sheet = goblin_sheet(parts, sheet=make_sheet(max_hp=30, dex=14), equipment=equipment(parts), attacks=attacks(parts))
    scenario, published = await publish(client, me, parts, monster_sheets=[sheet])
    assert published.status_code == status.HTTP_201_CREATED, published.text
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    await client.post(table_url(table, '/start'), headers=me)
    dice = load_dice(app, [BODY, 19, 3, 1])

    response = await send(client, me, table, {'kind': 'check', 'ability': 'dex', 'difficulty': 'medium'}, '숨는다.')

    assert response.status_code == status.HTTP_200_OK, response.text
    turn = (await turns_of(session, table))[0]['outcome']
    assert (turn['modifier'], turn['target'], turn['success']) == (1, 20, True)
    assert turn['blow']['weapon']['name'] == '녹슨 칼'
    assert (turn['blow']['location_name'], turn['blow']['defense']) == ('몸', 5)
    assert turn['effect']['after'] == 7
    assert dice.remaining == 0
    (attacked,) = await events_of(client, me, table, 'monster_attacked')
    assert attacked['payload']['blow']['location'] == 'body'


async def test_the_character_armor_cuts_a_monster_blow_when_the_rule_reduces(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    # 고블린이 먼저. 몸에 맞음(목표 15 그대로), 판정 15, 피해 4 에서 판금 5 를 빼 0. 엘프는 쉰다(판정 1)
    parts = await make_parts(client, me, session, mode='reduce')
    claw = [{'name': '할퀴기', 'ability': 'str', 'difficulty': 'medium', 'harm': 'light'}]
    sheet = goblin_sheet(parts, sheet=make_sheet(max_hp=30, dex=14), attacks=claw)
    scenario, published = await publish(client, me, parts, monster_sheets=[sheet])
    assert published.status_code == status.HTTP_201_CREATED, published.text
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    await client.post(table_url(table, '/start'), headers=me)
    load_dice(app, [BODY, 15, 4, 1])

    await send(client, me, table, {'kind': 'check', 'ability': 'dex', 'difficulty': 'medium'}, '숨는다.')

    turn = (await turns_of(session, table))[0]['outcome']
    assert (turn['target'], turn['success']) == (15, True)
    assert (turn['effect']['rolls'], turn['effect']['amount'], turn['effect']['after']) == ([4], 0, 10)


# --- 기록과 서술 ---


async def test_the_blow_is_recorded_and_narrated(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    parts, table = await start_with_goblin(client, me, session, equipment=plate_on_body)
    goblin = await goblin_id(client, me, table)
    load_dice(app, [BODY, 18, 6])

    await outcome_of(client, me, table, slash(goblin, weapon=parts['sword']['id']))
    await narrated()

    (rolled,) = await events_of(client, me, table, 'check_rolled')
    assert rolled['payload']['blow']['defense'] == 5
    scene = (await client.get(table_url(table, '/rounds/current'), headers=me)).json()['scene']
    assert '무기: 장검 +2 · 맞은 곳: 몸 · 방어 5(목표값에 더함)' in scene


# --- 게시 ---


@pytest.mark.parametrize(
    ('sheet', 'problem'),
    [
        (lambda parts: {'equipment': [{'entry_id': parts['plate']['id'], 'wear': ['head']}]}, 'carried_wear_invalid'),
        (lambda parts: {'equipment': [{'entry_id': parts['lamp']['id'], 'wear': ['body']}]}, 'carried_wear_invalid'),
        (lambda parts: {'natural_armor': [{'slot': 'tail', 'defense': 2}]}, 'natural_armor_invalid'),
        (
            lambda parts: {
                'equipment': [{'entry_id': parts['blade']['id']}],
                'attacks': [
                    {
                        'name': '베기',
                        'ability': 'str',
                        'difficulty': 'medium',
                        'harm': 'light',
                        'weapon': parts['blade']['id'],
                    }
                ],
            },
            'attack_weapon_invalid',
        ),
        (
            lambda parts: {
                'equipment': [{'entry_id': parts['plate']['id'], 'wear': ['body']}],
                'attacks': [
                    {
                        'name': '밀기',
                        'ability': 'str',
                        'difficulty': 'medium',
                        'harm': 'light',
                        'weapon': parts['plate']['id'],
                    }
                ],
            },
            'attack_weapon_invalid',
        ),
    ],
)
async def test_gear_that_does_not_fit_is_not_published(
    client: AsyncClient, me: dict, session: AsyncSession, sheet, problem: str
):
    parts = await make_parts(client, me, session)

    _, response = await publish(client, me, parts, monster_sheets=[goblin_sheet(parts, **sheet(parts))])

    assert response.status_code == status.HTTP_409_CONFLICT, response.text
    assert response.json()['problems'] == [problem]


async def test_the_gear_is_frozen_into_the_version(client: AsyncClient, me: dict, session: AsyncSession):
    parts = await make_parts(client, me, session)
    sheet = goblin_sheet(
        parts,
        equipment=[{'entry_id': parts['plate']['id'], 'wear': ['body']}],
        natural_armor=[{'slot': 'head', 'defense': 1}],
    )

    _, response = await publish(client, me, parts, monster_sheets=[sheet])

    snapshot = response.json()['snapshot']
    assert snapshot['rulebook']['rules']['armor'] == {'mode': 'ac', 'save_target': None, 'pierce_base': 10}
    (goblin,) = snapshot['monsters']
    assert goblin['equipment'][0]['wear'] == ['body']
    assert goblin['natural_armor'] == [{'slot': 'head', 'defense': 1}]
    assert (snapshot['items'][0]['attack'], snapshot['items'][1]['defense']) == (2, 5)


async def test_the_catalog_shows_the_numbers(client: AsyncClient, me: dict, session: AsyncSession):
    _, table = await start(client, me, session)

    detail = (await client.get(table_url(table), headers=me)).json()

    numbers = {item['name']: (item['attack'], item['defense'], item['guard']) for item in detail['items']}
    assert numbers['장검'] == (2, None, None)
    assert numbers['방패'] == (None, None, 2)
    assert detail['rules']['armor'] == {'mode': 'ac', 'save_target': None, 'pierce_base': 10}


# --- DB 를 쓰지 않는 것 ---


SWORD = uuid.UUID('aaaaaaaa-0000-4000-8000-000000000001')
PLATE = uuid.UUID('aaaaaaaa-0000-4000-8000-000000000002')
SHIELD = uuid.UUID('aaaaaaaa-0000-4000-8000-000000000003')
CATALOG = {
    SWORD: CatalogItem(SWORD, '장검', 'gear', None, slots=tuple(HANDS), attack=2),
    PLATE: CatalogItem(PLATE, '판금 갑옷', 'gear', None, slots=('body',), defense=5),
    SHIELD: CatalogItem(SHIELD, '방패', 'gear', None, slots=('off_hand',), guard=2),
}


@pytest.mark.parametrize(
    'body',
    [
        {'attack': 2},
        {'defense': 1, 'kind': 'consumable', 'heals': 'light'},
        {'slots': ['body'], 'defense': 11},
        {'slots': ['body'], 'guard': 0},
    ],
)
def test_wrong_numbers_are_refused(body: dict):
    with pytest.raises(ValidationError):
        ItemRule.model_validate({'entry_id': str(SWORD), **body})


@pytest.mark.parametrize(
    'body',
    [
        {'inventory': [{'entry_id': str(SWORD), 'wear': ['main_hand']}]},
        {
            'attacks': [
                {'name': '베기', 'ability': 'str', 'difficulty': 'medium', 'harm': 'light', 'weapon': str(SWORD)}
            ]
        },
        {'natural_armor': [{'slot': 'body', 'defense': 1}, {'slot': 'body', 'defense': 2}]},
    ],
)
def test_wrong_monster_gear_is_refused(body: dict):
    with pytest.raises(ValidationError):
        MonsterSheet.model_validate({'monster_id': str(SWORD), 'sheet': SHEET, **body})


def test_an_npc_wears_only_equipment():
    with pytest.raises(ValidationError):
        NpcSheet.model_validate(
            {'entry_id': str(SWORD), 'sheet': SHEET, 'inventory': [{'entry_id': str(PLATE), 'wear': ['body']}]}
        )


@pytest.mark.parametrize(
    'body',
    [
        {'weapon': str(SWORD)},
        {'strike': 'head'},
        {'harm': 'light', 'npc': str(SWORD), 'strike': 'head', 'aim': 'lost_eye'},
    ],
)
def test_a_weapon_and_a_struck_part_go_with_harm(body: dict):
    with pytest.raises(ValidationError):
        CheckAction.model_validate({'kind': 'check', 'ability': 'str', **body})


def test_protection_adds_the_parts_and_the_guard():
    worn = [Worn(('body',), defense=5), Worn(('off_hand',), guard=2), Worn(tuple(HANDS), defense=1)]

    protection = armor.protection_of(worn, {'body': 1, 'head': 2})

    assert protection == Protection(by_slot={'body': 6, 'head': 2, 'off_hand': 1, 'main_hand': 1}, guard=2)
    assert armor.defense_at(protection, 'body') == 8
    assert armor.defense_at(protection, 'tail') == 2
    assert armor.defense_at(protection, None) == 2


def test_only_part_armor_needs_a_location():
    assert armor.varies_by_slot(Protection(by_slot={'body': 1}))
    assert not armor.varies_by_slot(Protection(by_slot={'body': 0}, guard=3))


@pytest.mark.parametrize(('roll', 'slot'), [(1, 'main_hand'), (2, 'off_hand'), (3, 'body'), (6, 'body'), (7, 'head')])
def test_the_location_follows_the_weights(roll: int, slot: str):
    assert armor.roll_location(SRD5, ScriptedDice([roll])) == slot


def test_no_location_without_an_armor_rule_or_with_one_part():
    no_armor = SRD5.model_copy(update={'armor': None})
    one_part = SRD5.model_copy(update={'equipment_slots': (SRD5.equipment_slots[2],)})
    ringed = SRD5.model_copy(
        update={'equipment_slots': tuple(slot.model_copy(update={'hit_weight': 0}) for slot in SRD5.equipment_slots)}
    )

    assert armor.roll_location(no_armor, ScriptedDice([])) is None
    assert armor.roll_location(one_part, ScriptedDice([])) == 'body'
    assert armor.roll_location(ringed, ScriptedDice([])) is None
    assert not armor.can_strike(ringed, 'body')
    assert not armor.can_strike(SRD5.model_copy(update={'called_shot': None}), 'body')
    assert armor.can_strike(SRD5, 'head')


@pytest.mark.parametrize(('mode', 'raise_by', 'cut'), [(ArmorMode.AC, 4, 0), (ArmorMode.REDUCE, 0, 4), (None, 0, 0)])
def test_the_rule_decides_what_armor_does(mode, raise_by: int, cut: int):
    rules = SRD5.model_copy(update={'armor': Armor(mode=mode) if mode else None})

    assert (armor.target_raise(rules, 4), armor.damage_cut(rules, 4)) == (raise_by, cut)


def test_a_cut_takes_off_the_roll_but_not_below_zero():
    magnitude = Magnitude(key='moderate', name='보통', count=2, sides=6)

    cut = health.change_hp(ChangeKind.DAMAGE, magnitude, 10, 10, ScriptedDice([3, 4]), cut=5)
    over = health.change_hp(ChangeKind.DAMAGE, magnitude, 10, 10, ScriptedDice([1, 1]), cut=5)
    healed = health.change_hp(ChangeKind.RECOVERY, magnitude, 5, 10, ScriptedDice([1, 1]), cut=5)

    assert (cut.amount, cut.blocked, cut.after) == (2, 5, 8)
    assert (over.amount, over.blocked, over.after) == (0, 2, 10)
    assert (healed.amount, healed.blocked) == (2, 0)


def judging_with(ruleset=SRD5, rolls=()) -> SimpleNamespace:
    return SimpleNamespace(ruleset=ruleset, dice=ScriptedDice(list(rolls)), items=CATALOG, covers={})


def member_wearing(*worn: tuple[uuid.UUID, list[str]]) -> SimpleNamespace:
    rows = [SimpleNamespace(entry_id=entry_id, slots=slots) for entry_id, slots in worn]
    return SimpleNamespace(user_id=uuid.uuid4(), sheet=SimpleNamespace(worn=rows))


def test_a_member_is_protected_by_what_is_worn():
    member = member_wearing((PLATE, ['body']), (SHIELD, ['off_hand']))

    assert blows.member_protection(judging_with(), member) == Protection(by_slot={'body': 5, 'off_hand': 0}, guard=2)


def test_a_member_weapon_must_still_be_worn():
    member = member_wearing((SWORD, ['main_hand']))

    assert blows.member_weapon(judging_with(), member, SWORD) == blows.Weapon(SWORD, '장검', 2)
    assert blows.member_weapon(judging_with(), member_wearing(), SWORD) is None
    assert blows.member_weapon(judging_with(), member, PLATE) is None
    assert blows.member_weapon(judging_with(), member, None) is None


def test_carried_gear_counts_only_what_is_still_held_and_worn():
    held = [
        Carried(0, PLATE, 1, True, 100, ('body',)),
        Carried(1, SHIELD, 1, True, 100, ()),
        Carried(2, SWORD, 1, False, 100, ()),
    ]
    attack = SimpleNamespace(weapon=SWORD)

    assert blows.carried_protection(judging_with(), held, {'head': 1}) == Protection(by_slot={'head': 1, 'body': 5})
    assert blows.carried_weapon(judging_with(), held, attack) is None
    assert blows.carried_weapon(judging_with(), [Carried(0, SWORD, 1, True, 100, ('main_hand',))], attack).bonus == 2


def test_a_blow_without_gear_leaves_no_document():
    blow = blows.plan_blow(judging_with(), None, armor.NO_PROTECTION, None)

    assert blow == blows.NO_BLOW
    assert blows.blow_document(SRD5, blow) is None


def test_a_blow_rolls_the_part_only_when_armor_varies():
    judging = judging_with(rolls=[BODY])

    blow = blows.plan_blow(judging, None, Protection(by_slot={'body': 5}, guard=1), None)

    assert (blow.location, blow.defense, blow.raise_by, blow.cut) == ('body', 6, 6, 0)


def test_without_an_armor_rule_nothing_blocks():
    judging = judging_with(ruleset=SRD5.model_copy(update={'armor': None}))

    blow = blows.plan_blow(judging, None, Protection(by_slot={'body': 5}, guard=2), None)

    assert (blow.location, blow.defense, blow.raise_by, blow.cut) == (None, 0, 0, 0)


def test_an_npc_attack_uses_its_weapon_and_the_armor():
    attack = AttackSnapshot(name='베기', ability='str', difficulty='medium', harm='light')
    person = SimpleNamespace(npc=SimpleNamespace(injuries=[], abilities=SHEET['abilities']))
    blow = blows.Blow(weapon=blows.Weapon(SWORD, '장검', 2), location='body', aimed=False, defense=5, raise_by=5, cut=0)

    rolled = npc_attacks.roll_attack(judging_with(rolls=[18]), person, attack, blow)

    assert (rolled.check.modifier, rolled.check.total, rolled.check.target) == (2, 20, 20)


def test_an_old_snapshot_has_no_armor():
    rules = {**SRD5.model_dump(mode='json'), 'equipment_slots': [{'key': 'body', 'name': '몸'}]}
    del rules['armor']
    holder = {
        'equipment': [{'entry_id': str(SWORD), 'count': 1, 'chance': 100}],
        'inventory': [],
        'attacks': [{'name': '베기'}],
    }
    document = {
        'format': 47,
        'rulebook': {'id': 'r', 'title': '룰북', 'gm_guide': '', 'rules': rules},
        'items': [{'entry_id': str(SWORD), 'kind': 'gear'}],
        'npc_sheets': [{'entry_id': str(PLATE), **holder}],
        'monsters': [{'id': str(SHIELD), **holder}],
    }

    upgraded = upgrade_from_47(document)

    assert upgraded['format'] == 48
    assert upgraded['rulebook']['rules']['armor'] is None
    assert upgraded['rulebook']['rules']['equipment_slots'] == [{'key': 'body', 'name': '몸', 'hit_weight': 1}]
    assert upgraded['items'] == [
        {'entry_id': str(SWORD), 'kind': 'gear', 'attack': None, 'defense': None, 'guard': None}
    ]
    for holder_ in (upgraded['npc_sheets'][0], upgraded['monsters'][0]):
        assert holder_['equipment'][0]['wear'] == []
        assert holder_['attacks'][0]['weapon'] is None
    assert upgraded['monsters'][0]['natural_armor'] == []
    assert 'natural_armor' not in upgraded['npc_sheets'][0]
    assert UPGRADES[47] is upgrade_from_47


def test_the_blow_line():
    note = BlowNote(weapon='장검', weapon_bonus=2, location='머리', aimed=True, defense=0, mode='reduce')

    assert describe_blow(note) == '무기: 장검 +2 · 맞은 곳: 머리(노림) · 방어 0(피해에서 뺌)'
    assert describe_blow(BlowNote(weapon='장검', weapon_bonus=2)) == '무기: 장검 +2'


def test_the_blow_is_written_in_the_record():
    blow = {
        'weapon': {'name': '장검', 'bonus': 2},
        'location': 'body',
        'location_name': '몸',
        'aimed': False,
        'defense': 5,
        'mode': 'ac',
    }
    payload = {'character_name': '엘프', 'ability': 'str', 'difficulty': 'medium', 'roll': 18, 'modifier': 2}
    payload |= {'total': 20, 'target': 20, 'success': True, 'blow': blow}

    line = render_event(TableEvent(type=EventType.CHECK_ROLLED, payload=payload), Labels())

    assert '(장검 +2 · 몸 · 방어 5)' in line
