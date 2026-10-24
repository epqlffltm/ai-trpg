# asset-server/tests/test_world_events.py

"""
세계관의 이벤트(#591, 판의 형식 2)를 검증한다. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 이벤트는 판에 적은 차례대로 굳는다. 장면 지시, 열릴 때의 효과, 선택지와 그 효과가 들어간다. 형식 1 의 판도 읽힌다
  - 칸의 검사(422): 효과는 종류마다 amount 를 맞게 적는다(호감도는 0 이 아님, 물건은 1~99, 나머지는 없음),
    일러스트가 없으면 해금 대상이 아니다, 장면의 인물과 선택지와 이벤트의 id 는 하나씩, 선택지는 셋까지
  - 막는 것: 없는 이벤트를 봤다(event_missing), 장면과 효과가 없는 인물, 물건, 장소를 가리킨다
  - 알리는 것: 열릴 수 없는 이벤트(자기를 봐야 열린다, 열릴 수 없는 이벤트를 봐야 열린다, 기한 뒤의 날,
    겹치지 않는 날짜), 어디에도 나오지 않는 인물. "하나라도"는 하나만 맞을 수 있으면 열린다
  - 이벤트의 일러스트는 자기 그림이어야 하고, 판에 쓰인 그림으로 적힌다
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.worlds.documents import DOCUMENT_FORMAT, WorldDocument
from app.worlds.models import WorldImageUse
from tests.images import own_image
from tests.worlds import (
    ARI_ENDING,
    MEET,
    OTHER,
    OWNER,
    WORLDS_URL,
    bearer,
    character,
    check,
    create_world,
    full_world,
    member,
    publish,
)

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def owner(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OWNER)


async def world_with(client: AsyncClient, headers: dict, **fields) -> dict:
    ari, beo = await character(client, headers, '아리'), await character(client, headers, '버')
    return await create_world(client, headers, {**full_world(ari['id'], beo['id']), **fields})


def event(event_id: str, *items: dict, match: str = 'all', **fields) -> dict:
    """장면 지시만 있는 이벤트. 조건은 items 다."""
    return {
        'id': event_id,
        'name': event_id,
        'when': {'match': match, 'items': list(items)},
        'scene': {'text': f'{event_id} 의 장면.'},
        **fields,
    }


def seen(event_id: str) -> dict:
    return {'kind': 'event_seen', 'target': event_id}


def day_at_least(day: int) -> dict:
    return {'kind': 'day_at_least', 'count': day}


# --- 판 ---


async def test_events_are_frozen_in_order_with_their_choices(client: AsyncClient, owner: dict):
    world = await world_with(client, owner)

    document = (await publish(client, owner, world)).json()['document']

    meet, hint = document['events']
    assert (document['format'], [meet['id'], hint['id']]) == (DOCUMENT_FORMAT, ['meet', 'hint'])
    assert meet['scene'] == {
        'text': '도서관 구석에서 버가 책을 떨어뜨린다.',
        'cast': ['beo', 'ari'],
        'image_id': None,
        'collectible': False,
    }
    assert meet['on_open'] == [{'kind': 'affection', 'target': 'beo', 'amount': 3}]
    assert [choice['id'] for choice in meet['choices']] == ['help', 'walk']
    assert meet['choices'][1]['effects'][0] == {'kind': 'accompany_start', 'target': 'beo', 'amount': None}
    assert (hint['repeat'], hint['when']['items'][0]) == (
        False,
        {'kind': 'event_seen', 'target': 'meet', 'value': None, 'count': 1},
    )


def test_a_format_one_version_reads_without_events():
    old = {
        'format': 1,
        'name': '옛 판',
        'intro_html': '',
        'tags': [],
        'rating': 'all',
        'image_id': None,
        'slots': [{'id': 'day', 'name': '낮', 'start_hour': 9}],
        'start_slot': 'day',
        'deadline_days': None,
        'after_ending': 'end',
        'places': [],
        'paths': [],
        'start_place': 'home',
        'items': [],
        'start_items': [],
        'cast': [],
        'lorebooks': [],
    }

    assert WorldDocument.model_validate(old).events == []


# --- 칸의 검사 ---


@pytest.mark.parametrize(
    'effect',
    [
        {'kind': 'affection', 'target': 'beo'},
        {'kind': 'affection', 'target': 'beo', 'amount': 0},
        {'kind': 'affection', 'target': 'beo', 'amount': 101},
        {'kind': 'give_item', 'target': 'rose'},
        {'kind': 'take_item', 'target': 'rose', 'amount': -1},
        {'kind': 'give_item', 'target': 'rose', 'amount': 100},
        {'kind': 'accompany_end', 'target': 'beo', 'amount': 1},
        {'kind': 'move_to', 'target': 'school', 'amount': 2},
    ],
)
async def test_an_effect_writes_the_amount_its_kind_needs(client: AsyncClient, owner: dict, effect: dict):
    body = {'name': '여', 'events': [event('x', on_open=[effect])]}

    response = await client.post(WORLDS_URL, json=body, headers=owner)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    'events',
    [
        # 일러스트 없이 해금 대상
        [event('x', scene={'text': '장면', 'collectible': True})],
        # 장면에 같은 인물 둘, 다섯 명
        [event('x', scene={'text': '장면', 'cast': ['a', 'a']})],
        [event('x', scene={'text': '장면', 'cast': ['a', 'b', 'c', 'd', 'e']})],
        # 장면 지시가 비었다
        [event('x', scene={'text': ' '})],
        # 같은 선택지 id, 선택지 넷
        [event('x', choices=[{'id': 'a', 'text': '가'}, {'id': 'a', 'text': '나'}])],
        [event('x', choices=[{'id': key, 'text': key} for key in 'abcd'])],
        # 같은 이벤트 id
        [event('x'), event('x')],
    ],
)
async def test_bad_events_are_rejected(client: AsyncClient, owner: dict, events: list):
    response = await client.post(WORLDS_URL, json={'name': '여', 'events': events}, headers=owner)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 막는 것 ---


@pytest.mark.parametrize(
    ('broken', 'problem'),
    [
        (event('x', seen('ghost')), 'event_missing'),
        (event('x', scene={'text': '장면', 'cast': ['nobody']}), 'cast_target_missing'),
        (event('x', on_open=[{'kind': 'affection', 'target': 'nobody', 'amount': 1}]), 'cast_target_missing'),
        (event('x', on_open=[{'kind': 'take_item', 'target': 'ghost', 'amount': 1}]), 'item_missing'),
        (
            event('x', choices=[{'id': 'go', 'text': '간다', 'effects': [{'kind': 'move_to', 'target': 'moon'}]}]),
            'place_missing',
        ),
    ],
)
async def test_an_event_pointing_at_nothing_blocks(client: AsyncClient, owner: dict, broken: dict, problem: str):
    world = await world_with(client, owner, events=[MEET, broken])

    checked = await check(client, owner, world)
    response = await publish(client, owner, world)

    assert checked['problems'] == [problem]
    assert response.status_code == status.HTTP_409_CONFLICT


# --- 알리는 것 ---


@pytest.mark.parametrize(
    'events',
    [
        # 자기를 봐야 열린다
        [MEET, event('loop', seen('loop'))],
        # 서로를 봐야 열린다
        [MEET, event('a', seen('b')), event('b', seen('a'))],
        # 기한(30일) 뒤의 날을 기다린다. 그것을 봐야 열리는 이벤트도 열리지 않는다
        [MEET, event('late', day_at_least(31)), event('after', seen('late'))],
        # 5일째 이상이면서 3일째 이하
        [MEET, event('never', day_at_least(5), {'kind': 'day_at_most', 'count': 3})],
    ],
)
async def test_events_that_can_never_open_are_only_warned(client: AsyncClient, owner: dict, events: list):
    world = await world_with(client, owner, events=events)

    checked = await check(client, owner, world)
    response = await publish(client, owner, world)

    assert checked['warnings'] == ['place_unreachable', 'event_unreachable']
    assert response.status_code == status.HTTP_201_CREATED


async def test_any_opens_when_one_condition_can_hold(client: AsyncClient, owner: dict):
    events = [MEET, event('either', seen('missing-later'), day_at_least(2), match='any'), event('missing-later')]
    world = await world_with(client, owner, events=events)

    assert (await check(client, owner, world))['warnings'] == ['place_unreachable']


async def test_a_chain_of_events_opens_in_turn(client: AsyncClient, owner: dict):
    events = [MEET, event('second', seen('meet')), event('third', seen('second'), day_at_least(30))]
    # 기한이 없으니 기한의 엔딩도 뺀다
    world = await world_with(client, owner, events=events, deadline_days=None, endings=[ARI_ENDING])

    assert (await check(client, owner, world))['warnings'] == ['place_unreachable']


async def test_someone_who_never_appears_is_warned(client: AsyncClient, owner: dict):
    ari, beo, cyan = [await character(client, owner, name) for name in ('아리', '버', '시안')]
    body = full_world(ari['id'], beo['id'])
    body['cast'].append(member('cyan', cyan['id']))
    world = await create_world(client, owner, body)

    assert (await check(client, owner, world))['warnings'] == ['place_unreachable', 'cast_never_present']


async def test_starting_company_counts_as_appearing(client: AsyncClient, owner: dict):
    ari, beo, cyan = [await character(client, owner, name) for name in ('아리', '버', '시안')]
    body = full_world(ari['id'], beo['id'])
    body['cast'].append(member('cyan', cyan['id']))
    body['events'].append(event('join', on_open=[{'kind': 'accompany_start', 'target': 'cyan'}]))
    world = await create_world(client, owner, body)

    assert (await check(client, owner, world))['warnings'] == ['place_unreachable']


# --- 그림 ---


async def test_an_event_illustration_is_mine_and_recorded(client: AsyncClient, owner: dict, session: AsyncSession):
    picture = await own_image(session, OWNER)
    theirs = await own_image(session, OTHER)
    collectible = {**MEET, 'scene': {**MEET['scene'], 'image_id': picture, 'collectible': True}}
    stolen = {**MEET, 'scene': {**MEET['scene'], 'image_id': theirs}}

    rejected = await client.post(WORLDS_URL, json={'name': '여', 'events': [stolen]}, headers=owner)
    world = await world_with(client, owner, events=[collectible])
    version = (await publish(client, owner, world)).json()

    used = await session.scalars(
        select(WorldImageUse.image_id).where(WorldImageUse.version_id == uuid.UUID(version['id']))
    )
    assert (rejected.status_code, rejected.json()['code']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'image_not_owned')
    assert version['document']['events'][0]['scene']['collectible'] is True
    assert {str(image_id) for image_id in used} == {picture}
