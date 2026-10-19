# game-server/tests/test_quest_goals.py

"""
퀘스트의 조건을 엔진이 보고 성공으로 바꾸는 것(#367, app/rounds/quest_goals.py)을 검증한다.

맵은 성문(시작)과 숲이다. 성문에 들쥐 둘(최대 HP 4), 성문에 악역영애(인물, 최대 HP 4)가 장면에 나온다.
물건은 치유 물약과 늑대 가죽이다. 퀘스트는 시험마다 조건을 달리 적는다.
주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다. 판정의 눈, 피해의 양의 눈 차례다.

보는 것.
  - 시나리오: 조건을 적고 판에 굳힌다. count 는 세는 조건에만, 같은 조건 두 줄과 6 줄은 거부.
    게시할 때 가리키는 것이 있는지, 맞는 종류인지, 이룰 수 있는지 본다. 옛 판은 조건이 없는 것으로 읽는다.
  - 라운드: 장소에 닿기, 몬스터를 쓰러뜨리기(여러 라운드에 걸쳐 센다), 물건 갖기, 인물 쓰러뜨리기.
    모두(all)와 하나라도(any). 숨긴 퀘스트는 드러나며 바로 성공. 조건이 없으면 성공하지 않는다.
  - 보상: 살아 있는 캐릭터마다, 죽은 캐릭터는 빼고, 상한에 닿으면 거기까지.
  - 이벤트: quest_changed 에 까닭(conditions_met), 행한 사람 없음, 라운드가 닫힌 이벤트보다 앞이고 같은 묶음.
맨 아래에는 DB 를 쓰지 않는 작은 함수들의 테스트가 있다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import QUEST_MAX_CONDITIONS, QuestConditionKind, QuestMatch
from app.assets.scenarios.snapshot import QuestConditionSnapshot, read_snapshot
from app.assets.scenarios.upgrades import upgrade_from_29
from app.engine.dice import ScriptedDice
from app.main import API_PREFIX
from app.rounds import prompt
from app.rounds.quest_goals import defeated_monsters, held, is_achieved, npc_defeated, reached
from app.tables.models import NpcStatus
from app.tables.quests import CatalogQuest
from tests.narration_model import asset_body
from tests.sheets import SHEET, make_sheet
from tests.test_table_items import FRIEND, ME, bearer, events_of, kill, read_table, table_url
from tests.test_table_items import held as held_items

pytestmark = pytest.mark.usefixtures('clean_tables')

API = API_PREFIX
LOREBOOKS_URL = f'{API}/lorebooks'
BESTIARIES_URL = f'{API}/bestiaries'
RULEBOOKS_URL = f'{API}/rulebooks'
SCENARIOS_URL = f'{API}/scenarios'
TABLES_URL = f'{API}/tables'
SMALL = make_sheet(max_hp=4)
PASS = 20
# 최대 HP 4 를 넘기는 피해의 눈(보통 1d8)
DOWN = 8
OPENING = '성문 앞에 악역영애가 서 있다.'
LOOK = '주위를 살핀다.'


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key) -> dict[str, str]:
    return bearer(signing_key, FRIEND)


async def post(client: AsyncClient, url: str, headers: dict[str, str], **body) -> dict:
    response = await client.post(url, json=asset_body(url, body), headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def load_dice(app: FastAPI, rolls: list[int]) -> ScriptedDice:
    dice = ScriptedDice(rolls)
    app.state.dice = dice
    return dice


def goal(kind: str, target: dict, count: int = 1) -> dict:
    return {'kind': kind, 'target': target['id'], 'count': count}


def quest(world: dict, *conditions: dict, start: str = 'active', match: str = 'all', reward: list | None = None):
    """첫 사건(구출)의 퀘스트 규칙."""
    rule = {'entry_id': world['rescue']['id'], 'start': start, 'conditions': list(conditions), 'match': match}
    return {**rule, 'reward': reward or []}


async def make_world(client: AsyncClient, me: dict[str, str]) -> dict:
    """로어북(장소 둘, 물건 둘, 인물 하나, 사건 둘), 도감(들쥐), 룰북. 시나리오는 아직 없다."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='성문')
    entries = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'
    bestiary = await post(client, BESTIARIES_URL, me, title='들의 것들')
    monsters = f'{BESTIARIES_URL}/{bestiary["id"]}/monsters'

    async def entry(name: str, kind: str) -> dict:
        return await post(client, entries, me, name=name, keywords=[], content=f'{name}의 설명', kind=kind)

    return {
        'lorebook': lorebook,
        'bestiary': bestiary,
        'gate': await entry('성문', 'place'),
        'forest': await entry('숲', 'place'),
        'island': await entry('외딴섬', 'place'),
        'potion': await entry('치유 물약', 'item'),
        'pelt': await entry('늑대 가죽', 'item'),
        'lady': await entry('악역영애', 'person'),
        'rescue': await entry('왕녀 구출', 'event'),
        'secret': await entry('숨은 비밀', 'event'),
        'rat': await post(client, monsters, me, name='들쥐', kind='beast', content='큰 쥐'),
        'rulebook': await post(client, RULEBOOKS_URL, me, title='룰북'),
    }


