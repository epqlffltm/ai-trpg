# trpg-server/tests/test_covers.py

"""
커버 세이브(#276)를 검증한다. app/rounds/covers.py, app/engine/armor.py, app/rounds/blows.py.

판: 룰북은 SRD5 템플릿에서 방어 규칙만 세이브로 바꾼다(목표값 15, 관통의 기준값 10). 주사위는 d20 이다.
  맵: 수로 입구(시작, 커버는 시험마다), 배수로(길로 이어짐, 커버 없음).
  캐릭터(엘프): 모든 능력치 10, 최대 HP 10. 판금 갑옷(몸, 방어 5)을 착용하고 시작한다.
  몬스터(고블린, 최대 HP 30, 민첩 14): 수로 입구에 한 마리. 할퀴기(근력, 보통, 가벼운 피해)로 엘프를 친다.
  고블린이 먼저 친다. 엘프의 엄폐는 차례를 기다리지 않고 그 라운드의 처음부터 든다.
주사위의 차례: 부위(1~7, 3~6 이 몸) → 맞히기 → 세이브 → 피해.

보는 것.
  - 시나리오: 장소마다의 커버를 적고, 맵에 없는 장소면 게시하지 못한다(cover_off_map). 테이블의 맵에 커버가 보인다.
  - 받기: 세이브 방식에서, 커버가 있는 장소에 서 있을 때만 엄폐를 받는다(422 kind, 409 no_cover).
  - 세이브: 아머, 커버, 불굴 중 큰 값으로 한 번 굴린다. 관통하면 커버로도 막지 못한다.
  - 기록과 서술에 엄폐와 커버 세이브가 붙는다(narration-55).
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

from app.assets.scenarios.schemas import CoverRule, ScenarioCreate
from app.assets.scenarios.snapshot import CoverSnapshot, cover_at
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_50
from app.engine import armor
from app.engine.armor import Pierce, Protection, Save
from app.engine.dice import ScriptedDice
from app.engine.ruleset import Armor, ArmorMode
from app.engine.templates import SRD5
from app.main import API_PREFIX
from app.rounds import blows
from app.rounds.models import Round
from app.rounds.move_lines import describe_blow, describe_cover
from app.rounds.narrator import BlowNote, CoverNote
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
SAVE = {'mode': 'save', 'save_target': 15, 'pierce_base': 10}
BODY = 4
CLAW = [{'name': '할퀴기', 'ability': 'str', 'difficulty': 'medium', 'harm': 'light'}]
COVER = {'kind': 'cover'}


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
    """로어북(장소 둘과 판금 갑옷), 도감(고블린), 방어 규칙을 고른 룰북."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='수로')
    url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'

    async def entry(name: str, kind: str) -> dict:
        return await post(client, url, me, name=name, keywords=[], content=f'{name}의 설정', kind=kind)

    bestiary = await post(client, BESTIARIES_URL, me, title='수로의 것들')
    return {
        'lorebook': lorebook,
        'bestiary': bestiary,
        'goblin': await post(client, f'{BESTIARIES_URL}/{bestiary["id"]}/monsters', me, name='고블린', kind='humanoid'),
        'rulebook': await post(client, RULEBOOKS_URL, me, title='룰북', armor=armor_rule),
        'gate': await entry('수로 입구', 'place'),
        'drain': await entry('배수로', 'place'),
        'plate': await entry('판금 갑옷', 'item'),
    }


def scenario_body(parts: dict, covers: list[dict], goblin: bool = True) -> dict:
    """수로 입구에서 시작해 배수로로 이어지는 판. 엘프는 판금 갑옷을 입는다. 고블린은 수로 입구에 있다."""
    gate, drain = parts['gate']['id'], parts['drain']['id']
    monster = {'monster_id': parts['goblin']['id'], 'sheet': make_sheet(max_hp=30, dex=14), 'attacks': CLAW}
    body = {
        'title': '수로',
        'rulebook_id': parts['rulebook']['id'],
        'lorebook_ids': [parts['lorebook']['id']],
        'bestiary_ids': [parts['bestiary']['id']],
        'openings': ['물 떨어지는 소리가 난다.'],
        'default_sheet': SHEET,
        'items': [{'entry_id': parts['plate']['id'], 'slots': ['body'], 'defense': 5}],
        'starting_items': [{'entry_id': parts['plate']['id'], 'count': 1, 'wear': ['body']}],
        'start_place': gate,
        'routes': [{'from_place': gate, 'to_place': drain}],
        'covers': covers,
    }
    if goblin:
        body['monster_sheets'] = [monster]
        body['encounters'] = [{'place_id': gate, 'monster_id': parts['goblin']['id'], 'count': 1}]
    return body


