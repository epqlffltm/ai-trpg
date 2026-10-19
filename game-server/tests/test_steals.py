# game-server/tests/test_steals.py

"""
몬스터가 지닌 물건을 훔치는 행동(steal, #456, app/rounds/steals.py)을 검증한다.

맵은 수로 입구 하나다. 수로 쥐(야수)와 해골 병사(언데드)가 한 마리씩 있다. 둘 다 따로 정하지 않으면 공격이 없어
차례를 받지 않는다(앉은 순서대로 행동한다). 캐릭터와 몬스터의 능력치는 모두 10(보정 0)이다.
쥐는 송곳니 1개를 장비로, 늑대 가죽 2개와 왕관(에픽) 1개를 소지품으로 지녔다.

규칙은 SRD5 템플릿의 훔치기다. 민첩으로 보통(15)에서 시작한다. 대상의 지혜의 보정을 더하고,
장비 +5, 등급 한 단계마다 +2, 언데드와 구조물 -3, 둔하다고 적은 대상 -3, 싸움 전 -3, 다른 사람과 싸우는 중 -2.

보는 것.
  - 목표값: 걸리는 것마다 오르내리고 모두 더한다. 결과의 factors 에 걸린 것이 적힌다.
  - 성공: 그 줄을 통째로 갖고 마리에게서 빠진다. 상한을 넘은 것은 마리에게 남는다. 이벤트가 둘 남는다.
  - 실패(들킴): 마리와 싸운 것이 되고, 그 마리는 이번 라운드의 차례에 도둑을 친다.
  - 차례: 앞사람이 먼저 훔쳐 간 물건은 굴리지 않는다.
  - 받기: 그 마리가 지닌 물건만, 자기가 선 장소의 죽지 않은 마리만.
  - 판과 규칙: 훔치기 규칙과 둔함 표시를 적고 읽는다. 옛 판은 SRD5 의 훔치기로, 몬스터는 둔하지 않게 읽는다.
  - 서술: 한 일의 줄에 훔치기의 결과가 붙는다.
"""

