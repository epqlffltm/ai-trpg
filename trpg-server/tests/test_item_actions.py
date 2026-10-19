# trpg-server/tests/test_item_actions.py

"""
물건을 쓰고 건네는 행동(#202, app/rounds/item_actions.py).

넷을 본다.
  - 받기: 선언에 붙일 때 판의 물건인지, 쓸 수 있는 물건인지, 가지고 있는지, 대상이 맞는지.
  - 닫힐 때: 소모품이 하나 줄고, 회복하는 것이면 대상이 회복한다. 건네면 옮겨진다.
    그사이에 사정이 바뀌었으면(빼앗겼다, 대상이 죽었다, 받는 쪽이 가득 찼다) 아무것도 바뀌지 않고 까닭을 적는다.
  - 기록: 결과가 선언과 이벤트에 남는다. 회복은 HP 의 변화로 잇는다.
  - 서술: 서술자가 쓰고 건넨 결과를 받는다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.dice import ScriptedDice
from app.main import API_PREFIX
from app.rounds.move_lines import describe_item_action
from app.rounds.narrator import Impact, ItemActionNote
from tests.narration_model import asset_body
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
STRANGER = uuid.UUID('99999999-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'

LOOK = '주위를 살핀다.'


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장의 머리말. 직접 만든 캐릭터(기사)를 한다. 시작 소지품(밧줄 하나)만 가진다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """프리젠(약사)을 고르는 사람의 머리말. 밧줄 하나, 물약 둘, 연막탄 하나를 가진다."""
    return bearer(signing_key, FRIEND)


async def post(client: AsyncClient, url: str, headers: dict[str, str], **body) -> dict:
    response = await client.post(url, json=asset_body(url, body), headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def table_url(table: dict, path: str = '') -> str:
    return f'{TABLES_URL}/{table["id"]}{path}'


@pytest.fixture
async def lore(client: AsyncClient, me: dict[str, str]) -> dict:
    """물건 넷(치유 물약, 연막탄, 밧줄, 등불)과 인물 하나."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='모험의 물건들')
    url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'

    async def entry(name: str, kind: str) -> dict:
        return await post(client, url, me, name=name, keywords=[], content=f'{name}의 설명', kind=kind)

    return {
        'lorebook': lorebook,
        'potion': await entry('치유 물약', 'item'),
        'smoke': await entry('연막탄', 'item'),
        'rope': await entry('밧줄', 'item'),
        'lamp': await entry('등불', 'item'),
        'lady': await entry('악역영애', 'person'),
    }