async def start(
    client: AsyncClient, me: dict, cover: int | None = 7, armor_rule: dict | None = SAVE, goblin: bool = True
) -> tuple[dict, dict]:
    """판을 게시하고 테이블을 시작한다. 엘프 혼자 앉는다. 수로 입구의 커버는 cover 다(None 이면 없다)."""
    parts = await make_parts(client, me, armor_rule)
    covers = [] if cover is None else [{'place_id': parts['gate']['id'], 'cover': cover}]
    scenario = await post(client, SCENARIOS_URL, me, **scenario_body(parts, covers, goblin))
    published = await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)
    assert published.status_code == status.HTTP_201_CREATED, published.text
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return parts, table


async def declare(client: AsyncClient, me: dict, table: dict, action: dict):
    body = {'content': '무너진 담 뒤로 몸을 숨긴다.', 'action': action}
    return await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=me)


async def first_turn(session: AsyncSession, table: dict) -> dict:
    """1 라운드의 첫 차례(고블린)의 결과."""
    query = select(Round).where(Round.table_id == uuid.UUID(table['id']), Round.number == 1)
    return (await session.scalar(query.execution_options(populate_existing=True))).turns[0]['outcome']


# --- 시나리오와 테이블 ---


async def test_a_scenario_keeps_its_covers(client: AsyncClient, me: dict):
    parts = await make_parts(client, me, SAVE)
    covers = [{'place_id': parts['gate']['id'], 'cover': 4}]

    scenario = await post(client, SCENARIOS_URL, me, **scenario_body(parts, covers))
    changed = await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'covers': []}, headers=me)

    assert scenario['covers'] == covers
    assert changed.json()['covers'] == []


async def test_a_cover_off_the_map_cannot_be_published(client: AsyncClient, me: dict):
    parts = await make_parts(client, me, SAVE)
    elsewhere = await post(
        client,
        f'{LOREBOOKS_URL}/{parts["lorebook"]["id"]}/entries',
        me,
        name='탑',
        keywords=[],
        content='탑',
        kind='place',
    )
    body = scenario_body(parts, [{'place_id': elsewhere['id'], 'cover': 4}])
    scenario = await post(client, SCENARIOS_URL, me, **body)

    check = await client.get(f'{SCENARIOS_URL}/{scenario["id"]}/publish-check', headers=me)

    assert check.json()['problems'] == ['cover_off_map']


async def test_the_table_map_shows_the_cover(client: AsyncClient, me: dict):
    parts, table = await start(client, me, cover=7)

    places = (await client.get(table_url(table), headers=me)).json()['map']['places']

    covers = {place['name']: place['cover'] for place in places}
    assert covers == {'수로 입구': 7, '배수로': 0}


# --- 받기 ---


async def test_cover_is_refused_without_the_save_mode(client: AsyncClient, me: dict):
    _, table = await start(client, me, armor_rule={'mode': 'ac'}, goblin=False)

    response = await declare(client, me, table, COVER)

    assert response.status_code == 422
    assert 'action.kind' in response.json()['detail']


async def test_cover_is_refused_where_there_is_nothing_to_hide_behind(client: AsyncClient, me: dict):
    _, table = await start(client, me, cover=None, goblin=False)

    response = await declare(client, me, table, COVER)

    assert (response.status_code, response.json()['reason']) == (409, 'no_cover')


# --- 세이브 ---