import importlib.util
import pathlib
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.upgrades import upgrade_from_35
from app.engine.ruleset import Ruleset
from app.engine.templates import SRD5
from app.rounds.errors import ActionNotInRulesError
from app.rounds.models import Round
from app.rounds.move_lines import describe_move, describe_steal
from app.rounds.narrator import Move, StealNote
from app.rounds.steals import is_unwary, require_steal
from app.tables.models import NpcStatus
from tests.narration_model import asset_body
from tests.sheets import SHEET, make_sheet
from tests.signing import SigningKey, make_access_claims, make_token
from tests.test_monster_combat import (
    BESTIARIES_URL,
    LOREBOOKS_URL,
    RULEBOOKS_URL,
    SCENARIOS_URL,
    TABLES_URL,
    load_dice,
    table_url,
)
from tests.test_table_items import events_of, give, read_table
from tests.test_table_items import held as held_items
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
RAT_SHEET = make_sheet(max_hp=4)
BITE = {'name': '물기', 'ability': 'str', 'difficulty': 'medium', 'harm': 'light'}
STEAL = '몰래 손을 뻗는다.'
LOOK = '주위를 살핀다.'
MIGRATION = pathlib.Path(__file__).parent.parent / 'migrations/versions/20261019_8b4f2d6e9a71_steal.py'


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    return {'Authorization': f'Bearer {make_token(signing_key, make_access_claims(sub=str(user_id)))}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장. 캐릭터는 엘프다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """두 번째로 앉는 사람. 캐릭터는 드워프 기사다."""
    return bearer(signing_key, FRIEND)


async def post(client: AsyncClient, url: str, headers: dict[str, str], **body) -> dict:
    response = await client.post(url, json=asset_body(url, body), headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def make_world(client: AsyncClient, me: dict[str, str]) -> dict:
    """로어북(장소 하나, 물건 셋), 도감(쥐, 해골), 룰북."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='지하 수로')
    entries = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'
    bestiary = await post(client, BESTIARIES_URL, me, title='지하 수로의 것들')
    monsters = f'{BESTIARIES_URL}/{bestiary["id"]}/monsters'
    return {
        'lorebook': lorebook,
        'bestiary': bestiary,
        'gate': await post(client, entries, me, name='수로 입구', kind='place'),
        'tooth': await post(client, entries, me, name='송곳니', kind='item'),
        'pelt': await post(client, entries, me, name='늑대 가죽', kind='item'),
        'crown': await post(client, entries, me, name='왕관', kind='item'),
        'rat': await post(client, monsters, me, name='수로 쥐', kind='beast'),
        'skeleton': await post(client, monsters, me, name='해골 병사', kind='undead'),
        'rulebook': await post(client, RULEBOOKS_URL, me, title='룰북'),
    }


def carrying(world: dict, monster: str, sheet: dict = RAT_SHEET, attacks: list | None = None, dull: bool = False):
    """그 몬스터의 시트. 송곳니를 장비로, 늑대 가죽 2개와 왕관을 소지품으로 지닌다."""
    return {
        'monster_id': world[monster]['id'],
        'sheet': sheet,
        'attacks': attacks or [],
        'equipment': [{'entry_id': world['tooth']['id']}],
        'inventory': [{'entry_id': world['pelt']['id'], 'count': 2}, {'entry_id': world['crown']['id']}],
        'dull': dull,
    }


async def start(
    client: AsyncClient,
    me: dict,
    *others: dict,
    world: dict | None = None,
    rat: dict | None = None,
    skeleton: dict | None = None,
) -> dict:
    """
    쥐와 해골을 수로 입구에 둔 시나리오로 테이블을 시작한다. 모두 수로 입구에 선다.

    world 를 주면 그 로어북과 도감을 쓴다(rat, skeleton 이 그 몬스터를 가리킬 때). 아니면 새로 만든다.
    """
    world = world or await make_world(client, me)
    scenario = await post(
        client,
        SCENARIOS_URL,
        me,
        title='지하 수로',
        rulebook_id=world['rulebook']['id'],
        lorebook_ids=[world['lorebook']['id']],
        bestiary_ids=[world['bestiary']['id']],
        openings=['물 떨어지는 소리가 난다.'],
        default_sheet=SHEET,
        items=[{'entry_id': world['crown']['id'], 'rarity': 'epic'}],
        monster_sheets=[rat or carrying(world, 'rat'), skeleton or carrying(world, 'skeleton')],
        start_place=world['gate']['id'],
        encounters=[
            {'place_id': world['gate']['id'], 'monster_id': world['rat']['id'], 'count': 1},
            {'place_id': world['gate']['id'], 'monster_id': world['skeleton']['id'], 'count': 1},
        ],
    )
    published = await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)
    assert published.status_code == status.HTTP_201_CREATED, published.text
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1 + len(others))
    for headers, name in zip([me, *others], ['엘프', '드워프 기사'], strict=False):
        if headers is not me:
            await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=headers)
        await client.put(table_url(table, '/character'), json={'name': name}, headers=headers)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return {**world, 'table': table}


async def scene_monster(client: AsyncClient, headers: dict, world: dict, name: str) -> dict:
    response = await client.get(table_url(world['table'], '/rounds/current/people'), headers=headers)
    return next(monster for monster in response.json()['monsters'] if monster['name'] == name)


def steal(monster: dict, item: dict) -> dict:
    return {'kind': 'steal', 'monster': monster['id'], 'item': item['id']}


async def send(client: AsyncClient, headers: dict, world: dict, action: dict | None = None, content: str = STEAL):
    body = {'content': content} if action is None else {'content': content, 'action': action}
    return await client.put(table_url(world['table'], '/rounds/current/declaration'), json=body, headers=headers)


async def outcome(client: AsyncClient, me: dict, world: dict, number: int = 1, user_id: uuid.UUID = ME) -> dict:
    response = await client.get(table_url(world['table'], f'/rounds/{number}'), headers=me)
    declaration = next(item for item in response.json()['declarations'] if item['user_id'] == str(user_id))
    return declaration['outcome']


async def steal_now(client, app, me, world, monster: str, item: str, rolls: list[int], narrated) -> dict:
    """나 혼자 앉은 테이블에서 훔치고 라운드를 닫는다. 결과의 steal 을 돌려준다."""
    load_dice(app, rolls)
    target = await scene_monster(client, me, world, monster)
    response = await send(client, me, world, steal(target, world[item]))
    assert response.status_code == status.HTTP_200_OK, response.text
    await narrated()
    return (await outcome(client, me, world))['steal']


def carried(monster: dict) -> list[tuple[str, int]]:
    return [(item['name'], item['count']) for item in monster['items']]


# --- 목표값 ---


@pytest.mark.parametrize(
    ('item', 'target', 'factors'),
    [
        # 보통 15, 싸움 전 -3
        ('pelt', 12, ['unwary']),
        # 장비 +5
        ('tooth', 17, ['equipped', 'unwary']),
        # 에픽은 노말에서 세 단계, +6
        ('crown', 18, ['rarity', 'unwary']),
    ],
)
async def test_the_target_depends_on_the_item(
    client: AsyncClient, app: FastAPI, me: dict, narrated, item: str, target: int, factors: list[str]
):
    world = await start(client, me)

    stolen = await steal_now(client, app, me, world, '수로 쥐', item, [1], narrated)

    assert (stolen['check']['target'], stolen['factors']) == (target, factors)


@pytest.mark.parametrize(
    ('monster', 'sheet', 'dull', 'target', 'factors'),
    [
        # 지혜 16 은 보정 +3 이다. 적히지 않고 목표값에 섞인다
        ('rat', make_sheet(max_hp=4, wis=16), False, 15, ['unwary']),
        # 지혜 6 은 보정 -2. 둔하다고 적었으면 -3 더
        ('rat', make_sheet(max_hp=4, wis=6), True, 7, ['dull', 'unwary']),
        # 언데드 -3
        ('skeleton', RAT_SHEET, False, 9, ['dull_kind', 'unwary']),
        # 셋이 다 걸리면 모두 더한다
        ('skeleton', make_sheet(max_hp=4, wis=6), True, 4, ['dull', 'dull_kind', 'unwary']),
    ],
)
async def test_a_dull_target_is_easier(
    client: AsyncClient,
    app: FastAPI,
    me: dict,
    narrated,
    monster: str,
    sheet: dict,
    dull: bool,
    target: int,
    factors: list[str],
):
    world = await make_world(client, me)
    sheets = {monster: carrying(world, monster, sheet=sheet, dull=dull)}
    world = await start(client, me, world=world, **sheets)
    name = {'rat': '수로 쥐', 'skeleton': '해골 병사'}[monster]

    stolen = await steal_now(client, app, me, world, name, 'pelt', [1], narrated)

    assert (stolen['check']['target'], stolen['factors']) == (target, factors)


async def test_after_a_fight_the_monster_is_no_longer_unwary(client: AsyncClient, app: FastAPI, me: dict, narrated):
    world = await start(client, me)
    rat = await scene_monster(client, me, world, '수로 쥐')
    load_dice(app, [1])
    kick = {'kind': 'check', 'ability': 'str', 'harm': 'moderate', 'monster': rat['id']}
    await send(client, me, world, kick, content='쥐를 걷어찬다.')
    await narrated()

    load_dice(app, [1])
    await send(client, me, world, steal(rat, world['pelt']))
    await narrated()

    stolen = (await outcome(client, me, world, 2))['steal']
    assert (stolen['check']['target'], stolen['factors']) == (15, [])


async def test_a_monster_fighting_someone_else_is_distracted(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated
):
    world = await start(client, me, friend)
    rat = await scene_monster(client, me, world, '수로 쥐')
    # 엘프가 먼저 걷어차고(빗나감), 드워프 기사가 그 틈에 훔친다
    load_dice(app, [1, 1])
    kick = {'kind': 'check', 'ability': 'str', 'harm': 'moderate', 'monster': rat['id']}
    await send(client, me, world, kick, content='쥐를 걷어찬다.')
    await send(client, friend, world, steal(rat, world['pelt']))
    await narrated()

    stolen = (await outcome(client, me, world, 1, FRIEND))['steal']
    # 싸움은 이미 붙었다(싸움 전이 아니다). 다른 사람과 싸우는 중이라 -2
    assert (stolen['check']['target'], stolen['factors']) == (13, ['distracted'])


# --- 성공 ---


async def test_a_success_takes_the_whole_line(client: AsyncClient, app: FastAPI, me: dict, narrated):
    world = await start(client, me)
    rat = await scene_monster(client, me, world, '수로 쥐')

    stolen = await steal_now(client, app, me, world, '수로 쥐', 'pelt', [12], narrated)

    assert stolen == {
        'user_id': str(ME),
        'character_name': '엘프',
        'monster_id': rat['id'],
        'monster_name': '수로 쥐',
        'entry_id': world['pelt']['id'],
        'name': '늑대 가죽',
        'check': {'roll': 12, 'modifier': 0, 'total': 12, 'target': 12, 'success': True},
        'hindrance': None,
        'factors': ['unwary'],
        'stolen': True,
        'count': 2,
        'left': 0,
        'total': 2,
        'reason': None,
    }
    assert held_items(await read_table(client, me, world['table']), ME) == [('늑대 가죽', 2)]
    assert carried(await scene_monster(client, me, world, '수로 쥐')) == [('송곳니', 1), ('왕관', 1)]
    (attempted,) = await events_of(client, me, world['table'], 'steal_attempted')
    (acted,) = await events_of(client, me, world['table'], 'player_action')
    (gained,) = await events_of(client, me, world['table'], 'items_gained')
    assert (attempted['actor_id'], attempted['caused_by_sequence']) == (None, acted['sequence'])
    assert 'user_id' not in attempted['payload']
    assert attempted['payload']['check']['target'] == 12
    assert gained['caused_by_sequence'] == attempted['sequence']
    payload = gained['payload']
    assert (payload['source'], payload['monster_name'], payload['count'], payload['total']) == (
        'steal',
        '수로 쥐',
        2,
        2,
    )


async def test_what_does_not_fit_stays_with_the_monster(client: AsyncClient, app: FastAPI, me: dict, narrated):
    world = await start(client, me)
    given = await give(client, me, world['table'], ME, world['pelt'], 98)
    assert given.status_code == status.HTTP_200_OK, given.text

    stolen = await steal_now(client, app, me, world, '수로 쥐', 'pelt', [20], narrated)

    assert (stolen['count'], stolen['left'], stolen['total'], stolen['reason']) == (1, 1, 99, 'full')
    assert carried(await scene_monster(client, me, world, '수로 쥐')) == [('송곳니', 1), ('늑대 가죽', 1), ('왕관', 1)]


# --- 들킴 ---


async def test_a_caught_thief_takes_nothing(client: AsyncClient, app: FastAPI, me: dict, narrated):
    world = await start(client, me)

    stolen = await steal_now(client, app, me, world, '수로 쥐', 'pelt', [11], narrated)

    assert (stolen['stolen'], stolen['count'], stolen['left'], stolen['reason']) == (False, 0, 2, None)
    assert held_items(await read_table(client, me, world['table']), ME) == []
    (attempted,) = await events_of(client, me, world['table'], 'steal_attempted')
    assert attempted['payload']['stolen'] is False
    assert await events_of(client, me, world['table'], 'items_gained') == []


async def test_the_monster_goes_for_the_caught_thief(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated, session: AsyncSession
):
    world = await make_world(client, me)
    # 쥐는 민첩이 낮아 도둑 다음에 차례가 온다. 물기 하나를 가졌다. 엘프는 행동이 없어 차례가 없지만 칠 대상이다
    rat_sheet = carrying(world, 'rat', sheet=make_sheet(max_hp=4, dex=6), attacks=[BITE])
    world = await start(client, me, friend, world=world, rat=rat_sheet)
    rat = await scene_monster(client, me, world, '수로 쥐')
    # 드워프 기사가 훔치다 들킴(1), 쥐의 물기(1, 빗나감). 대상이 둘이지만 고르는 주사위는 굴리지 않는다
    dice = load_dice(app, [1, 1])
    await send(client, me, world, content=LOOK)
    await send(client, friend, world, steal(rat, world['pelt']))
    await narrated()

    query = select(Round).where(Round.table_id == uuid.UUID(world['table']['id']), Round.number == 1)
    round_ = await session.scalar(query.execution_options(populate_existing=True))
    bites = [turn for turn in round_.turns if turn['kind'] == 'monster']
    assert [turn['outcome']['character_name'] for turn in bites] == ['드워프 기사']
    assert dice.remaining == 0


# --- 차례 ---


async def test_the_one_after_finds_it_gone(client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated):
    world = await start(client, me, friend)
    rat = await scene_monster(client, me, world, '수로 쥐')
    dice = load_dice(app, [20])
    await send(client, me, world, steal(rat, world['pelt']))
    await send(client, friend, world, steal(rat, world['pelt']))
    await narrated()

    theirs = (await outcome(client, me, world, 1, FRIEND))['steal']
    assert (theirs['stolen'], theirs['check'], theirs['reason']) == (False, None, 'gone')
    assert dice.remaining == 0


# --- 받기 ---


async def test_only_what_the_monster_carries_can_be_stolen(client: AsyncClient, me: dict):
    world = await start(client, me)
    rat = await scene_monster(client, me, world, '수로 쥐')

    response = await send(client, me, world, {'kind': 'steal', 'monster': rat['id'], 'item': str(uuid.uuid4())})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert '지닌 물건이 아닙니다' in response.text


async def test_an_unknown_monster_cannot_be_robbed(client: AsyncClient, me: dict):
    world = await start(client, me)

    response = await send(
        client, me, world, {'kind': 'steal', 'monster': str(uuid.uuid4()), 'item': world['pelt']['id']}
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'action.monster' in response.text


def test_a_ruleset_without_stealing_refuses_it():
    rules = SRD5.model_copy(update={'steal': None})

    with pytest.raises(ActionNotInRulesError):
        require_steal(rules)


def test_a_downed_monster_is_unwary():
    fought = SimpleNamespace(state=SimpleNamespace(fought_round=2, status=NpcStatus.DOWNED))
    awake = SimpleNamespace(state=SimpleNamespace(fought_round=2, status=NpcStatus.ALIVE))

    assert (is_unwary(fought), is_unwary(awake)) == (True, False)


# --- 판과 규칙 ---


def test_the_steal_rule_must_point_at_known_keys():
    for fields in ({'ability': 'luck'}, {'awareness': 'luck'}, {'difficulty': 'impossible'}):
        rules = SRD5.model_dump(mode='json')
        rules['steal'] = {**rules['steal'], **fields}
        with pytest.raises(ValidationError):
            Ruleset.model_validate(rules)


def test_an_old_snapshot_reads_the_srd5_steal_and_no_dull_monsters():
    rules = {key: value for key, value in SRD5.model_dump(mode='json').items() if key != 'steal'}
    document = {'format': 35, 'rulebook': {'title': '룰북', 'rules': rules}, 'monsters': [{'id': 'm'}]}

    upgraded = upgrade_from_35(document)

    assert upgraded['format'] == 36
    assert upgraded['rulebook']['rules']['steal'] == SRD5.model_dump(mode='json')['steal']
    assert upgraded['monsters'] == [{'id': 'm', 'dull': False}]
    assert 'steal' not in document['rulebook']['rules']


def test_the_migration_fills_the_same_steal_as_the_template():
    spec = importlib.util.spec_from_file_location('steal_migration', MIGRATION)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert SRD5.model_dump(mode='json')['steal'] == migration.STEAL
    assert migration.with_steal({'die': 20}) == {'die': 20, 'steal': migration.STEAL}
    assert migration.with_steal({'steal': None}) == {'steal': None}
    assert migration.without_steal({'die': 20, 'steal': {}}) == {'die': 20}


async def test_a_dull_mark_is_published(client: AsyncClient, me: dict):
    world = await make_world(client, me)
    sheet = carrying(world, 'rat', dull=True)
    body = {'title': '수로', 'bestiary_ids': [world['bestiary']['id']], 'monster_sheets': [sheet]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert response.json()['monster_sheets'][0]['dull'] is True


# --- 서술 ---


@pytest.mark.parametrize(
    ('note', 'line'),
    [
        (
            StealNote(monster='수로 쥐', name='송곳니', count=1, stolen=True, caught=False),
            '(훔치기: 수로 쥐 에게서 송곳니 1개를 몰래 빼냈다)',
        ),
        (
            StealNote(monster='수로 쥐', name='송곳니', count=0, stolen=False, caught=True),
            '(훔치기: 수로 쥐 에게서 송곳니을(를) 훔치다 들켰다. 수로 쥐 이(가) 노린다)',
        ),
        (
            StealNote(monster='수로 쥐', name='송곳니', count=0, stolen=False, caught=False),
            '(훔치기: 수로 쥐 은(는) 송곳니을(를) 이미 지니지 않았다)',
        ),
    ],
)
def test_the_steal_line(note: StealNote, line: str):
    assert describe_steal(note) == line


async def test_the_narrator_is_told_about_the_steal(client: AsyncClient, app: FastAPI, me: dict, narrated):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    world = await start(client, me)

    await steal_now(client, app, me, world, '수로 쥐', 'pelt', [11], narrated)

    (request,) = narrator.requests
    (moved,) = request.moves
    assert moved.steal == StealNote(monster='수로 쥐', name='늑대 가죽', count=0, stolen=False, caught=True)


def test_the_move_line_carries_the_steal():
    note = StealNote(monster='수로 쥐', name='송곳니', count=1, stolen=True, caught=False)

    line = describe_move(Move(character_name='엘프', content=STEAL, steal=note))

    assert line == f'엘프: {STEAL} (훔치기: 수로 쥐 에게서 송곳니 1개를 몰래 빼냈다)'
