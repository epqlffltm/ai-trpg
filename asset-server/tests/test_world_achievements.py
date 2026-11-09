# asset-server/tests/test_world_achievements.py

"""
세계관의 업적(판의 형식 9, docs/architecture/achievements.md 의 "story")을 검증한다. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 업적을 적어 게시하면 판(형식 9)에 그대로 굳는다. 고치기(PATCH)로 업적만 바꿀 수 있다
  - 모양만으로 아는 것은 저장할 때 422 다. id 가 겹친다, 받는 조건이 없다, 이름이 비거나 길다, 받는 법이 길다, 51개다
  - 업적의 그림은 내가 올린 것만 붙인다(422 image_not_owned). 게시하면 판의 그림으로 적힌다(공개 세계관이면 남이 본다)
  - 받는 조건은 다른 조건과 같이 게시할 때 본다. 없는 장소, 인물, 엔딩, 장을 가리키면 게시하지 못한다
  - 공개 소개에 판의 차례로 실린다. 숨긴 업적은 이름, 받는 법, 그림이 null 이다. 조건은 싣지 않는다
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from app.worlds.documents import DOCUMENT_FORMAT
from app.worlds.models import WorldImageUse
from tests.images import own_image
from tests.worlds import OTHER, OWNER, WORLDS_URL, bearer, character, check, create_world, full_world, publish

pytestmark = pytest.mark.usefixtures('clean_tables')

LISTINGS_URL = f'{API_PREFIX}/listings/worlds'
REACH_LIBRARY = {'kind': 'reach_place', 'target': 'library'}


@pytest.fixture
def owner(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OWNER)


def achievement(achievement_id: str, *items: dict, **fields) -> dict:
    """업적 하나. 조건은 items 다."""
    return {
        'id': achievement_id,
        'name': f'{achievement_id} 업적',
        'description': f'{achievement_id} 을 했다',
        'when': {'match': 'all', 'items': list(items)},
        **fields,
    }


async def body_with(client: AsyncClient, headers: dict, **fields) -> dict:
    ari, beo = await character(client, headers, '아리'), await character(client, headers, '버')
    return {**full_world(ari['id'], beo['id']), **fields}


async def test_achievements_are_frozen_in_a_format_nine_version(client: AsyncClient, owner: dict):
    achievements = [achievement('library', REACH_LIBRARY), achievement('secret', REACH_LIBRARY, hidden=True)]
    world = await create_world(client, owner, await body_with(client, owner, achievements=achievements))

    response = await publish(client, owner, world)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    document = response.json()['document']
    assert document['format'] == DOCUMENT_FORMAT >= 9
    assert document['achievements'] == [
        {
            'id': 'library',
            'name': 'library 업적',
            'description': 'library 을 했다',
            'hidden': False,
            'image_id': None,
            'when': {
                'match': 'all',
                'items': [{'kind': 'reach_place', 'target': 'library', 'value': None, 'count': 1}],
            },
        },
        {
            'id': 'secret',
            'name': 'secret 업적',
            'description': 'secret 을 했다',
            'hidden': True,
            'image_id': None,
            'when': {
                'match': 'all',
                'items': [{'kind': 'reach_place', 'target': 'library', 'value': None, 'count': 1}],
            },
        },
    ]


async def test_achievements_can_be_patched_alone(client: AsyncClient, owner: dict):
    world = await create_world(client, owner, await body_with(client, owner))
    assert world['achievements'] == []

    response = await client.patch(
        f'{WORLDS_URL}/{world["id"]}', json={'achievements': [achievement('library', REACH_LIBRARY)]}, headers=owner
    )

    assert response.status_code == status.HTTP_200_OK, response.text
    assert [entry['id'] for entry in response.json()['achievements']] == ['library']
    assert response.json()['events'] == world['events']


@pytest.mark.parametrize(
    'achievements',
    [
        [achievement('library', REACH_LIBRARY), achievement('library', REACH_LIBRARY)],
        [achievement('library')],
        [{**achievement('library', REACH_LIBRARY), 'name': ' '}],
        [{**achievement('library', REACH_LIBRARY), 'name': '가' * 41}],
        [{**achievement('library', REACH_LIBRARY), 'description': '가' * 201}],
        [achievement(f'a{index}', REACH_LIBRARY) for index in range(51)],
    ],
    ids=['repeated-id', 'no-condition', 'blank-name', 'long-name', 'long-description', 'too-many'],
)
async def test_shapes_known_without_the_rest_are_refused_on_save(client: AsyncClient, owner: dict, achievements: list):
    response = await client.post(
        WORLDS_URL, json=await body_with(client, owner, achievements=achievements), headers=owner
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_achievement_pictures_must_be_mine_and_are_recorded(
    client: AsyncClient, owner: dict, session: AsyncSession
):
    theirs, mine = await own_image(session, OTHER), await own_image(session, OWNER)
    stolen = await client.post(
        WORLDS_URL,
        json=await body_with(client, owner, achievements=[achievement('library', REACH_LIBRARY, image_id=theirs)]),
        headers=owner,
    )
    assert (stolen.status_code, stolen.json()['code']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'image_not_owned')
    world = await create_world(client, owner, await body_with(client, owner))
    patched = await client.patch(
        f'{WORLDS_URL}/{world["id"]}',
        json={'achievements': [achievement('library', REACH_LIBRARY, image_id=theirs)]},
        headers=owner,
    )
    assert patched.json()['code'] == 'image_not_owned'

    await client.patch(
        f'{WORLDS_URL}/{world["id"]}',
        json={'achievements': [achievement('library', REACH_LIBRARY, image_id=mine)]},
        headers=owner,
    )
    version = (await publish(client, owner, world)).json()

    used = await session.scalars(
        select(WorldImageUse.image_id).where(WorldImageUse.version_id == uuid.UUID(version['id']))
    )
    assert mine in {str(image_id) for image_id in used}


@pytest.mark.parametrize(
    ('item', 'problem'),
    [
        ({'kind': 'reach_place', 'target': 'moon'}, 'place_missing'),
        ({'kind': 'accompanied', 'target': 'ghost'}, 'cast_target_missing'),
        ({'kind': 'ending_seen', 'target': 'ghost'}, 'ending_target_missing'),
        ({'kind': 'chapter_at_least', 'target': 'ghost'}, 'chapter_target_missing'),
    ],
)
async def test_conditions_that_point_at_nothing_block_publishing(
    client: AsyncClient, owner: dict, item: dict, problem: str
):
    world = await create_world(client, owner, await body_with(client, owner, achievements=[achievement('a', item)]))

    checked = await check(client, owner, world)
    response = await publish(client, owner, world)

    assert problem in checked['problems']
    assert response.status_code == status.HTTP_409_CONFLICT


async def test_the_public_intro_lists_achievements_and_veils_the_hidden(
    client: AsyncClient, owner: dict, session: AsyncSession
):
    picture = await own_image(session, OWNER)
    achievements = [
        achievement('library', REACH_LIBRARY, image_id=picture),
        achievement('secret', REACH_LIBRARY, hidden=True, image_id=picture),
    ]
    world = await create_world(client, owner, await body_with(client, owner, achievements=achievements))
    await client.patch(f'{WORLDS_URL}/{world["id"]}', json={'visibility': 'public'}, headers=owner)
    assert (await publish(client, owner, world)).status_code == status.HTTP_201_CREATED

    detail = (await client.get(f'{LISTINGS_URL}/{world["id"]}')).json()

    assert detail['achievements'] == [
        {
            'id': 'library',
            'hidden': False,
            'name': 'library 업적',
            'description': 'library 을 했다',
            'image_id': picture,
        },
        {'id': 'secret', 'hidden': True, 'name': None, 'description': None, 'image_id': None},
    ]
