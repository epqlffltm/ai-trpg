# trpg-server/tests/test_monster_rules.py

"""
몬스터의 공격, 네임드 몹, 조우의 기습, 규칙의 차례 능력치(#231 3b)를 검증한다.

넷을 본다.
  - 자산과 시나리오: 도감 몬스터의 unique, 몬스터 시트의 attacks, 조우의 surprise 를 적고 읽고 고친다.
  - 게시: 공격의 이름표가 룰북에 있는지(monster_attack_invalid), 네임드 몹이 한 마리인지(unique_monster_repeated).
  - 판: 형식 23 에 실린다. 옛 판은 공격 없는 일반 몹, 기습 없음, 민첩(있으면)으로 읽는다.
  - 규칙과 테이블: initiative_ability 는 능력치 중 하나다. 테이블의 몬스터는 아직 아무도 만나지 않은 채로 시작한다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from pydantic import ValidationError
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.bestiaries.models import MonsterKind
from app.assets.models import MONSTER_MAX_ATTACKS
from app.assets.scenarios.snapshot import SNAPSHOT_FORMAT, MonsterSnapshot, Snapshot, read_snapshot
from app.assets.scenarios.upgrades import upgrade_from_22
from app.engine.ruleset import Ruleset
from app.engine.templates import SRD5
from app.main import API_PREFIX
from app.rounds.monster_scene import label_of
from app.tables.models import NpcStatus, TableMonster
from tests.narration_model import asset_body, with_model
from tests.sheets import SHEET, make_sheet

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
BESTIARIES_URL = f'{API_PREFIX}/bestiaries'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'

RAT_SHEET = make_sheet(dex=14, max_hp=4)
KING_SHEET = make_sheet(str=18, max_hp=30)
BITE = {
    'name': '물어뜯기',
    'ability': 'dex',
    'difficulty': 'medium',
    'harm': 'light',
    'weapon': None,
    'cost': None,
    'effects': [],
    'nature': None,
}
SLAM = {
    'name': '내려치기',
    'ability': 'str',
    'difficulty': 'hard',
    'harm': 'heavy',
    'weapon': None,
    'cost': None,
    'effects': [],
    'nature': None,
}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(ME)))
    return {'Authorization': f'Bearer {token}'}


async def post(client: AsyncClient, url: str, headers: dict[str, str], **body) -> dict:
    response = await client.post(url, json=asset_body(url, body), headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


@pytest.fixture
async def world(client: AsyncClient, me: dict[str, str]) -> dict:
    """장소 둘(늪 입구, 늪 한가운데), 일반 몹(늪 쥐)과 네임드 몹(늪의 왕)이 든 도감."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='늪')
    entries = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'
    bestiary = await post(client, BESTIARIES_URL, me, title='늪의 것들')
    monsters = f'{BESTIARIES_URL}/{bestiary["id"]}/monsters'
    return {
        'lorebook': lorebook,
        'bestiary': bestiary,
        'edge': await post(client, entries, me, name='늪 입구', kind='place'),
        'heart': await post(client, entries, me, name='늪 한가운데', kind='place'),
        'rat': await post(client, monsters, me, name='늪 쥐', kind='beast'),
        'king': await post(client, monsters, me, name='늪의 왕', kind='humanoid', unique=True),
    }


def sheet_for(monster: dict, sheet: dict, attacks: list | None = None) -> dict:
    return {'monster_id': monster['id'], 'sheet': sheet, 'attacks': attacks or []}


def encounter(place: dict, monster: dict, count: int, surprise: str = 'none') -> dict:
    return {'place_id': place['id'], 'monster_id': monster['id'], 'count': count, 'surprise': surprise}