async def test_cover_saves_even_against_an_earlier_attack(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    _, table = await start(client, me, cover=7)
    # 고블린이 먼저. 몸(판금 5)에 맞음, 맞히기 15, 세이브: 커버 7 이 아머 5 보다 크다. 10 + 7 = 17 → 막음
    dice = load_dice(app, [BODY, 15, 10])

    response = await declare(client, me, table, COVER)

    assert response.status_code == status.HTTP_200_OK, response.text
    (mine,) = response.json()['declarations']
    assert mine['outcome'] == {
        'cover': {'place': {'entry_id': mine['outcome']['cover']['place']['entry_id'], 'name': '수로 입구'}, 'value': 7}
    }
    turn = await first_turn(session, table)
    assert turn['blow']['save'] == {'kind': 'cover', 'value': 7, 'roll': 10, 'target': 15, 'saved': True}
    assert turn['effect'] is None
    assert dice.remaining == 0


async def test_armor_is_rolled_when_it_is_better_than_the_cover(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    _, table = await start(client, me, cover=3)
    load_dice(app, [BODY, 15, 10])

    await declare(client, me, table, COVER)

    turn = await first_turn(session, table)
    assert (turn['blow']['save']['kind'], turn['blow']['save']['value']) == ('armor', 5)


async def test_without_taking_cover_there_is_no_cover_save(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    _, table = await start(client, me, cover=9)
    # 엄폐하지 않고 숨는 판정(1)만 한다. 아머 5 로 굴린다: 10 + 5 = 15 → 막음
    load_dice(app, [BODY, 15, 10, 1])

    await declare(client, me, table, {'kind': 'check', 'ability': 'dex', 'difficulty': 'medium'})

    turn = await first_turn(session, table)
    assert (turn['blow']['save']['kind'], turn['blow']['save']['value']) == ('armor', 5)


# --- 기록과 서술 ---


async def test_the_cover_is_narrated(client: AsyncClient, app: FastAPI, me: dict, narrated):
    _, table = await start(client, me, cover=7)
    load_dice(app, [BODY, 15, 10])

    await declare(client, me, table, COVER)
    await narrated()

    scene = (await client.get(table_url(table, '/rounds/current'), headers=me)).json()['scene']
    assert '(엄폐: 수로 입구, 커버 7)' in scene
    assert '커버 세이브 7: 막음' in scene


# --- DB 를 쓰지 않는 것 ---


@pytest.mark.parametrize('cover', [0, 11])
def test_a_cover_is_one_to_ten(cover: int):
    with pytest.raises(ValidationError):
        CoverRule.model_validate({'place_id': str(ME), 'cover': cover})


def test_a_place_has_one_cover():
    cover = {'place_id': str(ME), 'cover': 3}
    with pytest.raises(ValidationError):
        ScenarioCreate.model_validate({'title': '수로', 'narration_model': 'm', 'covers': [cover, cover]})


SAVE_RULES = SRD5.model_copy(update={'armor': Armor(mode=ArmorMode.SAVE, save_target=15)})


@pytest.mark.parametrize(
    ('defense', 'cover', 'ward', 'expected'),
    [
        (0, 0, 0, None),
        (5, 7, 3, ('cover', 7)),
        (5, 5, 5, ('armor', 5)),
        (0, 4, 4, ('cover', 4)),
        (2, 3, 6, ('ward', 6)),
    ],
)
def test_the_best_of_three_saves_is_chosen(defense: int, cover: int, ward: int, expected):
    assert armor.save_terms(defense, ward, cover) == expected


def judging_with(ruleset, rolls) -> SimpleNamespace:
    return SimpleNamespace(ruleset=ruleset, dice=ScriptedDice(list(rolls)), items={})


def test_a_pierce_must_beat_the_cover_too():
    weapon = blows.Weapon(ME, '볼터', 1, ap=4)
    # 방어가 없는 곳이지만 커버 6 이 있다. 관통의 목표 6 + 10 = 16. 11 + 4 < 16 → 관통 못 함
    protection = Protection(by_slot={}, cover=6)

    blow = blows.plan_blow(judging_with(SAVE_RULES, [11]), weapon, protection, None)

    assert (blow.cover, blow.pierce) == (6, Pierce(roll=11, ap=4, target=16, pierced=False))


def test_after_a_pierce_the_cover_is_gone():
    blow = blows.Blow(None, 'body', False, 5, 0, 0, pierce=Pierce(12, 4, 16, True), ward=2, cover=6)

    save = blows.roll_blow_save(judging_with(SAVE_RULES, [13]), blow)

    assert save == Save('ward', 2, 13, 15, True)


def test_a_cover_alone_rolls_a_cover_save():
    blow = blows.Blow(None, None, False, 0, 0, 0, cover=4)

    save = blows.roll_blow_save(judging_with(SAVE_RULES, [11]), blow)

    assert save == Save('cover', 4, 11, 15, True)
    assert blows.blow_document(SAVE_RULES, blow, save)['save']['kind'] == 'cover'


def test_the_cover_of_a_place():
    snapshot = SimpleNamespace(covers=[CoverSnapshot(place_id=ME, cover=5)])

    assert (cover_at(snapshot, ME), cover_at(snapshot, uuid.uuid4()), cover_at(snapshot, None)) == (5, 0, 0)


def test_an_old_snapshot_has_no_covers():
    upgraded = upgrade_from_50({'format': 50, 'title': '수로'})

    assert upgraded == {'format': 51, 'title': '수로', 'covers': []}
    assert UPGRADES[50] is upgrade_from_50


def test_the_cover_lines():
    assert describe_cover(CoverNote(place='수로 입구', value=7)) == '(엄폐: 수로 입구, 커버 7)'
    assert describe_cover(CoverNote(place='배수로', value=0)) == '(엄폐: 숨을 곳이 없어 숨지 못했다)'
    saved = BlowNote(location='몸', defense=5, mode='save', save_kind='cover', save_value=7, saved=True)
    assert describe_blow(saved) == '맞은 곳: 몸 · 방어 5(세이브) · 커버 세이브 7: 막음'