async def make_scenario(client: AsyncClient, me: dict[str, str], world: dict, quests: list[dict], **fields) -> dict:
    body = {
        'title': '성문',
        'rulebook_id': world['rulebook']['id'],
        'lorebook_ids': [world['lorebook']['id']],
        'bestiary_ids': [world['bestiary']['id']],
        'openings': [OPENING],
        'default_sheet': SHEET,
        'default_npc_sheet': SHEET,
        'npc_sheets': [{'entry_id': world['lady']['id'], 'sheet': SMALL}],
        'monster_sheets': [{'monster_id': world['rat']['id'], 'sheet': SMALL}],
        'start_place': world['gate']['id'],
        'routes': [{'from_place': world['gate']['id'], 'to_place': world['forest']['id']}],
        'encounters': [{'place_id': world['gate']['id'], 'monster_id': world['rat']['id'], 'count': 2}],
        'quests': quests,
        **fields,
    }
    return await post(client, SCENARIOS_URL, me, **body)


async def publish(client: AsyncClient, me: dict[str, str], scenario: dict):
    return await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)


async def start(client: AsyncClient, me: dict[str, str], world: dict, quests: list[dict], *others, **fields) -> dict:
    """그 퀘스트들로 테이블을 시작한다. 나(기사)와 others(약사)가 성문에 선다."""
    scenario = await make_scenario(client, me, world, quests, **fields)
    published = await publish(client, me, scenario)
    assert published.status_code == status.HTTP_201_CREATED, published.text
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1 + len(others))
    for headers, name in zip([me, *others], ['기사', '약사'], strict=False):
        if headers is not me:
            await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=headers)
        await client.put(table_url(table, '/character'), json={'name': name}, headers=headers)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


async def declare(client: AsyncClient, headers: dict, table: dict, content: str = LOOK, action: dict | None = None):
    body = {'content': content} if action is None else {'content': content, 'action': action}
    response = await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def move(place: dict) -> dict:
    return {'kind': 'move', 'place': place['id']}


def strike(**target) -> dict:
    """근력으로 보통에 도전해 죽이려고 친다. target 은 monster= 또는 npc= 다."""
    return {'kind': 'check', 'ability': 'str', 'difficulty': 'medium', 'harm': 'moderate', 'lethal': True, **target}


async def rat_ids(client: AsyncClient, me: dict, table: dict) -> list[str]:
    response = await client.get(table_url(table, '/rounds/current/people'), headers=me)
    return [monster['id'] for monster in response.json()['monsters']]


def status_of(table: dict, name: str) -> str:
    return next(quest['status'] for quest in table['quests'] if quest['name'] == name)


# --- 시나리오 ---


async def test_conditions_are_saved_and_published(client: AsyncClient, me: dict[str, str]):
    world = await make_world(client, me)
    rule = quest(world, goal('reach_place', world['forest']), goal('defeat_monster', world['rat'], 2), match='any')
    scenario = await make_scenario(client, me, world, [rule])

    response = await publish(client, me, scenario)

    # 가져가는지(consume)를 적지 않았으면 가져가지 않는다
    assert scenario['quests'][0]['conditions'] == [{**one, 'consume': False} for one in rule['conditions']]
    snapshot = read_snapshot(response.json()['snapshot'])
    (published,) = snapshot.quests
    assert published.match == QuestMatch.ANY
    assert [(item.kind, str(item.target), item.count) for item in published.conditions] == [
        (QuestConditionKind.REACH_PLACE, world['forest']['id'], 1),
        (QuestConditionKind.DEFEAT_MONSTER, world['rat']['id'], 2),
    ]


