# trpg-server/tests/test_item_effects.py

"""
소모품의 효과 목록(#800)과, 물건을 인물이나 몬스터에게 쓰는 것(app/rounds/item_targets.py)을 검증한다.

맵은 수로 입구 하나다. 입구에 수로 쥐 하나(야수, 최대 HP 4)와 해골 병사 하나(언데드, 최대 HP 6, 독에 면역)가 있다.
악역영애(비올레타, 최대 HP 10)는 스타팅에 나오는 인물이다. 자리가 없어 어디서나 닿는다.
룰북은 SRD5 다. 물건을 인물이나 몬스터에게 쓸 때 민첩·보통(목표 15)으로 맞힌다(rules.item_check).
물건은 넷이다. 독 단검은 가벼운(1d4) 피해와 중독, 기절 가루는 기절, 치유 물약은 가벼운 회복, 연막탄은 효과가 없다.
모두 하나씩 가지고 시작한다. 주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다. 판정의 눈, 양의 눈 차례다.

보는 것.
  - 시나리오: 효과는 소모품에만. 회복과 피해를 함께, 같은 종류를 두 번, 모르는 종류는 받지 않는다(422).
    게시할 때 등급과 부상이 룰북에 있어야 한다(item_magnitude_missing, item_injure_invalid). 판 형식 62.
  - 자기와 동료: 굴리지 않는다. 피해와 부상은 자기에게만 쓴다(동료면 409 friendly_fire_off).
  - 인물과 몬스터: 늘 맞히는 판정을 굴린다. 맞히면 피해(방어는 치기와 같다)와 부상이 들고, 빗나가면 아무 일도 없다.
    굴렸으면 물건이 없어진다. 몬스터는 그 성질에 면역인 부상을 입지 않는다.
  - 받기: 규칙에 맞히는 판정이 없으면 422, 효과가 없는 물건에 대상을 적으면 422, 피해가 없는데 죽이려 하면 422.
  - 기록과 서술: item_used 뒤에 판정과 맞은 쪽의 변화, 입힌 부상이 잇는다. 판정 줄 앞에 쓴 물건이 붙는다.
  - 옛 판(형식 61)과 옛 시나리오 초안: heals, cures 가 효과가 되고, 룰북에는 맞히는 판정이 없다(판) / 템플릿의 것(DB).
"""

import json
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.schemas import ItemRule
from app.assets.scenarios.snapshot import SNAPSHOT_FORMAT, read_snapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_61
from app.engine.ruleset import Ruleset
from app.engine.templates import SRD5
from app.rounds.move_lines import describe_item_action, describe_move
from app.rounds.narrator import ItemActionNote, Move, Verdict
from tests import test_monster_combat as combat
from tests.sheets import SHEET, make_sheet
from tests.test_npc_sheets import published, refused
from tests.test_ruleset import load_migration

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = combat.ME
FRIEND = combat.FRIEND
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'
OPENING = '물 떨어지는 소리가 난다. 악역영애가 부채를 펼친다.'
PASS = combat.PASS
FAIL = combat.FAIL

me = combat.me
friend = combat.friend
post = combat.post
table_url = combat.table_url
load_dice = combat.load_dice
send = combat.send
declare = combat.declare
monster_named = combat.monster_named
events_of = combat.events_of

POISON = {'kind': 'injure', 'injury': 'poisoned'}
STUN = {'kind': 'injure', 'injury': 'stunned'}
LIGHT_DAMAGE = {'kind': 'damage', 'magnitude': 'light'}
LIGHT_HEAL = {'kind': 'heal', 'magnitude': 'light'}


def use(item: dict, **target) -> dict:
    """그 물건을 쓰는 행동. 대상은 target(앉은 사람), npc, monster 중 하나다."""
    return {'kind': 'use', 'item': item['id'], **target}


def the_items(world: dict) -> list[dict]:
    """독 단검(피해와 중독), 기절 가루(기절), 치유 물약(회복), 연막탄(효과 없음)."""
    return [
        {'entry_id': world['dagger']['id'], 'kind': 'consumable', 'effects': [LIGHT_DAMAGE, POISON]},
        {'entry_id': world['powder']['id'], 'kind': 'consumable', 'effects': [STUN]},
        {'entry_id': world['potion']['id'], 'kind': 'consumable', 'effects': [LIGHT_HEAL]},
        {'entry_id': world['smoke']['id'], 'kind': 'consumable'},
    ]


