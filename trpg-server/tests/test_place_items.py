# trpg-server/tests/test_place_items.py

"""
장소에 놓인 물건(#279)을 검증한다. 판에 적고, 테이블이 남은 개수를 갖고, 줍고(take), 찾는다(search).

맵과 판은 test_quest_goals.py 의 것이다. 성문(시작)과 숲이 열린 길로 이어지고, 외딴섬은 맵에 없다.
물건은 치유 물약과 늑대 가죽이다. 주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다(찾는 판정의 눈).

보는 것.
  - 시나리오: 놓인 물건을 적고 판에 굳힌다. 숨긴 것에만 찾는 판정, 같은 줄 두 번은 거부.
    게시할 때 맵의 장소인지, 물건 항목인지, 판정이 규칙에 있는지 본다. 옛 판은 놓인 물건이 없는 것으로 읽는다.
  - 보이기: 서 본 장소의 보이는 물건만 응답에 실린다. 숨긴 물건은 아무에게도 보이지 않는다.
  - 줍기: 그 장소에 보이게 남은 것만 받는다. 차례가 오면 남은 만큼, 상한까지 줍는다. 앞사람이 가져갔으면 못 줍는다.
  - 찾기: 숨긴 물건을 찾으면 찾은 사람이 바로 갖는다. 상한을 넘은 것은 보이게 남는다. 못 찾으면 아무것도 적지 않는다.
  - 서술: 맵 절에 놓인 물건과 숨은 물건(실마리로만), 한 일의 줄에 줍기와 찾은 물건이 붙는다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient

from app.assets.scenarios.snapshot import read_snapshot
from app.assets.scenarios.upgrades import upgrade_from_31
from app.rounds.move_lines import describe_search, describe_take
from app.rounds.narrator import ItemNote, PlaceNote, SearchNote, TakeNote
from app.rounds.prompt import map_line
from tests.narration_model import asset_body
from tests.test_quest_goals import (
    SCENARIOS_URL,
    declare,
    load_dice,
    make_scenario,
    make_world,
    move,
    publish,
    start,
)
from tests.test_table_items import FRIEND, ME, bearer, events_of, give, read_table, table_url
from tests.test_table_items import held as held_items
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

PASS = 20
FAIL = 1
LOOK = '주위를 살핀다.'


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key) -> dict[str, str]:
    return bearer(signing_key, FRIEND)


def lying(world: dict, place: str, item: str, count: int = 1) -> dict:
    """보이게 놓인 물건 한 줄."""
    return {'place_id': world[place]['id'], 'entry_id': world[item]['id'], 'count': count}


def hidden(world: dict, place: str, item: str, count: int = 1, ability: str = 'wis') -> dict:
    """숨긴 물건 한 줄. 지혜로 보통에 찾는다."""
    find = {'ability': ability, 'difficulty': 'medium'}
    return {**lying(world, place, item, count), 'visibility': 'hidden', 'find': find}


def take(world: dict, item: str, count: int = 1) -> dict:
    return {'kind': 'take', 'item': world[item]['id'], 'count': count}


SEARCH = {'kind': 'search'}


def items_at(table: dict, world: dict, place: str) -> list[tuple[str, int]]:
    """응답의 맵에서 그 장소에 보이는 물건들."""
    found = next(spot for spot in table['map']['places'] if spot['entry_id'] == world[place]['id'])
    return [(item['name'], item['count']) for item in found['items']]


async def outcome(client: AsyncClient, me: dict, table: dict, number: int, user_id: uuid.UUID = ME) -> dict:
    response = await client.get(table_url(table, f'/rounds/{number}'), headers=me)
    declaration = next(item for item in response.json()['declarations'] if item['user_id'] == str(user_id))
    return declaration['outcome']


async def declare_raw(client: AsyncClient, headers: dict, table: dict, action: dict):
    body = {'content': LOOK, 'action': action}
    return await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=headers)


# --- 시나리오 ---


async def test_place_items_are_saved_and_published(client: AsyncClient, me: dict[str, str]):
    world = await make_world(client, me)
    rules = [lying(world, 'gate', 'potion', 2), hidden(world, 'forest', 'pelt')]
    scenario = await make_scenario(client, me, world, [], place_items=rules)

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert scenario['place_items'] == [
        {**rules[0], 'visibility': 'open', 'find': None},
        {**rules[1], 'find': {'ability': 'wis', 'difficulty': 'medium'}},
    ]
    published = read_snapshot(response.json()['snapshot']).place_items
    assert [(str(rule.place_id), rule.count, rule.visibility) for rule in published] == [
        (world['gate']['id'], 2, 'open'),
        (world['forest']['id'], 1, 'hidden'),
    ]


@pytest.mark.parametrize('case', ['hidden-without-find', 'open-with-find', 'twice', 'none'])
async def test_a_bad_place_item_is_refused(client: AsyncClient, me: dict[str, str], case: str):
    world = await make_world(client, me)
    rules = {
        'hidden-without-find': [{**lying(world, 'gate', 'potion'), 'visibility': 'hidden'}],
        'open-with-find': [{**lying(world, 'gate', 'potion'), 'find': {'ability': 'wis'}}],
        'twice': [lying(world, 'gate', 'potion'), lying(world, 'gate', 'potion', 3)],
        'none': [lying(world, 'gate', 'potion', 0)],
    }
    body = {'title': '성문', 'place_items': rules[case]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    ('rule', 'problem'),
    [
        (lambda world: lying(world, 'island', 'potion'), 'place_item_off_map'),
        (lambda world: lying(world, 'gate', 'lady'), 'item_not_item'),
        (lambda world: hidden(world, 'gate', 'potion', ability='luck'), 'place_item_find_invalid'),
    ],
    ids=['off-map', 'not-an-item', 'bad-find'],
)
async def test_a_place_item_must_be_possible(client: AsyncClient, me: dict[str, str], rule, problem: str):
    world = await make_world(client, me)
    scenario = await make_scenario(client, me, world, [], place_items=[rule(world)])

    response = await publish(client, me, scenario)

    # 외딴섬은 맵에 없다. 악역영애는 인물이다. 운은 규칙에 없는 능력치다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == [problem]


def test_an_old_snapshot_reads_as_no_place_items():
    document = {'format': 31}

    upgraded = upgrade_from_31(document)

    assert (upgraded['format'], upgraded['place_items']) == (32, [])
    assert 'place_items' not in document


# --- 보이기 ---


async def test_only_seen_places_show_their_open_items(client: AsyncClient, me: dict[str, str]):
    world = await make_world(client, me)
    rules = [lying(world, 'gate', 'potion', 2), hidden(world, 'gate', 'pelt'), lying(world, 'forest', 'pelt')]

    table = await start(client, me, world, [], place_items=rules)

    # 성문에는 서 있다. 숲은 열린 길로 알지만 아무도 서 본 적이 없다. 숨긴 늑대 가죽은 방장에게도 보이지 않는다
    assert items_at(table, world, 'gate') == [('치유 물약', 2)]
    assert items_at(table, world, 'forest') == []


# --- 줍기 ---


async def test_taking_an_item_moves_it_into_the_bag(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    table = await start(client, me, world, [], place_items=[lying(world, 'gate', 'potion', 3)])

    await declare(client, me, table, '물약을 줍는다.', take(world, 'potion', 2))
    await narrated()

    seen = await read_table(client, me, table)
    assert held_items(seen, ME) == [('치유 물약', 2)]
    assert items_at(seen, world, 'gate') == [('치유 물약', 1)]
    assert (await outcome(client, me, table, 1))['take'] == {
        'user_id': str(ME),
        'character_name': '기사',
        'place': {'entry_id': world['gate']['id'], 'name': '성문'},
        'entry_id': world['potion']['id'],
        'name': '치유 물약',
        'count': 2,
        'taken': 2,
        'total': 2,
        'reason': None,
    }
    (gained,) = await events_of(client, me, table, 'items_gained')
    (acted,) = await events_of(client, me, table, 'player_action')
    assert gained['actor_id'] is None
    assert gained['caused_by_sequence'] == acted['sequence']
    assert (gained['payload']['source'], gained['payload']['count'], gained['payload']['place']['name']) == (
        'place',
        2,
        '성문',
    )


async def test_asking_for_more_than_is_left_takes_what_is_left(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    table = await start(client, me, world, [], place_items=[lying(world, 'gate', 'potion', 2)])

    await declare(client, me, table, '물약을 다 줍는다.', take(world, 'potion', 5))
    await narrated()

    taken = (await outcome(client, me, table, 1))['take']
    assert (taken['taken'], taken['reason']) == (2, 'not_enough')
    assert items_at(await read_table(client, me, table), world, 'gate') == []


async def test_the_one_after_finds_nothing_left(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], narrated
):
    world = await make_world(client, me)
    table = await start(client, me, world, [], friend, place_items=[lying(world, 'gate', 'potion')])

    await declare(client, me, table, '물약을 줍는다.', take(world, 'potion'))
    await declare(client, friend, table, '물약을 줍는다.', take(world, 'potion'))
    await narrated()

    # 둘 다 받을 때는 남아 있었다. 차례가 먼저 온 기사가 주웠다
    mine, theirs = (await outcome(client, me, table, 1))['take'], (await outcome(client, me, table, 1, FRIEND))['take']
    assert (mine['taken'], theirs['taken'], theirs['reason']) == (1, 0, 'gone')
    assert len(await events_of(client, me, table, 'items_gained')) == 1


async def test_a_full_bag_takes_only_what_fits(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    table = await start(client, me, world, [], place_items=[lying(world, 'gate', 'potion', 3)])
    given = await give(client, me, table, ME, world['potion'], 98)
    assert given.status_code == status.HTTP_200_OK, given.text

    await declare(client, me, table, '물약을 줍는다.', take(world, 'potion', 3))
    await narrated()

    # 99 개까지만 든다. 못 주운 것은 그 자리에 남는다
    taken = (await outcome(client, me, table, 1))['take']
    assert (taken['taken'], taken['total'], taken['reason']) == (1, 99, 'full')
    assert items_at(await read_table(client, me, table), world, 'gate') == [('치유 물약', 2)]


@pytest.mark.parametrize('case', ['elsewhere', 'hidden', 'nothing'])
async def test_only_an_item_lying_here_in_sight_can_be_taken(client: AsyncClient, me: dict[str, str], case: str):
    world = await make_world(client, me)
    rules = [lying(world, 'forest', 'potion'), hidden(world, 'gate', 'pelt')]
    table = await start(client, me, world, [], place_items=rules)
    item = {'elsewhere': world['potion']['id'], 'hidden': world['pelt']['id'], 'nothing': str(uuid.uuid4())}[case]

    response = await declare_raw(client, me, table, {'kind': 'take', 'item': item})

    # 다른 곳의 물건, 숨긴 물건, 없는 물건을 가르지 않는다. 가르면 숨긴 물건이 드러난다
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'item' in response.text


# --- 찾기 ---


async def test_searching_finds_a_hidden_item_and_keeps_it(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    world = await make_world(client, me)
    table = await start(client, me, world, [], place_items=[hidden(world, 'gate', 'pelt', 2)])
    load_dice(app, [PASS])

    await declare(client, me, table, '마루 밑을 뒤진다.', SEARCH)
    await narrated()

    seen = await read_table(client, me, table)
    assert held_items(seen, ME) == [('늑대 가죽', 2)]
    assert items_at(seen, world, 'gate') == []
    (searched,) = await events_of(client, me, table, 'place_searched')
    assert searched['payload']['items'] == [
        {'entry_id': world['pelt']['id'], 'name': '늑대 가죽', 'count': 2, 'left': 0, 'total': 2}
    ]
    (gained,) = await events_of(client, me, table, 'items_gained')
    assert (gained['payload']['source'], gained['caused_by_sequence']) == ('search', searched['sequence'])


async def test_what_a_full_bag_cannot_hold_stays_in_sight(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    world = await make_world(client, me)
    table = await start(client, me, world, [], place_items=[hidden(world, 'gate', 'pelt', 3)])
    await give(client, me, table, ME, world['pelt'], 98)
    load_dice(app, [PASS])

    await declare(client, me, table, '마루 밑을 뒤진다.', SEARCH)
    await narrated()

    # 찾은 사람이 하나를 갖고, 남은 둘은 이제 보이는 물건이다. 다음 사람이 주울 수 있다
    assert items_at(await read_table(client, me, table), world, 'gate') == [('늑대 가죽', 2)]


async def test_a_failed_search_tells_nothing(client: AsyncClient, app: FastAPI, me: dict[str, str], narrated):
    world = await make_world(client, me)
    table = await start(client, me, world, [], place_items=[hidden(world, 'gate', 'pelt')])
    load_dice(app, [FAIL])

    await declare(client, me, table, '마루 밑을 뒤진다.', SEARCH)
    await narrated()

    # 숨긴 물건이 없는 곳을 찾았을 때와 같다. 굴린 것도 남지 않는다
    (searched,) = await events_of(client, me, table, 'place_searched')
    assert (searched['payload']['found'], searched['payload']['items']) == ([], [])
    assert await events_of(client, me, table, 'items_gained') == []
    assert items_at(await read_table(client, me, table), world, 'gate') == []


# --- 서술 ---


async def test_the_narrator_sees_items_lying_and_hidden(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    world = await make_world(client, me)
    rules = [lying(world, 'forest', 'potion', 2), hidden(world, 'forest', 'pelt')]
    table = await start(client, me, world, [], place_items=rules)

    await declare(client, me, table, '숲으로 간다.', move(world['forest']))
    await narrated()

    # 숲에 닿은 뒤의 장소다. 숨긴 늑대 가죽은 GM 만 안다
    (request,) = narrator.requests
    (moved,) = request.moves
    assert moved.place.items == [ItemNote(name='치유 물약', count=2)]
    assert moved.place.hidden_items == ['늑대 가죽']


def test_the_map_line_shows_items_and_hints():
    place = PlaceNote(
        name='광장',
        exits=['성문'],
        items=[ItemNote(name='치유 물약', count=2)],
        hidden_items=['은열쇠'],
    )

    line = map_line('광장', ['기사'], place)

    assert line == (
        '- 광장(기사): 나가는 길: 성문. 놓인 물건: 치유 물약 2개. 숨은 물건(플레이어는 모름, 실마리로만): 은열쇠'
    )


@pytest.mark.parametrize(
    ('note', 'line'),
    [
        (TakeNote(name='치유 물약', count=2, taken=2), '(줍기: 치유 물약 2개를 주웠다)'),
        (
            TakeNote(name='치유 물약', count=3, taken=1, reason='not_enough'),
            '(줍기: 치유 물약 1개를 주웠다. 남은 것만 주웠다)',
        ),
        (TakeNote(name='치유 물약', count=1, taken=0, reason='gone'), '(줍기: 치유 물약이(가) 남아 있지 않았다)'),
        (
            TakeNote(name='치유 물약', count=1, taken=0, reason='full'),
            '(줍기: 치유 물약을(를) 더 들 수 없어 줍지 못했다)',
        ),
    ],
)
def test_the_take_line(note: TakeNote, line: str):
    assert describe_take(note) == line


@pytest.mark.parametrize(
    ('note', 'line'),
    [
        (SearchNote(place='광장', items=[ItemNote(name='은열쇠', count=1)]), '(찾기: 은열쇠을(를) 찾아 챙겼다)'),
        (
            SearchNote(place='광장', found=['지하실'], items=[ItemNote(name='은열쇠', count=2)]),
            '(찾기: 길을 찾아냈다. 지하실(으)로 이어진다. 은열쇠 2개을(를) 찾아 챙겼다)',
        ),
        (SearchNote(place='광장'), '(찾기: 찾은 것이 없다)'),
    ],
)
def test_the_search_line_with_items(note: SearchNote, line: str):
    assert describe_search(note) == line
