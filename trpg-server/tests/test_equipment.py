# trpg-server/tests/test_equipment.py

"""
장비의 칸과 착용(#276, app/tables/equipment.py, app/tables/wearing.py)을 검증한다.

판: 룰북은 SRD5 템플릿(칸: 주손, 보조손, 몸, 머리). 검은 주손이나 보조손 하나, 대검은 두 손을 함께,
사슬 갑옷은 몸에 들어간다. 단검도 한 손이다. 물약은 소모품이라 착용하지 않는다. 등불은 규칙이 없다.
모두 검 둘(하나는 주손에), 사슬 갑옷(몸에), 대검, 단검, 물약을 가지고 시작한다.

보는 것.
  - 규칙과 시나리오의 모양: 칸이 겹치지 않고, 칸은 장비에만, 차지하는 칸은 들어갈 수 있는 칸보다 많지 않다.
  - 시작할 때 판에 적은 대로 착용한다. 새 캐릭터도 같다. 게시할 때 칸이 맞지 않으면 막는다.
  - 착용하고 벗기: 찬 칸은 비우고 끼운다. 두 손 무기는 두 칸을 함께 비운다. 가진 것이 모두 착용 중이면 하나를 옮긴다.
    선언을 받는 중에만, 쓰러지지 않은 자기 캐릭터만 바꾼다. 이벤트(equipment_changed)가 남는다.
  - 소지품이 줄면 착용하지 않은 것부터 나가고, 모자라면 착용도 빠진다.
  - 서술과 기록: 착용이 한 일의 줄에 붙는다(narration-51). 기록에는 칸의 이름으로 적힌다.
맨 아래에는 DB 를 쓰지 않는 작은 함수들의 테스트가 있다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import status
from httpx import AsyncClient
from pydantic import ValidationError
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.schemas import ItemRule, QuestRule
from app.assets.scenarios.snapshot import ItemStackSnapshot, wear_fault
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_46
from app.engine.ruleset import Ruleset
from app.engine.templates import SRD5
from app.events.models import EventType, TableEvent
from app.main import API_PREFIX
from app.rounds.move_lines import describe_move
from app.rounds.narrator import Move, WornNote
from app.tables import equipment, items
from app.tables.errors import TableOptionError
from app.tables.models import TableItem, TableSheet, TableWorn
from app.transcripts.labels import Labels
from app.transcripts.markdown import render_event
from tests.narration_model import asset_body
from tests.sheets import SHEET
from tests.test_clock_narration import held_jobs  # noqa: F401 (테스트가 픽스처로 쓴다)
from tests.test_table_items import kill

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
STRANGER = uuid.UUID('99999999-2222-4333-8444-555555555555')
HANDS = ['main_hand', 'off_hand']


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    return {'Authorization': f'Bearer {make_token(signing_key, make_access_claims(sub=str(user_id)))}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, FRIEND)


@pytest.fixture
def stranger(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, STRANGER)


async def post(client: AsyncClient, url: str, headers: dict, **body) -> dict:
    response = await client.post(url, json=asset_body(url, body), headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def table_url(world: dict, path: str = '') -> str:
    return f'{TABLES_URL}/{world["table"]["id"]}{path}'


async def make_lore(client: AsyncClient, me: dict) -> dict:
    """물건 여섯(검, 대검, 단검, 사슬 갑옷, 물약, 등불)과 사건 하나가 든 로어북과 SRD5 룰북."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='무기고')
    url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'

    async def entry(name: str, kind: str = 'item') -> dict:
        return await post(client, url, me, name=name, keywords=[], content=f'{name}의 설정', kind=kind)

    return {
        'lorebook': lorebook,
        'sword': await entry('검'),
        'greatsword': await entry('대검'),
        'dagger': await entry('단검'),
        'mail': await entry('사슬 갑옷'),
        'potion': await entry('치유 물약'),
        'lamp': await entry('등불'),
        'hunt': await entry('늑대 사냥', 'event'),
        'rulebook': await post(client, RULEBOOKS_URL, me, title='룰북'),
    }