async def make_world(client: AsyncClient, me: dict) -> dict:
    """로어북(장소 하나, 인물 하나, 물건 넷)과 도감(쥐, 해골)과 룰북을 만든다."""
    lorebook = await post(client, combat.LOREBOOKS_URL, me, title='지하 수로')
    entries = f'{combat.LOREBOOKS_URL}/{lorebook["id"]}/entries'

    async def entry(name: str, kind: str, keywords: list[str] | None = None) -> dict:
        return await post(client, entries, me, name=name, kind=kind, keywords=keywords or [], content=f'{name}의 글')

    bestiary = await post(client, combat.BESTIARIES_URL, me, title='지하 수로의 것들')
    monsters = f'{combat.BESTIARIES_URL}/{bestiary["id"]}/monsters'
    return {
        'lorebook': lorebook,
        'bestiary': bestiary,
        'rulebook': await post(client, combat.RULEBOOKS_URL, me, title='룰북'),
        'gate': await entry('수로 입구', 'place'),
        'lady': await entry('비올레타', 'person', ['악역영애']),
        'dagger': await entry('독 단검', 'item'),
        'powder': await entry('기절 가루', 'item'),
        'potion': await entry('치유 물약', 'item'),
        'smoke': await entry('연막탄', 'item'),
        'rat': await post(client, monsters, me, name='수로 쥐', kind='beast', content='개만 한 쥐'),
        'skeleton': await post(client, monsters, me, name='해골 병사', kind='undead', content='녹슨 창'),
    }


async def make_scenario(client: AsyncClient, me: dict, world: dict, items: list[dict]) -> dict:
    """그 아이템 규칙을 적은 수로의 시나리오. 모두 물건 넷을 하나씩 가지고 시작한다."""
    starting = [{'entry_id': world[name]['id'], 'count': 1} for name in ('dagger', 'powder', 'potion', 'smoke')]
    return await post(
        client,
        combat.SCENARIOS_URL,
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
        encounters=[
            {'place_id': world['gate']['id'], 'monster_id': world['rat']['id'], 'count': 1},
            {'place_id': world['gate']['id'], 'monster_id': world['skeleton']['id'], 'count': 1},
        ],
        starting_items=starting,
        items=items,
    )


