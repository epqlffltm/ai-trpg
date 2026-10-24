# asset-server/tests/test_world_endings.py

"""
세계관의 고백과 엔딩(#591, 판의 형식 3)을 검증한다. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 판에 인물의 고백과 엔딩이 적은 차례대로 굳는다. 형식 2 의 판도 읽힌다(고백과 엔딩이 없다)
  - 칸의 검사(422): 기한 말고는 엔딩의 시작에 target 을 적고 기한은 적지 않는다, 엔딩의 id 는 하나씩,
    고백의 실패에 내려가는 값(0~100)과 다시 못 하는 날(1~30)
  - 막는 것: 쓰일 수 있는 시작(고백 성공, 끝내는 고백 실패, 기한, 엔딩에 적은 시작)마다
    조건이 빈 엔딩이 없다(ending_missing).
    고백의 단계가 그 인물에 없다(stage_missing). 엔딩의 시작이나 장면이 없는 인물, 없는 이벤트를 가리킨다
  - 알리는 것(ending_unreachable): 기한이 없는데 기한의 엔딩, 고백할 수 없는 인물의 고백 엔딩,
    실패해도 계속하는 인물의 실패 엔딩, 같은 시작의 조건이 빈 엔딩 뒤에 적은 엔딩
"""

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey

from app.worlds.documents import DOCUMENT_FORMAT, WorldDocument
from tests.worlds import (
    ARI_CONFESSION,
    ARI_ENDING,
    OWNER,
    SOLO_ENDING,
    WORLDS_URL,
    bearer,
    character,
    check,
    create_world,
    full_world,
    publish,
)

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def owner(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OWNER)


async def world_with(client: AsyncClient, headers: dict, confession: dict | None = ARI_CONFESSION, **fields) -> dict:
    """full_world 에 아리의 고백을 바꿔 넣고 칸을 덮어쓴 세계관."""
    ari, beo = await character(client, headers, '아리'), await character(client, headers, '버')
    body = {**full_world(ari['id'], beo['id']), **fields}
    body['cast'][0]['confession'] = confession
    return await create_world(client, headers, body)


def ending(ending_id: str, kind: str, target: str | None = None, *items: dict) -> dict:
    """그 시작의 엔딩. 조건은 items 다."""
    trigger = {'kind': kind, 'target': target} if target is not None else {'kind': kind}
    return {
        'id': ending_id,
        'name': ending_id,
        'trigger': trigger,
        'when': {'items': list(items)},
        'scene': {'text': f'{ending_id} 의 장면.'},
    }


LOVER = {'kind': 'affection_at_least', 'target': 'ari', 'value': '연인'}


# --- 판 ---


async def test_confessions_and_endings_are_frozen_in_order(client: AsyncClient, owner: dict):
    world = await world_with(client, owner)

    document = (await publish(client, owner, world)).json()['document']

    assert document['format'] == DOCUMENT_FORMAT
    assert document['cast'][0]['confession'] == {
        'stage': '친함',
        'when': {'match': 'all', 'items': []},
        'on_fail': 'continue',
        'fail_drop': 10,
        'cooldown_days': 1,
    }
    assert document['cast'][1]['confession'] is None
    assert [item['id'] for item in document['endings']] == ['ari-end', 'solo']
    assert document['endings'][0]['trigger'] == {'kind': 'confess_success', 'target': 'ari'}
    assert document['endings'][1]['trigger'] == {'kind': 'deadline', 'target': None}
    assert (document['endings'][0]['unlock'], document['endings'][0]['hint']) == (
        True,
        '도서관의 단골에게 마음을 전해 보자.',
    )


def test_a_format_two_version_reads_without_endings():
    old = {
        'format': 2,
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
        'events': [],
    }

    assert WorldDocument.model_validate(old).endings == []


# --- 칸의 검사 ---


@pytest.mark.parametrize(
    'body',
    [
        {'endings': [ending('x', 'deadline', 'ari')]},
        {'endings': [ending('x', 'confess_success')]},
        {'endings': [ending('x', 'event')]},
        {'endings': [ending('x', 'deadline'), ending('x', 'deadline')]},
    ],
)
async def test_bad_endings_are_rejected(client: AsyncClient, owner: dict, body: dict):
    response = await client.post(WORLDS_URL, json={'name': '여', **body}, headers=owner)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    'confession',
    [
        {'stage': '친함', 'fail_drop': 101},
        {'stage': '친함', 'cooldown_days': 0},
        {'stage': '친함', 'cooldown_days': 31},
    ],
)
async def test_bad_confessions_are_rejected(client: AsyncClient, owner: dict, confession: dict):
    ari = await character(client, owner, '아리')
    cast = [
        {
            'id': 'ari',
            'character_id': ari['id'],
            'affection': {'stages': [{'name': '친함', 'at': 0}]},
            'confession': confession,
        }
    ]

    response = await client.post(WORLDS_URL, json={'name': '여', 'cast': cast}, headers=owner)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 막는 것: 엔딩의 빠짐 ---