def item_rules(lore: dict) -> list[dict]:
    return [
        {'entry_id': lore['sword']['id'], 'slots': HANDS},
        {'entry_id': lore['greatsword']['id'], 'slots': HANDS, 'slot_count': 2},
        {'entry_id': lore['dagger']['id'], 'slots': HANDS},
        {'entry_id': lore['mail']['id'], 'slots': ['body']},
        {'entry_id': lore['potion']['id'], 'kind': 'consumable', 'heals': 'light'},
    ]


def starting(lore: dict) -> list[dict]:
    return [
        {'entry_id': lore['sword']['id'], 'count': 2, 'wear': ['main_hand']},
        {'entry_id': lore['mail']['id'], 'count': 1, 'wear': ['body']},
        {'entry_id': lore['greatsword']['id'], 'count': 1},
        {'entry_id': lore['dagger']['id'], 'count': 1},
        {'entry_id': lore['potion']['id'], 'count': 1},
    ]


def scenario_body(lore: dict, **fields) -> dict:
    body = {
        'title': '무기고',
        'rulebook_id': lore['rulebook']['id'],
        'lorebook_ids': [lore['lorebook']['id']],
        'openings': ['무기고의 문이 열린다.'],
        'default_sheet': SHEET,
        'default_npc_sheet': SHEET,
        'items': item_rules(lore),
        'starting_items': starting(lore),
    }
    return {**body, **fields}


async def publish(client: AsyncClient, me: dict, lore: dict, **fields):
    scenario = await post(client, SCENARIOS_URL, me, **scenario_body(lore, **fields))
    return scenario, await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)