async def start_table(client: AsyncClient, me: dict, *others: dict, world: dict | None = None) -> dict:
    """수로의 시나리오로 테이블을 시작한다. 나(엘프)와 others(드워프 기사)가 앉는다."""
    world = world or await make_world(client, me)
    scenario = await make_scenario(client, me, world, the_items(world))
    await post(client, f'{combat.SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, combat.TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1 + len(others))
    for headers, name in zip([me, *others], ['엘프', '드워프 기사'], strict=False):
        if headers is not me:
            await client.post(f'{combat.TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=headers)
        await client.put(table_url(table, '/character'), json={'name': name}, headers=headers)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return {**world, 'table': started.json()}


async def read_table(client: AsyncClient, headers: dict, table: dict) -> dict:
    return (await client.get(table_url(table), headers=headers)).json()


def sheet_of(table: dict, user_id: uuid.UUID) -> dict:
    return next(member for member in table['members'] if member['user_id'] == str(user_id))['sheet']


def held(table: dict, user_id: uuid.UUID) -> dict[str, int]:
    return {item['name']: item['count'] for item in sheet_of(table, user_id)['items']}


def outcome_of(round_: dict, user_id: uuid.UUID = ME) -> dict:
    return next(d for d in round_['declarations'] if d['user_id'] == str(user_id))['outcome']


async def people(client: AsyncClient, headers: dict, table: dict) -> dict:
    response = await client.get(table_url(table, '/rounds/current/people'), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def injured_keys(used: dict) -> list[str | None]:
    return [one['injury'] for one in used['injured']]


# --- 시나리오 ---


def rule(**fields) -> dict:
    return {'entry_id': NO_SUCH_ID, 'kind': 'consumable', **fields}


@pytest.mark.parametrize(
    'fields',
    [
        {'kind': 'gear', 'effects': [LIGHT_HEAL]},
        {'effects': [LIGHT_HEAL, LIGHT_DAMAGE]},
        {'effects': [LIGHT_DAMAGE, LIGHT_DAMAGE]},
        {'effects': [POISON, POISON]},
        {'effects': [{'kind': 'charm', 'magnitude': 'light'}]},
        {'effects': [{'kind': 'heal'}]},
        {'effects': [POISON] * 3 + [STUN, LIGHT_DAMAGE, LIGHT_HEAL]},
        {'heals': 'light'},
    ],
    ids=['gear', 'heal-and-damage', 'damage-twice', 'same-injury', 'unknown-kind', 'no-magnitude', 'too-many', 'old'],
)
def test_rejects_misshaped_effects(fields: dict):
    with pytest.raises(ValidationError):
        ItemRule.model_validate(rule(**fields))


def test_injuries_of_different_kinds_fit_together():
    effects = [LIGHT_DAMAGE, POISON, STUN, {'kind': 'cure', 'injuries': ['blinded']}]

    parsed = ItemRule.model_validate(rule(effects=effects))

    assert [effect.model_dump(mode='json') for effect in parsed.effects] == effects


async def test_effects_are_frozen_into_the_version(client: AsyncClient, me: dict):
    world = await make_world(client, me)
    scenario = await make_scenario(client, me, world, the_items(world))

    document = await published(client, me, scenario)

    assert document['format'] == SNAPSHOT_FORMAT >= 62
    rules = read_snapshot(document).items
    assert [[effect.kind for effect in rule.effects] for rule in rules] == [
        ['damage', 'injure'],
        ['injure'],
        ['heal'],
        [],
    ]
    assert read_snapshot(document).rulebook.rules.item_check.model_dump() == {'ability': 'dex', 'difficulty': 'medium'}


@pytest.mark.parametrize(
    ('effect', 'problem'),
    [
        ({'kind': 'injure', 'injury': 'no_such_injury'}, 'item_injure_invalid'),
        ({'kind': 'damage', 'magnitude': 'enormous'}, 'item_magnitude_missing'),
        ({'kind': 'heal', 'magnitude': 'enormous'}, 'item_magnitude_missing'),
        ({'kind': 'cure', 'injuries': ['lost_eye']}, 'item_cure_invalid'),
    ],
)
async def test_effects_must_fit_the_rulebook(client: AsyncClient, me: dict, effect: dict, problem: str):
    world = await make_world(client, me)
    items = [{'entry_id': world['dagger']['id'], 'kind': 'consumable', 'effects': [effect]}]
    scenario = await make_scenario(client, me, world, items)

    assert problem in await refused(client, me, scenario)


async def test_the_table_lists_the_effects(client: AsyncClient, me: dict):
    world = await start_table(client, me)

    read = await read_table(client, me, world['table'])

    dagger = next(item for item in read['items'] if item['name'] == '독 단검')
    assert dagger['effects'] == [LIGHT_DAMAGE, POISON]


# --- 자기와 동료 ---


async def test_a_harmful_thing_used_on_oneself_needs_no_roll(client: AsyncClient, app: FastAPI, me: dict):
    world = await start_table(client, me)
    # 굴리지 않는다. 피해의 눈만 쓴다
    dice = load_dice(app, [3])

    closing = await declare(client, me, world['table'], '단검을 핥는다.', use(world['dagger']))

    outcome = outcome_of(closing)
    assert (outcome['effect']['kind'], outcome['effect']['amount']) == ('damage', 3)
    assert injured_keys(outcome['item_use']) == ['poisoned']
    assert 'roll' not in outcome
    assert dice.remaining == 0
    after = await read_table(client, me, world['table'])
    assert [one['injury'] for one in sheet_of(after, ME)['injuries']] == ['poisoned']
    assert sheet_of(after, ME)['hp'] == 7
    assert '독 단검' not in held(after, ME)
    (gained,) = await events_of(client, me, world['table'], 'injury_gained')
    assert (gained['payload']['source'], gained['payload']['user_id']) == ('item', str(ME))


async def test_a_harmful_thing_cannot_be_used_on_a_friend(client: AsyncClient, me: dict, friend: dict):
    world = await start_table(client, me, friend)

    response = await send(client, me, world['table'], '가루를 뿌린다.', use(world['powder'], target=str(FRIEND)))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'friendly_fire_off'


async def test_a_kind_thing_is_used_on_a_friend_without_a_roll(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated
):
    world = await start_table(client, me, friend)
    load_dice(app, [2])
    await declare(client, me, world['table'], '물약을 건넨다.', use(world['potion'], target=str(FRIEND)))

    closing = await declare(client, friend, world['table'], '마신다.')

    outcome = outcome_of(closing, ME)
    assert (outcome['effect']['user_id'], outcome['effect']['kind']) == (str(FRIEND), 'recovery')
    assert outcome['item_use']['target']['user_id'] == str(FRIEND)


# --- 인물과 몬스터 ---


async def test_a_poisoned_blade_hurts_and_poisons_a_monster(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐')
    # 1 은 HP 4 의 절반이 안 된다. 부상 표를 굴리지 않는다
    dice = load_dice(app, [PASS, 1])

    closing = await declare(client, me, world['table'], '쥐를 찌른다.', use(world['dagger'], monster=rat['id']))

    outcome = outcome_of(closing)
    assert (outcome['success'], outcome['target'], outcome['monster_effect']['amount']) == (True, 15, 1)
    used = outcome['item_use']
    assert (used['used'], used['ability'], used['difficulty']) == (True, 'dex', 'medium')
    assert used['target'] == {'monster_id': rat['id'], 'entry_id': None, 'name': '수로 쥐'}
    assert injured_keys(used) == ['poisoned']
    assert dice.remaining == 0
    assert (await monster_named(client, me, world['table'], '수로 쥐'))['injuries'] == ['poisoned']
    assert await combat.state_of(session, rat['id']) == (3, 'alive')
    assert '독 단검' not in held(await read_table(client, me, world['table']), ME)


async def test_an_undead_shrugs_off_the_poison(client: AsyncClient, app: FastAPI, me: dict):
    world = await start_table(client, me)
    skeleton = await monster_named(client, me, world['table'], '해골 병사')
    load_dice(app, [PASS, 1])

    closing = await declare(client, me, world['table'], '해골을 찌른다.', use(world['dagger'], monster=skeleton['id']))

    (injured,) = outcome_of(closing)['item_use']['injured']
    assert (injured['injury'], injured['immune']) == (None, 'poisoned')
    assert (await monster_named(client, me, world['table'], '해골 병사'))['injuries'] == []
    assert await events_of(client, me, world['table'], 'injury_gained') == []


async def test_a_miss_does_nothing_but_uses_the_thing_up(client: AsyncClient, app: FastAPI, me: dict):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐')
    load_dice(app, [FAIL])

    closing = await declare(client, me, world['table'], '가루를 뿌린다.', use(world['powder'], monster=rat['id']))

    outcome = outcome_of(closing)
    assert (outcome['success'], outcome['item_use']['used'], outcome['item_use']['injured']) == (False, True, [])
    assert (await monster_named(client, me, world['table'], '수로 쥐'))['injuries'] == []
    assert '기절 가루' not in held(await read_table(client, me, world['table']), ME)


async def test_a_kind_thing_on_a_person_is_rolled_too(client: AsyncClient, app: FastAPI, me: dict):
    world = await start_table(client, me)
    lady = (await people(client, me, world['table']))['people'][0]
    load_dice(app, [PASS, 2])

    closing = await declare(client, me, world['table'], '물약을 먹인다.', use(world['potion'], npc=lady['id']))

    outcome = outcome_of(closing)
    assert (outcome['success'], outcome['npc_effect']['kind'], outcome['npc_effect']['name']) == (
        True,
        'recovery',
        '악역영애',
    )
    assert outcome['item_use']['target'] == {'monster_id': None, 'entry_id': lady['id'], 'name': '악역영애'}


async def test_a_person_can_be_stunned(client: AsyncClient, app: FastAPI, me: dict):
    world = await start_table(client, me)
    lady = (await people(client, me, world['table']))['people'][0]
    load_dice(app, [PASS])

    closing = await declare(client, me, world['table'], '가루를 뿌린다.', use(world['powder'], npc=lady['id']))

    assert injured_keys(outcome_of(closing)['item_use']) == ['stunned']
    assert (await people(client, me, world['table']))['people'][0]['injuries'] == ['stunned']


async def test_a_monster_killed_meanwhile_is_not_used_on(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession
):
    world = await start_table(client, me, friend)
    rat = await monster_named(client, me, world['table'], '수로 쥐')
    await declare(client, me, world['table'], '쥐를 찌른다.', use(world['dagger'], monster=rat['id']))
    # 받은 뒤, 차례가 오기 전에 죽었다
    await session.execute(
        text("UPDATE table_monsters SET hp = 0, status = 'dead' WHERE id = :id"), {'id': uuid.UUID(rat['id'])}
    )
    await session.commit()
    dice = load_dice(app, [])

    closing = await declare(client, friend, world['table'], '지켜본다.')

    outcome = outcome_of(closing)
    assert (outcome['item_use']['used'], outcome['item_use']['reason']) == (False, 'target_gone')
    assert outcome['target_gone']['reason'] == 'dead'
    assert dice.remaining == 0
    assert held(await read_table(client, me, world['table']), ME)['독 단검'] == 1


# --- 받기 ---


@pytest.mark.parametrize(
    ('item', 'fields', 'detail'),
    [
        ('smoke', {'monster': 'rat'}, 'action.monster'),
        ('powder', {'monster': 'rat', 'lethal': True}, 'action.lethal'),
    ],
    ids=['no-effects', 'lethal-without-damage'],
)
async def test_what_cannot_be_used_on_others_is_refused(
    client: AsyncClient, me: dict, item: str, fields: dict, detail: str
):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐')
    target = {key: rat['id'] if value == 'rat' else value for key, value in fields.items()}

    response = await send(client, me, world['table'], '쓴다.', use(world[item], **target))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert detail in response.text


async def test_a_rulebook_without_the_check_uses_things_only_on_the_party(
    client: AsyncClient, me: dict, session: AsyncSession
):
    world = await make_world(client, me)
    await session.execute(
        text("UPDATE rulebooks SET rules = jsonb_set(rules, '{item_check}', 'null') WHERE asset_id = :id"),
        {'id': uuid.UUID(world['rulebook']['id'])},
    )
    await session.commit()
    world = await start_table(client, me, world=world)
    rat = await monster_named(client, me, world['table'], '수로 쥐')

    response = await send(client, me, world['table'], '찌른다.', use(world['dagger'], monster=rat['id']))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'action.monster' in response.text


def test_the_use_action_takes_one_target():
    from app.engine.action import UseAction

    with pytest.raises(ValidationError):
        UseAction.model_validate({'kind': 'use', 'item': NO_SUCH_ID, 'npc': NO_SUCH_ID, 'monster': NO_SUCH_ID})
    with pytest.raises(ValidationError):
        UseAction.model_validate({'kind': 'use', 'item': NO_SUCH_ID, 'lethal': True})


# --- 기록과 서술 ---


async def test_the_use_is_recorded_before_its_check_and_the_injury(client: AsyncClient, app: FastAPI, me: dict):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐')
    load_dice(app, [PASS, 1])
    await declare(client, me, world['table'], '쥐를 찌른다.', use(world['dagger'], monster=rat['id']))

    (used,) = await events_of(client, me, world['table'], 'item_used')
    (rolled,) = await events_of(client, me, world['table'], 'check_rolled')
    (changed,) = await events_of(client, me, world['table'], 'monster_changed')
    (gained,) = await events_of(client, me, world['table'], 'injury_gained')

    assert used['payload']['injured'] == [{'injury': 'poisoned', 'name': '중독'}]
    assert (rolled['payload']['ability'], rolled['caused_by_sequence']) == ('dex', used['sequence'])
    assert changed['caused_by_sequence'] == rolled['sequence']
    assert (gained['payload']['monster_id'], gained['payload']['source']) == (rat['id'], 'item')
    assert gained['caused_by_sequence'] == used['sequence']


def test_the_line_puts_the_thing_before_the_check():
    note = ItemActionNote(kind='use', name='독 단검', count=1, done=True, target='해골 병사', resisted=['중독'])
    verdict = Verdict(ability='민첩', difficulty='보통', roll=20, modifier=0, total=20, target=15, success=True)

    line = describe_move(Move(character_name='엘프', content='찌른다.', verdict=verdict, item_action=note))

    assert line.index('(쓴 물건: 독 단검 → 해골 병사)') < line.index('민첩')
    assert '[면역이라 입지 않은 부상: 중독]' in line


def test_the_line_names_what_was_inflicted():
    note = ItemActionNote(kind='use', name='기절 가루', count=1, done=True, injured=['기절'])

    assert describe_item_action(note) == '(쓴 물건: 기절 가루) [입힌 부상: 기절]'


# --- 옛 판과 옛 초안 ---


def test_an_old_version_reads_heals_and_cures_as_effects():
    old = {
        'format': 61,
        'rulebook': {'rules': {'die': 20}},
        'items': [
            {'entry_id': 'a', 'kind': 'consumable', 'heals': 'light', 'cures': ['poisoned']},
            {'entry_id': 'b', 'kind': 'gear', 'heals': None, 'cures': []},
        ],
    }

    upgraded = upgrade_from_61(old)

    assert upgraded['format'] == 62
    assert upgraded['items'] == [
        {
            'entry_id': 'a',
            'kind': 'consumable',
            'effects': [{'kind': 'heal', 'magnitude': 'light'}, {'kind': 'cure', 'injuries': ['poisoned']}],
        },
        {'entry_id': 'b', 'kind': 'gear', 'effects': []},
    ]
    assert upgraded['rulebook']['rules'] == {'die': 20, 'item_check': None}
    assert 'heals' in old['items'][0]
    assert UPGRADES[61] is upgrade_from_61


def test_the_migration_moves_drafts_and_fills_the_template_check():
    migration = load_migration('item_effects')
    old = {'entry_id': 'a', 'kind': 'consumable', 'heals': 'light', 'cures': ['poisoned']}

    moved = migration.with_effects(old)

    assert moved == {
        'entry_id': 'a',
        'kind': 'consumable',
        'effects': [{'kind': 'heal', 'magnitude': 'light'}, {'kind': 'cure', 'injuries': ['poisoned']}],
    }
    assert migration.with_effects(moved) == moved
    poisoned = {**moved, 'effects': [*moved['effects'], LIGHT_DAMAGE, POISON]}
    assert migration.without_effects(poisoned) == old
    assert migration.with_item_check({'template': 'srd5'})['item_check'] == {'ability': 'dex', 'difficulty': 'medium'}
    assert migration.with_item_check({'template': 'homebrew'})['item_check'] is None
    assert migration.without_item_check({'item_check': None, 'die': 20}) == {'die': 20}


async def test_the_migration_rewrites_the_drafts_and_rulebooks_in_the_database(
    client: AsyncClient, me: dict, session: AsyncSession
):
    migration = load_migration('item_effects')
    world = await make_world(client, me)
    scenario = await make_scenario(client, me, world, the_items(world))
    old_items = [{'entry_id': world['potion']['id'], 'kind': 'consumable', 'heals': 'light', 'cures': ['poisoned']}]
    await session.execute(
        text('UPDATE scenarios SET items = CAST(:items AS JSONB) WHERE asset_id = :id'),
        {'items': json.dumps(old_items), 'id': uuid.UUID(scenario['id'])},
    )
    await session.execute(text("UPDATE rulebooks SET rules = rules - 'item_check'"))
    await session.commit()

    async def run(step, rewrite) -> None:
        await session.run_sync(lambda sync: rewrite(sync.connection(), step))
        await session.commit()

    # 두 번 돌려도 같다
    for _ in range(2):
        await run(migration.with_effects, migration.rewrite_items)
        await run(migration.with_item_check, migration.rewrite_rulebooks)
    items = await session.scalar(
        text('SELECT items FROM scenarios WHERE asset_id = :id'), {'id': uuid.UUID(scenario['id'])}
    )
    check = await session.scalar(text("SELECT rules -> 'item_check' FROM rulebooks"))
    assert items == [{**migration.with_effects(old_items[0])}]
    assert check == {'ability': 'dex', 'difficulty': 'medium'}
    # 되돌리면 옛 모양이다
    await run(migration.without_effects, migration.rewrite_items)
    back = await session.scalar(
        text('SELECT items FROM scenarios WHERE asset_id = :id'), {'id': uuid.UUID(scenario['id'])}
    )
    assert back == old_items


@pytest.mark.parametrize('template', ['srd5', 'horror', 'light'])
def test_the_migration_knows_the_template_s_check(template: str):
    # 마이그레이션은 앱의 코드를 가져오지 않는다. 템플릿을 고치면 이 테스트가 깨진다
    from app.engine.templates import Template, from_template

    migration = load_migration('item_effects')

    assert migration.ITEM_CHECKS[template] == from_template(Template(template)).item_check.model_dump()


def test_the_check_must_be_one_of_the_rulebook():
    document = SRD5.model_dump(mode='json')

    with pytest.raises(ValidationError):
        Ruleset.model_validate({**document, 'item_check': {'ability': 'luck', 'difficulty': 'medium'}})
    with pytest.raises(ValidationError):
        Ruleset.model_validate({**document, 'item_check': {'ability': 'dex', 'difficulty': 'insane'}})