async def create_scenario(client: AsyncClient, headers: dict[str, str], world: dict, **fields) -> dict:
    """맵(늪 입구에서 시작)과 쥐, 왕의 시트를 둔 시나리오."""
    rulebook = await post(client, RULEBOOKS_URL, headers, title='룰북')
    body = {
        'title': '늪',
        'rulebook_id': rulebook['id'],
        'openings': ['안개가 낀다.'],
        'default_sheet': SHEET,
        'lorebook_ids': [world['lorebook']['id']],
        'bestiary_ids': [world['bestiary']['id']],
        'monster_sheets': [sheet_for(world['rat'], RAT_SHEET, [BITE]), sheet_for(world['king'], KING_SHEET, [SLAM])],
        'start_place': world['edge']['id'],
        'routes': [{'from_place': world['edge']['id'], 'to_place': world['heart']['id']}],
    }
    body.update(fields)
    return await post(client, SCENARIOS_URL, headers, **body)


async def try_publish(client: AsyncClient, headers: dict[str, str], scenario: dict):
    return await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=headers)


async def refused(client: AsyncClient, headers: dict[str, str], scenario: dict) -> list[str]:
    response = await try_publish(client, headers, scenario)
    assert response.status_code == status.HTTP_409_CONFLICT, response.text
    return response.json()['problems']


async def published(client: AsyncClient, headers: dict[str, str], scenario: dict) -> dict:
    response = await try_publish(client, headers, scenario)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()['snapshot']


# --- 도감: 네임드 몹 ---


async def test_a_monster_is_ordinary_unless_marked_unique(client: AsyncClient, me: dict[str, str], world: dict):
    assert world['rat']['unique'] is False
    assert world['king']['unique'] is True


async def test_unique_can_be_changed(client: AsyncClient, me: dict[str, str], world: dict):
    url = f'{BESTIARIES_URL}/{world["bestiary"]["id"]}/monsters/{world["rat"]["id"]}'

    changed = await client.patch(url, json={'unique': True}, headers=me)
    kept = await client.patch(url, json={'unique': None, 'name': '큰 늪 쥐'}, headers=me)

    assert changed.json()['unique'] is True
    # null 은 "보내지 않았다"다
    assert kept.json()['unique'] is True


# --- 시나리오: 공격과 기습 ---


async def test_attacks_and_surprise_are_saved_and_read_back(client: AsyncClient, me: dict[str, str], world: dict):
    encounters = [encounter(world['edge'], world['rat'], 2, 'monsters')]
    scenario = await create_scenario(client, me, world, encounters=encounters)

    read = (await client.get(f'{SCENARIOS_URL}/{scenario["id"]}', headers=me)).json()

    assert read['monster_sheets'][0]['attacks'] == [BITE]
    assert read['encounters'] == encounters