@pytest.mark.parametrize(
    ('confession', 'endings'),
    [
        # 아리에게 고백할 수 있는데 성공의 엔딩이 없다
        (ARI_CONFESSION, [SOLO_ENDING]),
        # 성공의 엔딩이 조건이 있는 것뿐이다(연인일 때만)
        (ARI_CONFESSION, [ending('lover', 'confess_success', 'ari', LOVER), SOLO_ENDING]),
        # 실패하면 끝내는데 실패의 엔딩이 없다
        ({**ARI_CONFESSION, 'on_fail': 'end'}, [ARI_ENDING, SOLO_ENDING]),
        # 기한이 있는데 기한의 엔딩이 없다
        (ARI_CONFESSION, [ARI_ENDING]),
        # 이벤트의 엔딩을 적었는데 조건이 빈 것이 없다
        (ARI_CONFESSION, [ARI_ENDING, SOLO_ENDING, ending('met', 'event', 'meet', LOVER)]),
    ],
)
async def test_a_trigger_without_a_sure_ending_blocks(
    client: AsyncClient, owner: dict, confession: dict, endings: list
):
    world = await world_with(client, owner, confession, endings=endings)

    checked = await check(client, owner, world)

    assert checked['problems'] == ['ending_missing']
    assert (await publish(client, owner, world)).status_code == status.HTTP_409_CONFLICT


async def test_a_conditional_ending_before_the_sure_one_is_fine(client: AsyncClient, owner: dict):
    endings = [ending('lover', 'confess_success', 'ari', LOVER), ARI_ENDING, SOLO_ENDING]
    world = await world_with(client, owner, endings=endings)

    checked = await check(client, owner, world)

    assert (checked['ready'], checked['problems'], checked['warnings']) == (True, [], ['place_unreachable'])


async def test_a_world_without_confessions_or_deadline_needs_no_ending(client: AsyncClient, owner: dict):
    world = await world_with(client, owner, None, deadline_days=None, endings=[])

    assert (await check(client, owner, world))['problems'] == []


@pytest.mark.parametrize(
    ('change', 'problem'),
    [
        ({'confession': {'stage': '원수'}}, 'stage_missing'),
        ({'endings': [ARI_ENDING, SOLO_ENDING, ending('x', 'confess_success', 'nobody')]}, 'cast_target_missing'),
        ({'endings': [ARI_ENDING, SOLO_ENDING, ending('x', 'event', 'ghost')]}, 'event_missing'),
    ],
)
async def test_confessions_and_endings_pointing_at_nothing_block(
    client: AsyncClient, owner: dict, change: dict, problem: str
):
    confession = change.pop('confession', ARI_CONFESSION)
    world = await world_with(client, owner, confession, **change)

    assert problem in (await check(client, owner, world))['problems']


async def test_an_ending_scene_with_someone_unknown_blocks(client: AsyncClient, owner: dict):
    stranger = {**ARI_ENDING, 'scene': {'text': '누군가 온다.', 'cast': ['nobody']}}
    world = await world_with(client, owner, endings=[stranger, SOLO_ENDING])

    assert (await check(client, owner, world))['problems'] == ['cast_target_missing']


# --- 알리는 것 ---


@pytest.mark.parametrize(
    ('confession', 'fields'),
    [
        # 기한이 없는데 기한의 엔딩
        (ARI_CONFESSION, {'deadline_days': None}),
        # 고백할 수 없는 버의 고백 엔딩
        (ARI_CONFESSION, {'endings': [ARI_ENDING, SOLO_ENDING, ending('beo', 'confess_success', 'beo')]}),
        # 실패해도 계속하는 아리의 실패 엔딩
        (ARI_CONFESSION, {'endings': [ARI_ENDING, SOLO_ENDING, ending('sad', 'confess_fail', 'ari')]}),
        # 같은 시작의 조건이 빈 엔딩 뒤에 적은 엔딩
        (ARI_CONFESSION, {'endings': [ARI_ENDING, ending('late', 'confess_success', 'ari', LOVER), SOLO_ENDING]}),
        # 열릴 수 없는 이벤트의 엔딩(이벤트의 경고도 함께다)
        (
            ARI_CONFESSION,
            {
                'events': [
                    {
                        'id': 'loop',
                        'name': '돌기',
                        'when': {'items': [{'kind': 'event_seen', 'target': 'loop'}]},
                        'scene': {'text': '돈다.', 'cast': ['beo']},
                    }
                ],
                'endings': [ARI_ENDING, SOLO_ENDING, ending('looped', 'event', 'loop')],
            },
        ),
    ],
)
async def test_endings_that_are_never_chosen_are_only_warned(
    client: AsyncClient, owner: dict, confession: dict, fields: dict
):
    world = await world_with(client, owner, confession, **fields)

    checked = await check(client, owner, world)

    assert checked['problems'] == []
    assert 'ending_unreachable' in checked['warnings']
    assert (await publish(client, owner, world)).status_code == status.HTTP_201_CREATED


async def test_a_failure_ending_for_someone_who_ends_on_failure_is_reachable(client: AsyncClient, owner: dict):
    endings = [ARI_ENDING, ending('sad', 'confess_fail', 'ari'), SOLO_ENDING]
    world = await world_with(client, owner, {**ARI_CONFESSION, 'on_fail': 'end'}, endings=endings)

    assert (await check(client, owner, world))['warnings'] == ['place_unreachable']