@pytest.fixture
async def table(client: AsyncClient, me: dict, friend: dict, lore: dict) -> dict:
    """
    둘이 앉아 시작한 테이블. 첫 라운드가 열려 있다.

    물약은 가벼움(1d4)만큼 회복하는 소모품, 연막탄은 회복하지 않는 소모품, 밧줄은 장비, 등불은 규칙이 없다(장비).
    """
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북')
    body = {
        'title': '물건의 모험',
        'rulebook_id': rulebook['id'],
        'openings': ['시장이다.'],
        'default_sheet': SHEET,
        'default_npc_sheet': SHEET,
        'lorebook_ids': [lore['lorebook']['id']],
        'items': [
            {'entry_id': lore['potion']['id'], 'kind': 'consumable', 'heals': 'light'},
            {'entry_id': lore['smoke']['id'], 'kind': 'consumable'},
            {'entry_id': lore['rope']['id'], 'kind': 'gear'},
        ],
        'starting_items': [{'entry_id': lore['rope']['id'], 'count': 1}],
        'pregens': [
            {
                'name': '약사',
                'sheet': SHEET,
                'items': [
                    {'entry_id': lore['potion']['id'], 'count': 2},
                    {'entry_id': lore['smoke']['id'], 'count': 1},
                ],
            },
        ],
    }
    scenario = await post(client, SCENARIOS_URL, me, **body)
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)
    created = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=2)
    await client.post(f'{TABLES_URL}/join', json={'invite_code': created['invite_code']}, headers=friend)
    await client.put(table_url(created, '/character'), json={'name': '기사'}, headers=me)
    await client.put(table_url(created, '/character'), json={'pregen_index': 0}, headers=friend)
    started = await client.post(table_url(created, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


def use(entry: dict, target: uuid.UUID | None = None) -> dict:
    action = {'kind': 'use', 'item': entry['id']}
    return action if target is None else {**action, 'target': str(target)}


def give(entry: dict, target: uuid.UUID | str, count: int = 1) -> dict:
    return {'kind': 'give', 'item': entry['id'], 'count': count, 'target': str(target)}


async def declare(client: AsyncClient, headers: dict, table: dict, action: dict | None = None, content: str = LOOK):
    """선언을 내는 요청. 응답을 그대로 돌려준다."""
    body = {'content': content} if action is None else {'content': content, 'action': action}
    return await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=headers)


async def declared(client: AsyncClient, headers: dict, table: dict, action: dict | None = None) -> None:
    response = await declare(client, headers, table, action)
    assert response.status_code == status.HTTP_200_OK, response.text


def held(table: dict, user_id: uuid.UUID) -> list[tuple[str, int]]:
    member = next(member for member in table['members'] if member['user_id'] == str(user_id))
    return [(item['name'], item['count']) for item in member['sheet']['items']]


def hp_of(table: dict, user_id: uuid.UUID) -> int:
    member = next(member for member in table['members'] if member['user_id'] == str(user_id))
    return member['sheet']['hp']


async def read_table(client: AsyncClient, headers: dict, table: dict) -> dict:
    return (await client.get(table_url(table), headers=headers)).json()


async def first_round(client: AsyncClient, headers: dict, table: dict) -> dict:
    return (await client.get(table_url(table, '/rounds/1'), headers=headers)).json()


async def events_of(client: AsyncClient, headers: dict, table: dict, kind: str) -> list[dict]:
    response = await client.get(table_url(table, '/events'), params={'limit': 100}, headers=headers)
    return [event for event in response.json()['items'] if event['type'] == kind]


async def set_hp(session: AsyncSession, user_id: uuid.UUID, hp: int) -> None:
    """서비스를 거치지 않고 그 사람의 HP 를 정한다. 다친 것과 같다."""
    await session.execute(
        text('UPDATE table_sheets SET hp = :hp WHERE user_id = :user_id'), {'hp': hp, 'user_id': user_id}
    )
    await session.commit()


async def kill(session: AsyncSession, user_id: uuid.UUID) -> None:
    """서비스를 거치지 않고 그 사람의 캐릭터를 죽인다."""
    await session.execute(
        text('UPDATE table_sheets SET hp = 0, died_at = now() WHERE user_id = :user_id'), {'user_id': user_id}
    )
    await session.commit()


def load_dice(app: FastAPI, rolls: list[int]) -> None:
    app.state.dice = ScriptedDice(rolls)


# --- 쓰기 ---


async def test_a_potion_heals_its_user_and_is_used_up(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, table: dict, session: AsyncSession, narrated
):
    await set_hp(session, FRIEND, 2)
    load_dice(app, [3])

    await declared(client, me, table)
    await declared(client, friend, table, use(lore['potion']))
    await narrated()

    after = await read_table(client, me, table)
    assert hp_of(after, FRIEND) == 5
    assert held(after, FRIEND) == [('치유 물약', 1), ('연막탄', 1), ('밧줄', 1)]
    outcome = next(d for d in (await first_round(client, me, table))['declarations'] if d['user_id'] == str(FRIEND))
    assert outcome['outcome']['item_use'] == {
        'entry_id': lore['potion']['id'],
        'name': '치유 물약',
        'used': True,
        'reason': None,
        'target': {'user_id': str(FRIEND), 'character_name': '약사'},
        'remaining': 1,
    }
    assert (outcome['outcome']['effect']['before'], outcome['outcome']['effect']['after']) == (2, 5)


async def test_a_potion_heals_someone_else(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, table: dict, session: AsyncSession, narrated
):
    await set_hp(session, ME, 4)
    load_dice(app, [2])

    await declared(client, friend, table, use(lore['potion'], ME))
    await declared(client, me, table)
    await narrated()

    after = await read_table(client, me, table)
    assert (hp_of(after, ME), hp_of(after, FRIEND)) == (6, 10)
    second = (await client.get(table_url(table, '/rounds/current'), headers=me)).json()
    assert '약사: 주위를 살핀다. (쓴 물건: 치유 물약 → 기사) → 기사 회복 2 (HP 6/10)' in second['scene']


async def test_using_and_healing_are_recorded_in_order(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, table: dict, session: AsyncSession, narrated
):
    await set_hp(session, FRIEND, 2)
    load_dice(app, [3])

    await declared(client, me, table)
    await declared(client, friend, table, use(lore['potion']))
    await narrated()

    (used,) = await events_of(client, me, table, 'item_used')
    (healed,) = await events_of(client, me, table, 'hp_changed')
    action = next(e for e in await events_of(client, me, table, 'player_action') if e['actor_id'] == str(FRIEND))
    assert used['caused_by_sequence'] == action['sequence']
    assert healed['caused_by_sequence'] == used['sequence']
    assert used['actor_id'] is None
    assert used['payload']['used'] is True
    assert (healed['payload']['kind'], healed['payload']['after']) == ('recovery', 5)


async def test_a_consumable_that_heals_nothing_is_just_used_up(
    client: AsyncClient, me: dict, friend: dict, lore: dict, table: dict, narrated
):
    await declared(client, me, table)
    await declared(client, friend, table, use(lore['smoke']))
    await narrated()

    after = await read_table(client, me, table)
    assert held(after, FRIEND) == [('치유 물약', 2), ('밧줄', 1)]
    assert await events_of(client, me, table, 'hp_changed') == []
    second = (await client.get(table_url(table, '/rounds/current'), headers=me)).json()
    assert '약사: 주위를 살핀다. (쓴 물건: 연막탄)' in second['scene']


@pytest.mark.parametrize(
    ('entry', 'field'), [('rope', 'item'), ('lamp', 'item'), ('lady', 'item')], ids=['gear', 'no-rule', 'person']
)
async def test_only_consumables_can_be_used(
    client: AsyncClient, friend: dict, lore: dict, table: dict, entry: str, field: str
):
    response = await declare(client, friend, table, use(lore[entry]))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert field in response.text


async def test_an_unknown_thing_cannot_be_used(client: AsyncClient, friend: dict, table: dict):
    response = await declare(client, friend, table, use({'id': NO_SUCH_ID}))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_only_what_is_held_can_be_used(client: AsyncClient, me: dict, lore: dict, table: dict):
    response = await declare(client, me, table, use(lore['potion']))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert 'item_not_held' in response.text


async def test_healing_needs_someone_seated(client: AsyncClient, friend: dict, lore: dict, table: dict):
    response = await declare(client, friend, table, use(lore['potion'], STRANGER))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'target' in response.text


async def test_the_dead_are_not_healed(
    client: AsyncClient, friend: dict, lore: dict, table: dict, session: AsyncSession
):
    await kill(session, ME)

    response = await declare(client, friend, table, use(lore['potion'], ME))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert 'patient_dead' in response.text


async def test_a_consumable_that_heals_nothing_has_no_target(client: AsyncClient, friend: dict, lore: dict, table):
    response = await declare(client, friend, table, use(lore['smoke'], ME))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'target' in response.text


async def test_a_healing_use_is_saved_with_its_target(client: AsyncClient, me: dict, friend, lore: dict, table):
    await declared(client, friend, table, use(lore['potion']))

    mine = next(d for d in (await first_round(client, friend, table))['declarations'] if d['user_id'] == str(FRIEND))
    # 비워 둔 대상은 자기 자신으로 채워 저장한다
    assert mine['action'] == {'kind': 'use', 'item': lore['potion']['id'], 'target': str(FRIEND)}


async def test_what_was_taken_meanwhile_is_not_used(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, table: dict, session, narrated
):
    await set_hp(session, FRIEND, 2)
    load_dice(app, [3])
    await declared(client, friend, table, use(lore['potion']))

    # 선언한 뒤에 방장이 물약을 모두 빼앗는다
    taken = await client.delete(
        table_url(table, f'/members/{FRIEND}/items/{lore["potion"]["id"]}'), params={'count': 2}, headers=me
    )
    assert taken.status_code == status.HTTP_200_OK, taken.text
    await declared(client, me, table)
    await narrated()

    after = await read_table(client, me, table)
    assert hp_of(after, FRIEND) == 2
    (used,) = await events_of(client, me, table, 'item_used')
    assert (used['payload']['used'], used['payload']['reason'], used['payload']['remaining']) == (
        False,
        'not_held',
        0,
    )
    second = (await client.get(table_url(table, '/rounds/current'), headers=me)).json()
    assert '(쓰려던 물건: 치유 물약. 가지고 있지 않았다)' in second['scene']


async def test_a_potion_is_kept_when_its_target_is_gone(
    client: AsyncClient, me: dict, friend: dict, lore: dict, table: dict, session: AsyncSession, narrated
):
    await declared(client, friend, table, use(lore['potion'], ME))
    await kill(session, ME)

    # 캐릭터가 죽어도 방장은 방장이다. 기다리지 않고 닫는다
    closed = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    assert closed.status_code == status.HTTP_202_ACCEPTED, closed.text
    await narrated()

    after = await read_table(client, friend, table)
    assert ('치유 물약', 2) in held(after, FRIEND)
    (used,) = await events_of(client, friend, table, 'item_used')
    assert (used['payload']['used'], used['payload']['reason']) == (False, 'target_gone')


# --- 건네기 ---


async def test_giving_moves_the_thing(client: AsyncClient, me: dict, friend: dict, lore: dict, table, narrated):
    await declared(client, friend, table, give(lore['potion'], ME))
    await declared(client, me, table)
    await narrated()

    after = await read_table(client, me, table)
    assert held(after, FRIEND) == [('치유 물약', 1), ('연막탄', 1), ('밧줄', 1)]
    assert held(after, ME) == [('치유 물약', 1), ('밧줄', 1)]
    (given,) = await events_of(client, me, table, 'item_given')
    assert given['payload'] == {
        'round': 1,
        'character_name': '약사',
        'entry_id': lore['potion']['id'],
        'name': '치유 물약',
        'count': 1,
        'given': True,
        'reason': None,
        'target': {'user_id': str(ME), 'character_name': '기사'},
        'remaining': 1,
        'target_total': 1,
    }
    second = (await client.get(table_url(table, '/rounds/current'), headers=me)).json()
    assert '약사: 주위를 살핀다. (건넨 물건: 치유 물약 1개 → 기사)' in second['scene']


async def test_gear_can_be_given_too(client: AsyncClient, me: dict, friend: dict, lore: dict, table, narrated):
    await declared(client, me, table, give(lore['rope'], FRIEND))
    await declared(client, friend, table)
    await narrated()

    after = await read_table(client, me, table)
    assert (held(after, ME), ('밧줄', 2) in held(after, FRIEND)) == ([], True)


async def test_cannot_give_to_oneself(client: AsyncClient, friend: dict, lore: dict, table: dict):
    response = await declare(client, friend, table, give(lore['potion'], FRIEND))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'target' in response.text


async def test_cannot_give_to_someone_not_seated(client: AsyncClient, friend: dict, lore: dict, table: dict):
    response = await declare(client, friend, table, give(lore['potion'], STRANGER))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_cannot_give_more_than_is_held(client: AsyncClient, friend: dict, lore: dict, table: dict):
    response = await declare(client, friend, table, give(lore['potion'], ME, 3))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert 'item_not_held' in response.text


async def test_cannot_give_to_the_dead(
    client: AsyncClient, friend: dict, lore: dict, table: dict, session: AsyncSession
):
    await kill(session, ME)

    response = await declare(client, friend, table, give(lore['potion'], ME))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert 'recipient_dead' in response.text


async def test_cannot_give_to_someone_full(client: AsyncClient, me: dict, friend: dict, lore: dict, table: dict):
    await client.post(
        table_url(table, f'/members/{ME}/items'), json={'entry_id': lore['rope']['id'], 'count': 98}, headers=me
    )

    response = await declare(client, friend, table, give(lore['rope'], ME))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert 'recipient_full' in response.text


async def test_a_gift_to_someone_filled_meanwhile_stays(
    client: AsyncClient, me: dict, friend: dict, lore: dict, table: dict, narrated
):
    await declared(client, friend, table, give(lore['rope'], ME))
    # 선언한 뒤에 방장이 자기에게 밧줄을 가득 채운다
    await client.post(
        table_url(table, f'/members/{ME}/items'), json={'entry_id': lore['rope']['id'], 'count': 98}, headers=me
    )
    await declared(client, me, table)
    await narrated()

    after = await read_table(client, me, table)
    assert ('밧줄', 1) in held(after, FRIEND)
    assert held(after, ME) == [('밧줄', 99)]
    (given,) = await events_of(client, me, table, 'item_given')
    assert (given['payload']['given'], given['payload']['reason']) == (False, 'too_many')


async def test_what_was_taken_meanwhile_is_not_given(
    client: AsyncClient, me: dict, friend: dict, lore: dict, table: dict, narrated
):
    await declared(client, friend, table, give(lore['potion'], ME, 2))
    # 선언한 뒤에 방장이 물약 하나를 빼앗는다. 둘을 건넬 수 없다
    await client.delete(table_url(table, f'/members/{FRIEND}/items/{lore["potion"]["id"]}'), headers=me)
    await declared(client, me, table)
    await narrated()

    after = await read_table(client, me, table)
    assert ('치유 물약', 1) in held(after, FRIEND)
    assert held(after, ME) == [('밧줄', 1)]
    (given,) = await events_of(client, me, table, 'item_given')
    assert (given['payload']['given'], given['payload']['reason']) == (False, 'not_held')


async def test_a_gift_to_the_dead_stays(
    client: AsyncClient, me: dict, friend: dict, lore: dict, table: dict, session: AsyncSession, narrated
):
    await declared(client, friend, table, give(lore['potion'], ME))
    await kill(session, ME)

    closed = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    assert closed.status_code == status.HTTP_202_ACCEPTED, closed.text
    await narrated()

    after = await read_table(client, friend, table)
    assert ('치유 물약', 2) in held(after, FRIEND)
    (given,) = await events_of(client, friend, table, 'item_given')
    assert (given['payload']['given'], given['payload']['reason'], given['payload']['target_total']) == (
        False,
        'target_gone',
        None,
    )


@pytest.mark.parametrize('count', [0, 100])
async def test_rejects_a_bad_count(client: AsyncClient, friend: dict, lore: dict, table: dict, count: int):
    response = await declare(client, friend, table, give(lore['potion'], ME, count))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 서술의 글 ---


def test_the_lines_of_items_for_the_narrator():
    healed = Impact(kind='recovery', character_name='기사', amount=2, hp=6, max_hp=10, downed=False)

    assert describe_item_action(ItemActionNote('use', '치유 물약', 1, True)) == '(쓴 물건: 치유 물약)'
    assert (
        describe_item_action(ItemActionNote('use', '치유 물약', 1, True, target='기사', impact=healed))
        == '(쓴 물건: 치유 물약 → 기사) → 기사 회복 2 (HP 6/10)'
    )
    assert (
        describe_item_action(ItemActionNote('give', '밧줄', 2, True, target='기사')) == '(건넨 물건: 밧줄 2개 → 기사)'
    )
    assert (
        describe_item_action(ItemActionNote('give', '밧줄', 1, False, reason='too_many', target='기사'))
        == '(건네려던 물건: 밧줄 1개 → 기사. 받는 쪽이 더 가질 수 없었다)'
    )
