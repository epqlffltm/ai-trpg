# trpg-server/tests/test_loots.py

"""
쓰러졌거나 죽은 대상이 지닌 물건을 빼앗는 행동(loot, #475, app/rounds/loots.py)을 검증한다.

NPC 의 판은 test_npc_items.py 의 것이다. 악역영애가 부채(늘 떨어짐)와 금화 5개(반)를 지녔다.
처음 쓰러뜨릴 때 금화가 떨어지지 않는 눈(51)을 써서 금화가 악역영애에게 남게 한다.
몬스터의 판은 test_monster_drops.py 의 것이다. 수로 쥐가 늑대 가죽 2개(늘)와 송곳니 1개(반)를 지녔다.
처음 쓰러뜨릴 때 송곳니가 떨어지지 않는 눈(51)을 써서 송곳니가 쥐에게 남게 한다. 해골 병사는 깊은 수로에 있다.

보는 것.
  - 행동의 모양: monster 와 npc 중 하나만 적는다.
  - 받을 때: 살아 있는(쓰러지지 않은) 대상, 장면에 없는 인물, 다른 장소의 마리, 지니지 않은 물건은 거부한다.
  - 차례: 굴리지 않고 줄을 통째로 갖는다. 죽은 대상에게서도 가져간다. NPC 의 태도는 바뀌지 않는다.
    앞사람이 먼저 가져갔으면 gone, 앞사람이 회복시켜 깨어 있으면 awake, 가득이면 full.
  - 이벤트와 서술: items_gained 의 source 가 loot 이고 그 대상이 적힌다. 빼앗기의 줄이 서술에 간다.
맨 아래에는 DB 를 쓰지 않는 작은 함수들의 테스트가 있다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError

from app.engine.action import LootAction
from app.rounds.loots import take
from app.rounds.move_lines import describe_loot
from app.rounds.narrator import LootNote
from app.tables.carried import Carried
from app.tables.models import TableItem
from tests.test_monster_combat import monster_named
from tests.test_monster_drops import kill_first_rat, start_table
from tests.test_npc_actions import PASS, PUNCH, TEND, bearer, events_of, load_dice, people, punch, table_url, tend
from tests.test_npc_steals import FRIEND, ME, outcome, send, start

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key) -> dict[str, str]:
    return bearer(signing_key, FRIEND)


LOOT = '쓰러진 상대의 품을 뒤진다.'
# 악역영애(최대 HP 10)를 쓰러뜨리는 큰 피해(2d8)와 부상 표(부상 없음), 금화가 떨어지지 않는 눈
KNOCK_DOWN = [PASS, 8, 8, 1, 51]
# 죽이려는 큰 피해. 죽은 인물에게는 부상 표를 굴리지 않는다
KILL = [PASS, 8, 8, 51]


def loot(world: dict, item: str, npc: str = 'lady') -> dict:
    return {'kind': 'loot', 'npc': world[npc]['id'], 'item': world[item]['id']}


def loot_monster(monster: dict, entry: dict) -> dict:
    return {'kind': 'loot', 'monster': monster['id'], 'item': entry['id']}


async def lady_down(client: AsyncClient, app: FastAPI, me: dict, world: dict, narrated, *others: dict, lethal=False):
    """라운드 1 에 엘프가 악역영애를 쓰러뜨린다(lethal 이면 죽인다). others 는 그 라운드에 말만 한다."""
    rolls = KILL if lethal else KNOCK_DOWN
    # 앉은 사람이 둘이면 떨어진 부채를 받을 사람을 고르는 눈이 하나 더 든다
    load_dice(app, rolls + ([1] if others else []))
    action = punch(world['lady']['id'], 'heavy', lethal=lethal)
    assert (await send(client, me, world, action, content=PUNCH)).status_code == status.HTTP_200_OK
    for headers in others:
        body = {'content': '지켜본다.'}
        await client.put(table_url(world['table'], '/rounds/current/declaration'), json=body, headers=headers)
    await narrated()


# --- 행동의 모양과 받을 때 ---


@pytest.mark.parametrize(
    'body',
    [
        {'kind': 'loot', 'item': str(uuid.uuid4())},
        {'kind': 'loot', 'item': str(uuid.uuid4()), 'monster': str(uuid.uuid4()), 'npc': str(uuid.uuid4())},
    ],
)
def test_a_loot_names_exactly_one_victim(body: dict):
    with pytest.raises(ValidationError):
        LootAction.model_validate(body)


async def test_a_standing_npc_cannot_be_looted(client: AsyncClient, me: dict):
    world = await start(client, me)

    response = await send(client, me, world, loot(world, 'coins'), content=LOOT)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'target_not_down'


@pytest.mark.parametrize(
    ('change', 'detail'),
    [
        (
            lambda world: loot(world, 'coins', npc='dwarf'),
            'action.npc 가 이번 장면의 인물이 아니거나 다른 장소에 있습니다.',
        ),
        (
            lambda world: {**loot(world, 'coins'), 'item': world['highway']['id']},
            'action.item 이 그 몬스터나 인물이 지금 지닌 물건이 아닙니다.',
        ),
    ],
)
async def test_what_cannot_be_looted_is_refused(client: AsyncClient, app: FastAPI, me: dict, narrated, change, detail):
    world = await start(client, me)
    await lady_down(client, app, me, world, narrated)

    response = await send(client, me, world, change(world), content=LOOT)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['detail'] == detail


async def test_a_monster_not_in_the_scene_cannot_be_looted(client: AsyncClient, me: dict):
    world = await start_table(client, me)
    # 해골 병사는 깊은 수로에 있다. 아무도 서 있지 않아 장면에도 없다
    skeleton = {'id': str(uuid.uuid4())}

    response = await send(client, me, world, loot_monster(skeleton, world['pelt']), content=LOOT)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['detail'] == 'action.monster 가 지금 장소의 몬스터가 아닙니다.'


async def test_a_monster_at_another_place_cannot_be_looted(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated
):
    world = await start_table(client, me, friend)
    # 드워프 기사가 깊은 수로로 간다. 해골 병사가 장면에 들지만 엘프는 수로 입구에 있다
    move = {'kind': 'move', 'place': world['deep']['id']}
    await client.put(table_url(world['table'], '/rounds/current/declaration'), json={'content': '쉰다.'}, headers=me)
    assert (await send(client, friend, world, move, content='깊이 들어간다.')).status_code == status.HTTP_200_OK
    await narrated()
    skeleton = await monster_named(client, me, world['table'], '해골 병사')

    response = await send(client, me, world, loot_monster(skeleton, world['pelt']), content=LOOT)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['detail'] == 'action.monster 가 지금 장소의 몬스터가 아닙니다.'


# --- 차례 ---


async def test_a_downed_npc_is_looted_without_a_roll(client: AsyncClient, app: FastAPI, me: dict, narrated):
    world = await start(client, me)
    await lady_down(client, app, me, world, narrated)

    dice = load_dice(app, [])
    assert (await send(client, me, world, loot(world, 'coins'), content=LOOT)).status_code == status.HTTP_200_OK
    await narrated()

    looted = (await outcome(client, me, world, 2))['loot']
    assert looted == {
        'user_id': str(ME),
        'character_name': '엘프',
        'monster_id': None,
        'monster_name': None,
        'npc_id': world['lady']['id'],
        'npc_name': '악역영애',
        'entry_id': world['coins']['id'],
        'name': '금화',
        'looted': True,
        'count': 5,
        'left': 0,
        'total': 5,
        'reason': None,
    }
    assert dice.remaining == 0
    (lady,) = (await people(client, me, world['table']))['people']
    # 의식이 없어서 태도는 그대로다
    assert (lady['items'], lady['attitude']) == ([], 'neutral')
    assert await events_of(client, me, world['table'], 'npc_attitude_changed') == []


async def test_a_dead_npc_is_looted_too(client: AsyncClient, app: FastAPI, me: dict, narrated):
    world = await start(client, me)
    await lady_down(client, app, me, world, narrated, lethal=True)

    await send(client, me, world, loot(world, 'coins'), content=LOOT)
    await narrated()

    assert (await outcome(client, me, world, 2))['loot']['count'] == 5


async def test_a_downed_monster_is_looted(client: AsyncClient, app: FastAPI, me: dict, narrated):
    world = await start_table(client, me)
    # 쥐를 쓰러뜨린다. 늑대 가죽은 떨어지고 송곳니(51)는 쥐에게 남는다
    _, rat, _ = await kill_first_rat(client, app, me, world, [PASS, 8, 51])
    await narrated()
    load_dice(app, [])

    await send(client, me, world, loot_monster(rat, world['tooth']), content=LOOT)
    await narrated()

    looted = (await outcome(client, me, world, 2))['loot']
    assert (looted['monster_id'], looted['monster_name'], looted['count']) == (rat['id'], '수로 쥐 1', 1)
    assert (await monster_named(client, me, world['table'], '수로 쥐 1'))['items'] == []
    gained = (await events_of(client, me, world['table'], 'items_gained'))[-1]['payload']
    assert {key: gained[key] for key in ('source', 'monster_id', 'monster_name', 'name')} == {
        'source': 'loot',
        'monster_id': rat['id'],
        'monster_name': '수로 쥐 1',
        'name': '송곳니',
    }
    narrations = await events_of(client, me, world['table'], 'gm_narration')
    assert '(빼앗기: 수로 쥐 1 에게서 송곳니 1개를 가져갔다)' in narrations[-1]['payload']['text']


async def test_the_gain_names_the_npc(client: AsyncClient, app: FastAPI, me: dict, narrated):
    world = await start(client, me)
    await lady_down(client, app, me, world, narrated)

    await send(client, me, world, loot(world, 'coins'), content=LOOT)
    await narrated()

    gained = (await events_of(client, me, world['table'], 'items_gained'))[-1]
    assert gained['actor_id'] is None
    assert {key: gained['payload'][key] for key in ('source', 'npc_id', 'npc_name', 'count', 'round')} == {
        'source': 'loot',
        'npc_id': world['lady']['id'],
        'npc_name': '악역영애',
        'count': 5,
        'round': 2,
    }
    assert 'monster_id' not in gained['payload']
    narrations = await events_of(client, me, world['table'], 'gm_narration')
    assert '(빼앗기: 악역영애 에게서 금화 5개를 가져갔다)' in narrations[-1]['payload']['text']


async def test_a_second_looter_finds_the_line_gone(client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated):
    world = await start(client, me, friend)
    await lady_down(client, app, me, world, narrated, friend)

    await send(client, me, world, loot(world, 'coins'), content=LOOT)
    await send(client, friend, world, loot(world, 'coins'), content=LOOT)
    await narrated()

    theirs = (await outcome(client, me, world, 2, FRIEND))['loot']
    assert (theirs['looted'], theirs['count'], theirs['reason']) == (False, 0, 'gone')
    assert len(await events_of(client, me, world['table'], 'items_gained')) == 2


async def test_an_npc_woken_earlier_in_the_round_is_not_looted(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated
):
    world = await start(client, me, friend)
    await lady_down(client, app, me, world, narrated, friend)
    # 엘프가 먼저 상처를 싸매 일으키고, 드워프 기사는 그 뒤에 뒤진다
    load_dice(app, [PASS, 2])

    await send(client, me, world, tend(world['lady']['id']), content=TEND)
    await send(client, friend, world, loot(world, 'coins'), content=LOOT)
    await narrated()

    theirs = (await outcome(client, me, world, 2, FRIEND))['loot']
    assert (theirs['looted'], theirs['reason']) == (False, 'awake')
    # 드워프 기사의 이름에 '드워프'가 있어 드워프도 장면에 나온다. 악역영애를 찾는다
    cast = (await people(client, me, world['table']))['people']
    lady = next(person for person in cast if person['id'] == world['lady']['id'])
    assert [thing['name'] for thing in lady['items']] == ['금화']


# --- DB 를 쓰지 않는 작은 함수들 ---


def victim_holding(coins: uuid.UUID, count: int) -> SimpleNamespace:
    line = Carried(slot=0, entry_id=coins, count=count, equipped=False, chance=50)
    counts = {}
    return SimpleNamespace(held=[line], set_count=lambda slot, value: counts.update({slot: value}), counts=counts)


def judging_for(coins: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(table=SimpleNamespace(id=uuid.uuid4()), items={coins: SimpleNamespace(name='금화')})


def test_a_looter_near_the_limit_takes_what_fits_and_leaves_the_rest():
    coins = uuid.uuid4()
    thief = SimpleNamespace(sheet=SimpleNamespace(id=uuid.uuid4(), items=[TableItem(entry_id=coins, count=97)]))
    victim = victim_holding(coins, 5)

    result = take(judging_for(coins), thief, victim, coins)

    assert result == {'looted': True, 'count': 2, 'left': 3, 'total': 99, 'reason': 'full'}
    assert victim.counts == {0: 3}


def test_a_full_looter_takes_nothing():
    coins = uuid.uuid4()
    thief = SimpleNamespace(sheet=SimpleNamespace(id=uuid.uuid4(), items=[TableItem(entry_id=coins, count=99)]))

    result = take(judging_for(coins), thief, victim_holding(coins, 5), coins)

    assert (result['looted'], result['count'], result['left'], result['reason']) == (False, 0, 5, 'full')


@pytest.mark.parametrize(
    ('note', 'line'),
    [
        (LootNote('수로 쥐 1', '송곳니', 1, True), '(빼앗기: 수로 쥐 1 에게서 송곳니 1개를 가져갔다)'),
        (
            LootNote('악역영애', '금화', 2, True, 'full'),
            '(빼앗기: 악역영애 에게서 금화 2개를 가져갔다. 더 들 수 없어 남은 것은 두었다)',
        ),
        (
            LootNote('수로 쥐 1', '송곳니', 0, False, 'gone'),
            '(빼앗기: 수로 쥐 1 은(는) 송곳니을(를) 이미 지니지 않았다)',
        ),
        (LootNote('악역영애', '금화', 0, False, 'awake'), '(빼앗기: 악역영애 이(가) 깨어 있어 가져가지 못했다)'),
        (LootNote('악역영애', '금화', 0, False, 'full'), '(빼앗기: 금화을(를) 더 들 수 없어 가져가지 못했다)'),
    ],
)
def test_the_loot_line(note: LootNote, line: str):
    assert describe_loot(note) == line