@pytest.mark.parametrize('kind', ['reach_place', 'defeat_npc'])
async def test_count_is_only_for_counted_conditions(client: AsyncClient, me: dict[str, str], kind: str):
    world = await make_world(client, me)
    target = world['forest'] if kind == 'reach_place' else world['lady']
    body = {'title': '성문', 'quests': [quest(world, goal(kind, target, 2))]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_same_condition_twice_and_too_many_are_refused(client: AsyncClient, me: dict[str, str]):
    world = await make_world(client, me)
    twice = quest(world, goal('hold_item', world['potion']), goal('hold_item', world['potion'], 3))
    many = quest(world, *[goal('reach_place', world['forest'])] * (QUEST_MAX_CONDITIONS + 1))

    for rule in (twice, many):
        body = {'title': '성문', 'quests': [rule]}
        response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    ('kind', 'target', 'count', 'problem'),
    [
        ('reach_place', 'gone', 1, 'quest_condition_missing'),
        ('defeat_monster', 'gone', 1, 'quest_condition_missing'),
        ('reach_place', 'potion', 1, 'quest_condition_invalid'),
        ('hold_item', 'lady', 1, 'quest_condition_invalid'),
        ('defeat_npc', 'gate', 1, 'quest_condition_invalid'),
        ('reach_place', 'island', 1, 'quest_condition_impossible'),
        ('defeat_monster', 'rat', 3, 'quest_condition_impossible'),
    ],
    ids=['no-place', 'no-monster', 'item-as-place', 'person-as-item', 'place-as-person', 'off-map', 'too-many-rats'],
)
async def test_a_condition_must_point_at_something_possible(
    client: AsyncClient, me: dict[str, str], kind: str, target: str, count: int, problem: str
):
    world = await make_world(client, me)
    pointed = world[target] if target in world else {'id': str(uuid.uuid4())}
    scenario = await make_scenario(client, me, world, [quest(world, goal(kind, pointed, count))])

    response = await publish(client, me, scenario)

    # 외딴섬은 맵에 없다. 들쥐는 둘만 놓였다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == [problem]


def test_an_old_snapshot_reads_as_no_conditions():
    document = {'format': 29, 'quests': [{'entry_id': str(uuid.uuid4()), 'start': 'active'}]}

    upgraded = upgrade_from_29(document)

    assert upgraded['format'] == 30
    assert (upgraded['quests'][0]['conditions'], upgraded['quests'][0]['match']) == ([], 'all')
    assert 'conditions' not in document['quests'][0]


# --- 라운드 ---