async def start(client: AsyncClient, me: dict, *others: dict) -> dict:
    """무기고의 판으로 테이블을 시작한다. 나(기사)와 others(약사)가 앉는다."""
    lore = await make_lore(client, me)
    scenario, published = await publish(client, me, lore)
    assert published.status_code == status.HTTP_201_CREATED, published.text
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1 + len(others))
    world = {**lore, 'table': table}
    for headers, name in zip([me, *others], ['기사', '약사'], strict=False):
        if headers is not me:
            await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=headers)
        await client.put(table_url(world, '/character'), json={'name': name}, headers=headers)
    started = await client.post(table_url(world, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return world


async def wear(client: AsyncClient, headers: dict, world: dict, item: str, *slots: str):
    body = {'entry_id': world[item]['id'], 'slots': list(slots)}
    return await client.put(table_url(world, '/equipment'), json=body, headers=headers)


async def take_off(client: AsyncClient, headers: dict, world: dict, slot: str):
    return await client.delete(table_url(world, f'/equipment/{slot}'), headers=headers)


def worn_in(detail: dict, user_id: uuid.UUID = ME) -> list[tuple[str, list[str]]]:
    sheet = next(member for member in detail['members'] if member['user_id'] == str(user_id))['sheet']
    return [(worn['name'], worn['slots']) for worn in sheet['worn']]


async def read(client: AsyncClient, headers: dict, world: dict) -> dict:
    return (await client.get(table_url(world), headers=headers)).json()


async def events_of(client: AsyncClient, headers: dict, world: dict, type_: str) -> list[dict]:
    response = await client.get(table_url(world, '/events'), params={'limit': 100}, headers=headers)
    return [event for event in response.json()['items'] if event['type'] == type_]


# --- 시작할 때 ---


async def test_everyone_starts_wearing_what_the_scenario_says(client: AsyncClient, me: dict, friend: dict):
    world = await start(client, me, friend)

    detail = await read(client, me, world)

    # 칸의 차례다(주손, 몸). 착용한 검도 소지품에 들어 있다
    assert worn_in(detail) == worn_in(detail, FRIEND) == [('검', ['main_hand']), ('사슬 갑옷', ['body'])]
    assert [slot['key'] for slot in detail['rules']['equipment_slots']] == ['main_hand', 'off_hand', 'body', 'head']
    sheet = detail['members'][0]['sheet']
    assert ('검', 2) in [(item['name'], item['count']) for item in sheet['items']]


async def test_the_catalog_tells_where_each_thing_goes(client: AsyncClient, me: dict):
    world = await start(client, me)

    catalog = {item['name']: (item['slots'], item['slot_count']) for item in (await read(client, me, world))['items']}

    assert catalog['대검'] == (HANDS, 2)
    assert catalog['사슬 갑옷'] == (['body'], 1)
    assert catalog['등불'] == ([], 1)


async def test_a_new_character_starts_wearing_afresh(client: AsyncClient, me: dict, session: AsyncSession):
    world = await start(client, me)
    await take_off(client, me, world, 'body')
    await kill(session, ME)

    arrived = await client.post(table_url(world, '/character'), json={'name': '새 기사'}, headers=me)

    assert arrived.status_code == status.HTTP_201_CREATED, arrived.text
    assert worn_in(arrived.json()) == [('검', ['main_hand']), ('사슬 갑옷', ['body'])]


# --- 착용하고 벗기 ---


async def test_wearing_fills_an_empty_slot_and_everyone_is_told(client: AsyncClient, me: dict, friend: dict):
    world = await start(client, me, friend)

    response = await wear(client, me, world, 'sword', 'off_hand')

    assert response.status_code == status.HTTP_200_OK, response.text
    assert worn_in(response.json()) == [('검', ['main_hand']), ('검', ['off_hand']), ('사슬 갑옷', ['body'])]
    (changed,) = await events_of(client, friend, world, 'equipment_changed')
    assert changed['actor_id'] == str(ME)
    assert changed['payload'] == {
        'user_id': str(ME),
        'character_name': '기사',
        'change': 'wear',
        'entry_id': world['sword']['id'],
        'name': '검',
        'slots': ['off_hand'],
        'removed': [],
    }


async def test_a_two_handed_weapon_empties_both_hands(client: AsyncClient, me: dict):
    world = await start(client, me)
    await wear(client, me, world, 'dagger', 'off_hand')

    response = await wear(client, me, world, 'greatsword', 'main_hand', 'off_hand')

    assert worn_in(response.json()) == [('대검', HANDS), ('사슬 갑옷', ['body'])]
    (_, changed) = await events_of(client, me, world, 'equipment_changed')
    assert [removed['name'] for removed in changed['payload']['removed']] == ['검', '단검']


async def test_taking_off_a_two_handed_weapon_frees_both_hands(client: AsyncClient, me: dict):
    world = await start(client, me)
    await wear(client, me, world, 'greatsword', 'main_hand', 'off_hand')

    response = await take_off(client, me, world, 'off_hand')

    assert worn_in(response.json()) == [('사슬 갑옷', ['body'])]
    (_, taken) = await events_of(client, me, world, 'equipment_changed')
    assert (taken['payload']['change'], taken['payload']['slots']) == ('take_off', HANDS)


async def test_the_only_one_held_is_moved(client: AsyncClient, me: dict):
    world = await start(client, me)
    await wear(client, me, world, 'dagger', 'off_hand')

    # 단검은 하나뿐이다. 주손에 끼우면 보조손에서 옮겨 온다
    response = await wear(client, me, world, 'dagger', 'main_hand')

    assert worn_in(response.json()) == [('단검', ['main_hand']), ('사슬 갑옷', ['body'])]


async def test_an_empty_slot_is_left_as_it_is(client: AsyncClient, me: dict):
    world = await start(client, me)

    response = await take_off(client, me, world, 'head')

    assert response.status_code == status.HTTP_200_OK
    assert await events_of(client, me, world, 'equipment_changed') == []


@pytest.mark.parametrize(
    ('item', 'slots', 'code', 'field'),
    [
        ('potion', ['main_hand'], 422, 'entry_id'),
        ('lamp', ['main_hand'], 422, 'entry_id'),
        ('sword', ['body'], 422, 'slots'),
        ('sword', ['main_hand', 'off_hand'], 422, 'slots'),
        ('greatsword', ['main_hand'], 422, 'slots'),
        ('greatsword', ['main_hand', 'main_hand'], 422, 'slots'),
        ('mail', ['wings'], 422, 'slots'),
    ],
)
async def test_what_does_not_fit_is_refused(
    client: AsyncClient, me: dict, item: str, slots: list[str], code: int, field: str
):
    world = await start(client, me)

    response = await wear(client, me, world, item, *slots)

    assert response.status_code == code
    assert field in response.text
    assert worn_in(await read(client, me, world)) == [('검', ['main_hand']), ('사슬 갑옷', ['body'])]


async def test_only_what_is_held_is_worn(client: AsyncClient, me: dict, session: AsyncSession):
    world = await start(client, me)
    await session.execute(
        text('DELETE FROM table_items WHERE entry_id = :id'), {'id': uuid.UUID(world['dagger']['id'])}
    )
    await session.commit()

    response = await wear(client, me, world, 'dagger', 'off_hand')

    assert response.status_code == status.HTTP_409_CONFLICT
    assert 'not_enough_items' in response.text


async def test_only_someone_seated_changes_equipment(client: AsyncClient, me: dict, stranger: dict):
    world = await start(client, me)

    response = await wear(client, stranger, world, 'sword', 'off_hand')

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_a_downed_character_cannot_change_equipment(client: AsyncClient, me: dict, session: AsyncSession):
    world = await start(client, me)
    await session.execute(text('UPDATE table_sheets SET hp = 0 WHERE user_id = :id'), {'id': ME})
    await session.commit()

    wearing = await wear(client, me, world, 'sword', 'off_hand')
    taking = await take_off(client, me, world, 'body')

    assert (wearing.status_code, taking.status_code) == (status.HTTP_409_CONFLICT, status.HTTP_409_CONFLICT)
    assert 'character_downed' in wearing.text


async def test_nothing_changes_while_the_round_closes(client: AsyncClient, me: dict, held_jobs):  # noqa: F811
    world = await start(client, me)
    # 혼자 앉았다. 선언을 내면 라운드가 닫기 시작하고, 서술은 돌지 않아 닫는 중에 머문다
    body = {'content': '주위를 살핀다.'}
    await client.put(table_url(world, '/rounds/current/declaration'), json=body, headers=me)

    response = await wear(client, me, world, 'sword', 'off_hand')

    assert response.status_code == status.HTTP_409_CONFLICT
    assert 'round_closing' in response.text


# --- 소지품이 줄면 ---


def give(world: dict, item: str, count: int) -> dict:
    return {'kind': 'give', 'item': world[item]['id'], 'count': count, 'target': str(FRIEND)}


async def close_with_gift(client: AsyncClient, me: dict, friend: dict, world: dict, action: dict, narrated) -> dict:
    """내가 건네고 약사는 지켜본다. 라운드가 닫힌 뒤의 테이블을 돌려준다."""
    url = table_url(world, '/rounds/current/declaration')
    response = await client.put(url, json={'content': '건넨다.', 'action': action}, headers=me)
    assert response.status_code == status.HTTP_200_OK, response.text
    await client.put(url, json={'content': '지켜본다.'}, headers=friend)
    await narrated()
    return await read(client, me, world)


async def test_what_is_not_worn_goes_first(client: AsyncClient, me: dict, friend: dict, narrated):
    world = await start(client, me, friend)

    detail = await close_with_gift(client, me, friend, world, give(world, 'sword', 1), narrated)

    # 검 둘 중 착용하지 않은 것을 건넸다. 주손의 검은 그대로다
    assert worn_in(detail) == [('검', ['main_hand']), ('사슬 갑옷', ['body'])]


async def test_giving_away_what_is_worn_takes_it_off(client: AsyncClient, me: dict, friend: dict, narrated):
    world = await start(client, me, friend)

    detail = await close_with_gift(client, me, friend, world, give(world, 'mail', 1), narrated)

    assert worn_in(detail) == [('검', ['main_hand'])]
    # 받은 사람은 착용하지 않은 채로 받는다
    assert worn_in(detail, FRIEND) == [('검', ['main_hand']), ('사슬 갑옷', ['body'])]


# --- 서술 ---


async def test_the_narrator_hears_what_each_one_wears(client: AsyncClient, me: dict, narrated):
    world = await start(client, me)
    await wear(client, me, world, 'greatsword', 'main_hand', 'off_hand')
    body = {'content': '대검을 고쳐 쥔다.'}

    await client.put(table_url(world, '/rounds/current/declaration'), json=body, headers=me)
    await narrated()

    # 가짜 서술자는 받은 것을 그대로 늘어놓는다
    scene = (await client.get(table_url(world, '/rounds/current'), headers=me)).json()['scene']
    assert '[착용: 대검(주손·보조손), 사슬 갑옷(몸)]' in scene


# --- 게시 ---


@pytest.mark.parametrize(
    ('change', 'problem'),
    [
        (
            lambda lore: {'items': [{'entry_id': lore['mail']['id'], 'slots': ['wings']}], 'starting_items': []},
            'item_slot_invalid',
        ),
        (
            lambda lore: {'starting_items': [{'entry_id': lore['mail']['id'], 'count': 1, 'wear': ['main_hand']}]},
            'starting_wear_invalid',
        ),
        (
            lambda lore: {
                'starting_items': [{'entry_id': lore['greatsword']['id'], 'count': 1, 'wear': ['main_hand']}]
            },
            'starting_wear_invalid',
        ),
        (
            lambda lore: {'starting_items': [{'entry_id': lore['lamp']['id'], 'count': 1, 'wear': ['head']}]},
            'starting_wear_invalid',
        ),
        (
            lambda lore: {
                'starting_items': [{'entry_id': lore['sword']['id'], 'count': 1, 'wear': ['main_hand']}],
                'pregens': [
                    {
                        'name': '검사',
                        'sheet': SHEET,
                        'items': [{'entry_id': lore['dagger']['id'], 'count': 1, 'wear': ['main_hand']}],
                    }
                ],
            },
            'starting_wear_invalid',
        ),
    ],
)
async def test_wearing_that_does_not_fit_is_not_published(client: AsyncClient, me: dict, change, problem: str):
    lore = await make_lore(client, me)

    _, response = await publish(client, me, lore, **change(lore))

    assert response.status_code == status.HTTP_409_CONFLICT, response.text
    assert response.json()['problems'] == [problem]


async def test_the_slots_are_frozen_into_the_version(client: AsyncClient, me: dict):
    lore = await make_lore(client, me)

    _, response = await publish(client, me, lore)

    snapshot = response.json()['snapshot']
    assert [slot['key'] for slot in snapshot['rulebook']['rules']['equipment_slots']] == [
        'main_hand',
        'off_hand',
        'body',
        'head',
    ]
    assert snapshot['items'][1]['slots'] == HANDS and snapshot['items'][1]['slot_count'] == 2
    assert snapshot['starting_items'][0]['wear'] == ['main_hand']


# --- DB 를 쓰지 않는 것 ---


SWORD = uuid.UUID('aaaaaaaa-0000-4000-8000-000000000001')
GREATSWORD = uuid.UUID('aaaaaaaa-0000-4000-8000-000000000002')
MAIL = uuid.UUID('aaaaaaaa-0000-4000-8000-000000000003')
TABLE = uuid.UUID('aaaaaaaa-0000-4000-8000-000000000009')


def sheet_with(*worn: tuple[uuid.UUID, list[str]], held: dict[uuid.UUID, int] | None = None) -> TableSheet:
    rows = [TableWorn(table_id=TABLE, entry_id=entry_id, slots=slots) for entry_id, slots in worn]
    stock = [TableItem(table_id=TABLE, entry_id=entry_id, count=count) for entry_id, count in (held or {}).items()]
    return TableSheet(worn=rows, items=stock)


def worn_of(sheet: TableSheet) -> list[tuple[uuid.UUID, list[str]]]:
    return [(row.entry_id, row.slots) for row in sheet.worn]


@pytest.mark.parametrize(
    'slots',
    [
        [{'key': 'hand', 'name': '손'}, {'key': 'hand', 'name': '오른손'}],
        [{'key': f's{number}', 'name': '칸'} for number in range(9)],
        [{'key': 'Hand', 'name': '손'}],
    ],
)
def test_wrong_slots_are_refused(slots: list[dict]):
    with pytest.raises(ValidationError):
        Ruleset.model_validate({**SRD5.model_dump(mode='json'), 'equipment_slots': slots})


@pytest.mark.parametrize(
    'body',
    [
        {'kind': 'consumable', 'slots': ['main_hand']},
        {'slots': ['main_hand'], 'slot_count': 2},
        {'slots': ['main_hand', 'main_hand']},
    ],
)
def test_wrong_item_slots_are_refused(body: dict):
    with pytest.raises(ValidationError):
        ItemRule.model_validate({'entry_id': str(SWORD), **body})


def test_a_reward_is_not_worn():
    with pytest.raises(ValidationError):
        QuestRule.model_validate(
            {'entry_id': str(SWORD), 'reward': [{'entry_id': str(MAIL), 'count': 1, 'wear': ['body']}]}
        )


def stack(entry_id: uuid.UUID, *wear: str) -> ItemStackSnapshot:
    return ItemStackSnapshot(entry_id=entry_id, count=1, wear=list(wear))


@pytest.mark.parametrize(
    ('stacks', 'fault'),
    [
        ([stack(SWORD, 'main_hand'), stack(MAIL, 'body')], False),
        ([stack(GREATSWORD, 'main_hand', 'off_hand'), stack(MAIL)], False),
        ([stack(SWORD, 'body')], True),
        ([stack(GREATSWORD, 'main_hand')], True),
        ([stack(SWORD, 'main_hand'), stack(GREATSWORD, 'main_hand', 'off_hand')], True),
        ([stack(uuid.uuid4(), 'main_hand')], True),
        ([stack(MAIL, 'tail')], True),
    ],
)
def test_the_starting_wear_must_fit(stacks: list[ItemStackSnapshot], fault: bool):
    slot_keys = {'main_hand', 'off_hand', 'body'}
    fits = {SWORD: (HANDS, 1), GREATSWORD: (HANDS, 2), MAIL: (['body', 'tail'], 1)}

    assert wear_fault(slot_keys, fits, stacks) is fault


def test_wearing_into_a_taken_slot_takes_the_other_off():
    sheet = sheet_with((SWORD, ['main_hand']), (MAIL, ['body']))

    removed = equipment.wear(TABLE, sheet, GREATSWORD, HANDS, held=1)

    assert [row.entry_id for row in removed] == [SWORD]
    assert worn_of(sheet) == [(MAIL, ['body']), (GREATSWORD, HANDS)]


def test_wearing_the_last_one_moves_it():
    sheet = sheet_with((SWORD, ['main_hand']))

    equipment.wear(TABLE, sheet, SWORD, ['off_hand'], held=1)

    assert worn_of(sheet) == [(SWORD, ['off_hand'])]


def test_a_second_one_is_worn_beside_the_first():
    sheet = sheet_with((SWORD, ['main_hand']))

    equipment.wear(TABLE, sheet, SWORD, ['off_hand'], held=2)

    assert worn_of(sheet) == [(SWORD, ['main_hand']), (SWORD, ['off_hand'])]


def test_losing_things_takes_off_the_last_worn():
    sheet = sheet_with((SWORD, ['main_hand']), (SWORD, ['off_hand']), held={SWORD: 2})

    items.remove_items(sheet, SWORD, 1)

    assert worn_of(sheet) == [(SWORD, ['main_hand'])]


def test_losing_what_is_not_worn_keeps_the_worn():
    sheet = sheet_with((SWORD, ['main_hand']), held={SWORD: 3})

    items.remove_items(sheet, SWORD, 2)

    assert worn_of(sheet) == [(SWORD, ['main_hand'])]


def test_taking_off_an_empty_slot_does_nothing():
    sheet = sheet_with((MAIL, ['body']))

    assert equipment.take_off(sheet, 'head') is None
    assert worn_of(sheet) == [(MAIL, ['body'])]


@pytest.mark.parametrize(
    ('slots_of_item', 'count', 'slots', 'field'),
    [
        ((), 1, ['main_hand'], 'entry_id'),
        (tuple(HANDS), 1, ['body'], 'slots'),
        (tuple(HANDS), 2, ['main_hand'], 'slots'),
        (tuple(HANDS), 2, ['main_hand', 'main_hand'], 'slots'),
        (('main_hand', 'tail'), 1, ['tail'], 'slots'),
    ],
)
def test_what_does_not_fit_the_rules_is_refused(slots_of_item, count: int, slots: list[str], field: str):
    with pytest.raises(TableOptionError) as raised:
        equipment.require_fits(SRD5, slots_of_item, count, slots)

    assert raised.value.field == field


def test_the_worn_are_shown_in_the_order_of_the_slots():
    sheet = sheet_with((MAIL, ['body']), (GREATSWORD, ['off_hand', 'main_hand']))

    ordered = equipment.in_slot_order(sheet.worn, SRD5)

    assert [row.entry_id for row in ordered] == [GREATSWORD, MAIL]
    assert equipment.slot_names(SRD5, ['main_hand', 'body', 'wings']) == ['주손', '몸', 'wings']


def test_the_starting_wear_is_put_on():
    snapshot = SimpleNamespace(
        starting_items=[stack(SWORD, 'main_hand'), stack(MAIL)],
        pregens=[SimpleNamespace(items=[stack(MAIL, 'body')])],
    )
    sheet = sheet_with()

    equipment.dress(TABLE, sheet, snapshot, 0)

    assert worn_of(sheet) == [(SWORD, ['main_hand']), (MAIL, ['body'])]


def test_an_old_snapshot_has_no_slots():
    rules = {key: value for key, value in SRD5.model_dump(mode='json').items() if key != 'equipment_slots'}
    document = {
        'format': 46,
        'rulebook': {'id': 'r', 'title': '룰북', 'gm_guide': '', 'rules': rules},
        'items': [{'entry_id': str(SWORD), 'kind': 'gear'}],
        'starting_items': [{'entry_id': str(SWORD), 'count': 1}],
        'pregens': [
            {'name': '검사', 'description': '', 'sheet': SHEET, 'items': [{'entry_id': str(MAIL), 'count': 1}]}
        ],
        'quests': [{'entry_id': str(MAIL), 'reward': [{'entry_id': str(SWORD), 'count': 1}]}],
    }

    upgraded = upgrade_from_46(document)

    assert upgraded['format'] == 47
    assert upgraded['rulebook']['rules']['equipment_slots'] == []
    assert (upgraded['items'][0]['slots'], upgraded['items'][0]['slot_count']) == ([], 1)
    assert upgraded['starting_items'][0]['wear'] == []
    assert upgraded['pregens'][0]['items'][0]['wear'] == []
    assert upgraded['quests'][0]['reward'][0]['wear'] == []
    assert 'equipment_slots' not in document['rulebook']['rules']
    assert UPGRADES[46] is upgrade_from_46


def test_the_worn_line():
    move = Move(
        character_name='기사',
        content='살핀다.',
        worn=[WornNote('대검', ['주손', '보조손']), WornNote('사슬 갑옷', ['몸'])],
    )

    assert describe_move(move) == '기사: 살핀다. [착용: 대검(주손·보조손), 사슬 갑옷(몸)]'


def test_a_change_is_written_with_the_slot_names():
    payload = {'character_name': '기사', 'change': 'take_off', 'name': '대검', 'slots': HANDS}
    labels = Labels(slots={'main_hand': '주손', 'off_hand': '보조손'})

    assert '기사: 대검 벗음 (주손·보조손)' in render_event(
        TableEvent(type=EventType.EQUIPMENT_CHANGED, payload=payload), labels
    )