@pytest.mark.parametrize(
    'attacks',
    [
        [{**BITE, 'harm': None}],
        [{key: value for key, value in BITE.items() if key != 'difficulty'}],
        [{**BITE, 'name': '   '}],
        [{**BITE, 'damage': 3}],
        # 같은 이름의 공격이 둘
        [BITE, {**SLAM, 'name': BITE['name']}],
        [{**BITE, 'name': f'공격{number}'} for number in range(MONSTER_MAX_ATTACKS + 1)],
    ],
)
async def test_rejects_bad_attacks(client: AsyncClient, me: dict[str, str], attacks: list):
    sheet = {'monster_id': NO_SUCH_ID, 'sheet': SHEET, 'attacks': attacks}

    response = await client.post(SCENARIOS_URL, json=with_model({'title': '늪', 'monster_sheets': [sheet]}), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_rejects_an_unknown_surprise(client: AsyncClient, me: dict[str, str]):
    bad = {'place_id': NO_SUCH_ID, 'monster_id': NO_SUCH_ID, 'count': 1, 'surprise': 'everyone'}

    response = await client.post(SCENARIOS_URL, json=with_model({'title': '늪', 'encounters': [bad]}), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 게시 ---


async def test_attacks_unique_and_surprise_are_frozen_into_the_version(
    client: AsyncClient, me: dict[str, str], world: dict
):
    encounters = [encounter(world['edge'], world['rat'], 2, 'monsters'), encounter(world['heart'], world['king'], 1)]
    scenario = await create_scenario(client, me, world, encounters=encounters)

    snapshot = await published(client, me, scenario)

    # 형식 23 에서 생긴 칸들이다. 형식은 그 뒤로도 올라간다
    assert snapshot['format'] == SNAPSHOT_FORMAT >= 23
    monsters = {monster['name']: monster for monster in snapshot['monsters']}
    assert (monsters['늪 쥐']['attacks'], monsters['늪 쥐']['unique']) == ([BITE], False)
    assert (monsters['늪의 왕']['attacks'], monsters['늪의 왕']['unique']) == ([SLAM], True)
    assert [line['surprise'] for line in snapshot['encounters']] == ['monsters', 'none']
    assert snapshot['rulebook']['rules']['initiative_ability'] == 'dex'


async def test_a_monster_without_attacks_is_allowed(client: AsyncClient, me: dict[str, str], world: dict):
    # 겁먹은 짐승처럼 공격하지 않는 몬스터
    scenario = await create_scenario(client, me, world, monster_sheets=[sheet_for(world['rat'], RAT_SHEET)])

    snapshot = await published(client, me, scenario)

    assert snapshot['monsters'][0]['attacks'] == []


@pytest.mark.parametrize(
    'attack',
    [{**BITE, 'ability': 'luck'}, {**BITE, 'difficulty': 'impossible'}, {**BITE, 'harm': 'apocalyptic'}],
)
async def test_an_attack_outside_the_rules_is_refused(
    client: AsyncClient, me: dict[str, str], world: dict, attack: dict
):
    scenario = await create_scenario(client, me, world, monster_sheets=[sheet_for(world['rat'], RAT_SHEET, [attack])])

    assert await refused(client, me, scenario) == ['monster_attack_invalid']


@pytest.mark.parametrize(
    'lines',
    [
        # 한 줄에 둘
        lambda world: [encounter(world['heart'], world['king'], 2)],
        # 두 줄에 하나씩
        lambda world: [encounter(world['edge'], world['king'], 1), encounter(world['heart'], world['king'], 1)],
    ],
)
async def test_a_unique_monster_is_only_one(client: AsyncClient, me: dict[str, str], world: dict, lines):
    scenario = await create_scenario(client, me, world, encounters=lines(world))

    assert await refused(client, me, scenario) == ['unique_monster_repeated']


async def test_an_ordinary_monster_may_be_many(client: AsyncClient, me: dict[str, str], world: dict):
    encounters = [encounter(world['edge'], world['rat'], 3), encounter(world['heart'], world['rat'], 2)]
    scenario = await create_scenario(client, me, world, encounters=encounters)

    snapshot = await published(client, me, scenario)

    assert [line['count'] for line in snapshot['encounters']] == [3, 2]


async def test_the_snapshot_refuses_a_repeated_unique_monster(client: AsyncClient, me: dict[str, str], world: dict):
    scenario = await create_scenario(client, me, world, encounters=[encounter(world['heart'], world['king'], 1)])
    document = await published(client, me, scenario)

    # 게시가 막는 것을 판의 계약도 막는다
    with pytest.raises(ValidationError):
        Snapshot.model_validate({**document, 'encounters': [{**document['encounters'][0], 'count': 2}]})


# --- 옛 판 ---


async def test_upgrades_a_format_22_document(client: AsyncClient, me: dict[str, str], world: dict):
    scenario = await create_scenario(client, me, world, encounters=[encounter(world['edge'], world['rat'], 1)])
    current = await published(client, me, scenario)
    rules = {key: value for key, value in current['rulebook']['rules'].items() if key != 'initiative_ability'}
    format_22 = {
        **current,
        'format': 22,
        'monsters': [
            {key: value for key, value in monster.items() if key not in ('attacks', 'unique')}
            for monster in current['monsters']
        ],
        'encounters': [
            {key: value for key, value in line.items() if key != 'surprise'} for line in current['encounters']
        ],
        'rulebook': {**current['rulebook'], 'rules': rules},
    }

    upgraded = upgrade_from_22(format_22)

    # 공격 없는 일반 몹, 기습 없음, 규칙에 민첩이 있으니 민첩이다
    assert upgraded['format'] == 23
    assert {(monster['unique'], len(monster['attacks'])) for monster in upgraded['monsters']} == {(False, 0)}
    assert [line['surprise'] for line in upgraded['encounters']] == ['none']
    assert upgraded['rulebook']['rules']['initiative_ability'] == 'dex'
    assert read_snapshot(format_22).rulebook.rules.initiative_ability == 'dex'


def test_old_rules_without_agility_get_no_initiative_ability():
    rules = {**SRD5.model_dump(mode='json'), 'abilities': [{'key': 'body', 'name': '몸'}]}
    rules.pop('initiative_ability')
    document = {'format': 22, 'monsters': [], 'encounters': [], 'rulebook': {'rules': rules}}

    assert upgrade_from_22(document)['rulebook']['rules']['initiative_ability'] is None


# --- 규칙 ---


def test_the_built_in_template_orders_turns_by_agility():
    assert SRD5.initiative_ability == 'dex'


def test_the_initiative_ability_must_be_one_of_the_abilities():
    with pytest.raises(ValidationError):
        Ruleset.model_validate({**SRD5.model_dump(mode='json'), 'initiative_ability': 'luck'})
    assert (
        Ruleset.model_validate({**SRD5.model_dump(mode='json'), 'initiative_ability': None}).initiative_ability is None
    )


# --- 테이블 ---


async def test_monsters_start_unengaged(client: AsyncClient, me: dict[str, str], world: dict, session: AsyncSession):
    scenario = await create_scenario(client, me, world, encounters=[encounter(world['heart'], world['rat'], 2)])
    await published(client, me, scenario)
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(f'{TABLES_URL}/{table["id"]}/character', json={'name': '엘프'}, headers=me)
    await client.post(f'{TABLES_URL}/{table["id"]}/start', headers=me)

    rows = await session.scalars(select(TableMonster).where(TableMonster.table_id == uuid.UUID(table['id'])))

    # 만난 첫 라운드는 라운드 닫기가 적는다(3c)
    assert {row.engaged_round for row in rows} == {None}


async def test_the_db_refuses_an_engaged_round_before_the_first(
    client: AsyncClient, me: dict[str, str], world: dict, session: AsyncSession
):
    scenario = await create_scenario(client, me, world, encounters=[encounter(world['heart'], world['rat'], 1)])
    await published(client, me, scenario)
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(f'{TABLES_URL}/{table["id"]}/character', json={'name': '엘프'}, headers=me)
    await client.post(f'{TABLES_URL}/{table["id"]}/start', headers=me)
    row = await session.scalar(select(TableMonster).where(TableMonster.table_id == uuid.UUID(table['id'])))
    row.engaged_round = 0

    with pytest.raises(IntegrityError):
        await session.commit()


def test_a_unique_monster_is_called_without_a_number():
    king = MonsterSnapshot(
        id=uuid.uuid4(), name='늪의 왕', content='', kind=MonsterKind.HUMANOID, sheet=KING_SHEET, unique=True
    )
    rat = MonsterSnapshot(id=uuid.uuid4(), name='늪 쥐', content='', kind=MonsterKind.BEAST, sheet=RAT_SHEET)
    counts = {king.id: 2, rat.id: 2}

    def state(monster: MonsterSnapshot) -> TableMonster:
        return TableMonster(monster_id=monster.id, number=2, hp=1, max_hp=1, status=NpcStatus.ALIVE)

    assert label_of(state(king), king, counts) == '늪의 왕'
    assert label_of(state(rat), rat, counts) == '늪 쥐 2'