async def test_reaching_the_place_succeeds_the_quest(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    reward = [{'entry_id': world['potion']['id'], 'count': 2}]
    table = await start(client, me, world, [quest(world, goal('reach_place', world['forest']), reward=reward)])

    await declare(client, me, table, '숲으로 간다.', move(world['forest']))
    await narrated()

    seen = await read_table(client, me, table)
    assert status_of(seen, '왕녀 구출') == 'succeeded'
    assert held_items(seen, ME) == [('치유 물약', 2)]
    (changed,) = await events_of(client, me, table, 'quest_changed')
    (closed,) = await events_of(client, me, table, 'round_closed')
    assert changed['actor_id'] is None
    assert changed['payload']['reason'] == 'conditions_met'
    assert (changed['payload']['previous'], changed['payload']['status']) == ('active', 'succeeded')
    # 라운드가 닫힌 일과 한 묶음이고 그보다 앞이다
    assert changed['action_group_id'] == closed['action_group_id']
    assert changed['sequence'] < closed['sequence']


async def test_a_finished_quest_is_not_finished_again(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    reward = [{'entry_id': world['potion']['id'], 'count': 2}]
    rules = [
        quest(world, goal('reach_place', world['forest']), reward=reward),
        {'entry_id': world['secret']['id'], 'start': 'active', 'conditions': [goal('reach_place', world['forest'])]},
    ]
    table = await start(client, me, world, rules)
    # 방장이 먼저 실패로 끝냈다. 조건을 채워도 되돌리지 않는다
    failed = await client.put(
        table_url(table, f'/quests/{world["secret"]["id"]}'), json={'status': 'failed'}, headers=me
    )
    assert failed.status_code == status.HTTP_200_OK, failed.text

    await declare(client, me, table, '숲으로 간다.', move(world['forest']))
    await narrated()
    await declare(client, me, table)
    await narrated()

    # 숲에 계속 서 있어도 이룬 것은 한 번이다. 보상도 한 번이다
    seen = await read_table(client, me, table)
    assert (status_of(seen, '왕녀 구출'), status_of(seen, '숨은 비밀')) == ('succeeded', 'failed')
    assert held_items(seen, ME) == [('치유 물약', 2)]
    reasons = [event['payload']['reason'] for event in await events_of(client, me, table, 'quest_changed')]
    assert reasons == [None, 'conditions_met']


async def test_not_yet_reached_stays_active(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    table = await start(client, me, world, [quest(world, goal('reach_place', world['forest']))])

    await declare(client, me, table)
    await narrated()

    assert status_of(await read_table(client, me, table), '왕녀 구출') == 'active'
    assert await events_of(client, me, table, 'quest_changed') == []


async def test_defeats_are_counted_across_rounds(client: AsyncClient, app: FastAPI, me: dict[str, str], narrated):
    world = await make_world(client, me)
    table = await start(client, me, world, [quest(world, goal('defeat_monster', world['rat'], 2))])
    first, second = await rat_ids(client, me, table)

    load_dice(app, [PASS, DOWN])
    await declare(client, me, table, '쥐를 찌른다.', strike(monster=first))
    await narrated()
    after_one = status_of(await read_table(client, me, table), '왕녀 구출')
    load_dice(app, [PASS, DOWN])
    await declare(client, me, table, '쥐를 찌른다.', strike(monster=second))
    await narrated()

    assert after_one == 'active'
    assert status_of(await read_table(client, me, table), '왕녀 구출') == 'succeeded'


async def test_defeating_the_person_succeeds_the_quest(client: AsyncClient, app: FastAPI, me: dict[str, str], narrated):
    world = await make_world(client, me)
    table = await start(client, me, world, [quest(world, goal('defeat_npc', world['lady']))])

    load_dice(app, [PASS, DOWN])
    await declare(client, me, table, '영애를 벤다.', strike(npc=world['lady']['id']))
    await narrated()

    assert status_of(await read_table(client, me, table), '왕녀 구출') == 'succeeded'


async def test_holding_enough_succeeds_at_the_first_close(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    starting = [{'entry_id': world['potion']['id'], 'count': 2}]
    table = await start(
        client, me, world, [quest(world, goal('hold_item', world['potion'], 2))], starting_items=starting
    )

    await declare(client, me, table)
    await narrated()

    assert status_of(await read_table(client, me, table), '왕녀 구출') == 'succeeded'


@pytest.mark.parametrize(('match', 'expected'), [('any', 'succeeded'), ('all', 'active')])
async def test_all_or_any(client: AsyncClient, me: dict[str, str], narrated, match: str, expected: str):
    world = await make_world(client, me)
    conditions = [goal('reach_place', world['forest']), goal('hold_item', world['pelt'], 5)]
    table = await start(client, me, world, [quest(world, *conditions, match=match)])

    # 숲에는 닿았지만 가죽은 없다
    await declare(client, me, table, '숲으로 간다.', move(world['forest']))
    await narrated()

    assert status_of(await read_table(client, me, table), '왕녀 구출') == expected


async def test_a_hidden_quest_is_revealed_as_succeeded(client: AsyncClient, me: dict[str, str], friend, narrated):
    world = await make_world(client, me)
    rule = quest(world, goal('reach_place', world['forest']), start='hidden')
    table = await start(client, me, world, [rule], friend)

    await declare(client, me, table, '숲으로 간다.', move(world['forest']))
    await declare(client, friend, table)
    await narrated()

    # 우연히 이룬 일도 이룬 것이다. 숨김에서 바로 성공이고, 모두에게 보인다
    seen = await read_table(client, friend, table)
    assert status_of(seen, '왕녀 구출') == 'succeeded'
    (changed,) = await events_of(client, friend, table, 'quest_changed')
    assert (changed['payload']['previous'], changed['payload']['due_at']) == ('hidden', None)


async def test_a_quest_without_conditions_never_succeeds(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    table = await start(client, me, world, [quest(world)])

    await declare(client, me, table, '숲으로 간다.', move(world['forest']))
    await narrated()

    assert status_of(await read_table(client, me, table), '왕녀 구출') == 'active'


async def test_achieving_in_the_last_round_beats_the_deadline(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    rule = {**quest(world, goal('reach_place', world['forest'])), 'time_limit_minutes': 20}
    clock = {'start_day': 1, 'start_hour': 8, 'round_minutes': 60}
    table = await start(client, me, world, [rule], clock=clock)

    # 8시 장면 동안 기한(8시 20분)이 지났다. 9시에 열린 라운드가 마지막이다
    await declare(client, me, table)
    await narrated()
    await declare(client, me, table, '숲으로 간다.', move(world['forest']))
    await narrated()

    # 이룬 것을 기한보다 먼저 본다. 실패로 바뀌지 않는다
    assert status_of(await read_table(client, me, table), '왕녀 구출') == 'succeeded'
    (changed,) = await events_of(client, me, table, 'quest_changed')
    assert changed['payload']['reason'] == 'conditions_met'


# --- 보상 ---


async def test_every_living_character_is_rewarded_but_the_dead(
    client: AsyncClient, me: dict[str, str], friend, session: AsyncSession, narrated
):
    world = await make_world(client, me)
    reward = [{'entry_id': world['potion']['id'], 'count': 2}, {'entry_id': world['pelt']['id'], 'count': 1}]
    rule = quest(world, goal('reach_place', world['forest']), reward=reward)
    starting = [{'entry_id': world['potion']['id'], 'count': 98}]
    table = await start(client, me, world, [rule], friend, starting_items=starting)
    await kill(session, FRIEND)

    await declare(client, me, table, '숲으로 간다.', move(world['forest']))
    await narrated()

    # 죽은 약사는 받지 않는다. 기사는 물약이 가득 차 하나만 받는다
    seen = await read_table(client, me, table)
    assert held_items(seen, ME) == [('치유 물약', 99), ('늑대 가죽', 1)]
    (changed,) = await events_of(client, me, table, 'quest_changed')
    (only,) = changed['payload']['rewards']
    assert only['user_id'] == str(ME)
    assert [(item['count'], item['capped']) for item in only['items']] == [(1, True), (1, False)]


# --- 서술 ---


def test_the_narrator_is_told_the_game_decides_quests():
    assert prompt.QUEST_NOTE.startswith('게임이 정한 퀘스트의 지금 상태다.')


# --- DB 를 쓰지 않는 작은 함수들 ---


def person(place: uuid.UUID | None, items: dict | None = None, dead: bool = False) -> SimpleNamespace:
    rows = [SimpleNamespace(entry_id=entry_id, count=count) for entry_id, count in (items or {}).items()]
    sheet = SimpleNamespace(place_id=place, died_at='then' if dead else None, items=rows)
    return SimpleNamespace(sheet=sheet)


def test_the_dead_neither_stand_nor_hold():
    here, potion = uuid.uuid4(), uuid.uuid4()
    table = SimpleNamespace(members=[person(here, {potion: 3}, dead=True), person(None, {potion: 2})])

    assert not reached(table, here)
    assert held(table, potion) == 2


def test_downed_and_dead_both_count_as_defeated():
    rat, other = uuid.uuid4(), uuid.uuid4()
    monsters = [
        SimpleNamespace(monster_id=rat, status=NpcStatus.DOWNED),
        SimpleNamespace(monster_id=rat, status=NpcStatus.DEAD),
        SimpleNamespace(monster_id=rat, status=NpcStatus.ALIVE),
        SimpleNamespace(monster_id=other, status=NpcStatus.DEAD),
    ]
    lady = uuid.uuid4()

    assert defeated_monsters(monsters, rat) == 2
    assert npc_defeated([SimpleNamespace(entry_id=lady, status=NpcStatus.DOWNED)], lady)
    assert not npc_defeated([SimpleNamespace(entry_id=lady, status=NpcStatus.ALIVE)], lady)
    assert not npc_defeated([], lady)


def test_no_conditions_is_never_achieved():
    quest_ = CatalogQuest(entry_id=uuid.uuid4(), name='구출', start='active', reward=[])
    table = SimpleNamespace(members=[])

    assert not is_achieved(quest_, table, [], [])


@pytest.mark.parametrize(('match', 'expected'), [(QuestMatch.ALL, False), (QuestMatch.ANY, True)])
def test_match_decides_with_some_met(match: QuestMatch, expected: bool):
    here = uuid.uuid4()
    conditions = (
        QuestConditionSnapshot(kind=QuestConditionKind.REACH_PLACE, target=here),
        QuestConditionSnapshot(kind=QuestConditionKind.HOLD_ITEM, target=uuid.uuid4(), count=1),
    )
    quest_ = CatalogQuest(
        entry_id=uuid.uuid4(), name='구출', start='active', reward=[], conditions=conditions, match=match
    )
    table = SimpleNamespace(members=[person(here)])

    assert is_achieved(quest_, table, [], []) is expected
