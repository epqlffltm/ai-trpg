# asset-server/tests/test_character_achievements.py

"""
캐릭터의 업적(판의 형식 11, docs/architecture/achievements.md 의 "chat")을 검증한다. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 업적을 적어 게시하면 판(형식 11)에 그대로 굳는다. 고치기(PATCH)로 업적만 바꿀 수 있다
  - 모양만으로 아는 것은 저장할 때 422 다. id 가 겹친다, 조건이 없다, 조건이 6개다, 칸이 종류와 맞지 않는다,
    수가 범위를 넘는다, 모르는 종류다, 이름이 비거나 길다, 받는 법이 길다, 51개다
  - 업적의 그림은 내가 올린 것만 붙인다(422 image_not_owned). 게시하면 판의 그림으로 적힌다
  - 조건이 없는 장소, 물건, 이벤트 씬, 호감도의 단계(호감도가 없는데 단계)를 가리키면 게시하지 못한다.
    보낸 말의 수는 가리키는 것이 없어 늘 된다
  - 공개 소개에는 판의 차례로 싣고 숨긴 업적은 이름, 받는 법, 그림이 null 이다. 문서의 업적은 비운다(조건이 들었다)
  - chat 이 받는 서비스 경로에는 조건까지 그대로 간다
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.documents import DOCUMENT_FORMAT
from app.images.models import ImageUse
from app.main import API_PREFIX
from tests.images import own_image
from tests.signing import signed_get

pytestmark = pytest.mark.usefixtures('clean_tables')

CHARACTERS_URL = f'{API_PREFIX}/characters'
LISTINGS_URL = f'{API_PREFIX}/listings/characters'
OPERATOR = uuid.UUID('11111111-2222-4333-8444-555555555555')
OTHER = uuid.UUID('99999999-2222-4333-8444-555555555555')
START = {'title': '비 오는 밤', 'situation': '문을 두드리는 소리가 난다.'}
CAFE = {'id': 'cafe', 'name': '카페', 'description': '', 'image_id': None, 'backgrounds': {}}
COOKIE = {'id': 'cookie', 'name': '쿠키', 'description': '', 'kind': 'thing', 'consumable': True, 'image_id': None}
AFFECTION = {'stages': [{'name': '낯섦', 'at': 0}, {'name': '연인', 'at': 70}]}
VISIT_CAFE = {'kind': 'visited_place', 'target': 'cafe'}


def achievement(achievement_id: str, *items: dict, **fields) -> dict:
    """업적 하나. 조건은 items 다."""
    return {
        'id': achievement_id,
        'name': f'{achievement_id} 업적',
        'description': f'{achievement_id} 을 했다',
        'when': {'match': 'all', 'items': list(items)},
        **fields,
    }


def frozen(item: dict) -> dict:
    """판에 굳은 조건 하나. 쓰지 않는 칸은 null 이고 count 는 1 이다."""
    return {'target': None, 'value': None, 'count': 1, **item}


@pytest.fixture
def operator(signing_key: SigningKey) -> dict:
    claims = make_access_claims(sub=str(OPERATOR))
    claims['roles'] = ['operator']
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


@pytest.fixture
async def picture(session: AsyncSession) -> str:
    return await own_image(session, OPERATOR)


async def scene_body(session: AsyncSession) -> dict:
    """카페에 가면 나오는 이벤트 씬 하나."""
    return {
        'id': 'first-date',
        'title': '첫 데이트',
        'image_id': await own_image(session, OPERATOR),
        'description': '',
        'collectible': True,
        'when': {'kind': 'reach_place', 'target': 'cafe'},
    }


async def post(client: AsyncClient, headers: dict, **fields):
    body = {
        'genre': 'romance',
        'name': '세라',
        'starts': [START],
        'places': [CAFE],
        'start_place': 'cafe',
        'items': [COOKIE],
        'affection': AFFECTION,
        **fields,
    }
    return await client.post(CHARACTERS_URL, json=body, headers=headers)


async def create(client: AsyncClient, headers: dict, **fields) -> dict:
    response = await post(client, headers, **fields)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def patch(client: AsyncClient, headers: dict, character: dict, body: dict):
    return await client.patch(f'{CHARACTERS_URL}/{character["id"]}', json=body, headers=headers)


async def publish(client: AsyncClient, headers: dict, character: dict):
    return await client.post(f'{CHARACTERS_URL}/{character["id"]}/versions', json={}, headers=headers)


async def problems(client: AsyncClient, headers: dict, character: dict) -> list[str]:
    response = await client.get(f'{CHARACTERS_URL}/{character["id"]}/publish-check', headers=headers)
    return response.json()['problems']


# --- 판에 굳는다 ---


async def test_achievements_are_frozen_in_a_format_eleven_version(
    client: AsyncClient, operator: dict, session: AsyncSession
):
    scene = await scene_body(session)
    every_kind = [
        VISIT_CAFE,
        {'kind': 'hold_item', 'target': 'cookie', 'count': 3},
        {'kind': 'received_item', 'target': 'cookie'},
        {'kind': 'affection_stage', 'value': '연인'},
        {'kind': 'scene_seen', 'target': 'first-date'},
        {'kind': 'messages_at_least', 'count': 50},
    ]
    regular = achievement('regular', *every_kind[:5])
    achievements = [
        {**regular, 'when': {'match': 'any', 'items': every_kind[:5]}},
        achievement('secret', every_kind[5], hidden=True),
    ]
    character = await create(client, operator, event_scenes=[scene], achievements=achievements)

    response = await publish(client, operator, character)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    document = response.json()['document']
    assert document['format'] == DOCUMENT_FORMAT >= 11
    assert document['achievements'] == [
        {
            'id': 'regular',
            'name': 'regular 업적',
            'description': 'regular 을 했다',
            'hidden': False,
            'image_id': None,
            'when': {'match': 'any', 'items': [frozen(item) for item in every_kind[:5]]},
        },
        {
            'id': 'secret',
            'name': 'secret 업적',
            'description': 'secret 을 했다',
            'hidden': True,
            'image_id': None,
            'when': {'match': 'all', 'items': [frozen(every_kind[5])]},
        },
    ]
    assert character['achievements'] == document['achievements']


async def test_achievements_can_be_patched_alone(client: AsyncClient, operator: dict):
    character = await create(client, operator)
    assert character['achievements'] == []

    response = await patch(client, operator, character, {'achievements': [achievement('cafe', VISIT_CAFE)]})

    assert response.status_code == status.HTTP_200_OK, response.text
    assert [entry['id'] for entry in response.json()['achievements']] == ['cafe']
    assert response.json()['places'] == character['places']


@pytest.mark.parametrize(
    'achievements',
    [
        [achievement('cafe', VISIT_CAFE), achievement('cafe', VISIT_CAFE)],
        [achievement('cafe')],
        [achievement('cafe', *[VISIT_CAFE] * 6)],
        [achievement('cafe', {'kind': 'visited_place'})],
        [achievement('cafe', {'kind': 'visited_place', 'target': 'cafe', 'count': 2})],
        [achievement('cafe', {'kind': 'visited_place', 'target': 'cafe', 'value': '연인'})],
        [achievement('cafe', {'kind': 'affection_stage', 'target': '연인'})],
        [achievement('cafe', {'kind': 'messages_at_least', 'count': 10, 'target': 'cafe'})],
        [achievement('cafe', {'kind': 'messages_at_least', 'count': 0})],
        [achievement('cafe', {'kind': 'hold_item', 'target': 'cookie', 'count': 10_000})],
        [achievement('cafe', {'kind': 'said_word', 'target': 'cafe'})],
        [{**achievement('cafe', VISIT_CAFE), 'name': ' '}],
        [{**achievement('cafe', VISIT_CAFE), 'name': '가' * 41}],
        [{**achievement('cafe', VISIT_CAFE), 'description': '가' * 201}],
        [{**achievement('cafe', VISIT_CAFE), 'when': {'match': 'some', 'items': [VISIT_CAFE]}}],
        [achievement(f'a{index}', VISIT_CAFE) for index in range(51)],
    ],
    ids=[
        'repeated-id',
        'no-condition',
        'six-conditions',
        'missing-target',
        'count-on-a-place',
        'value-on-a-place',
        'target-for-a-stage',
        'target-on-messages',
        'zero-messages',
        'too-many-held',
        'unknown-kind',
        'blank-name',
        'long-name',
        'long-description',
        'unknown-match',
        'too-many',
    ],
)
async def test_shapes_known_without_the_rest_are_refused_on_save(
    client: AsyncClient, operator: dict, achievements: list
):
    response = await post(client, operator, achievements=achievements)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text


async def test_fifty_achievements_and_five_conditions_are_kept(client: AsyncClient, operator: dict):
    many = [achievement(f'a{index}', VISIT_CAFE) for index in range(49)]
    many.append(achievement('five', *[VISIT_CAFE] * 5))

    response = await post(client, operator, achievements=many)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert len(response.json()['achievements']) == 50


async def test_achievement_pictures_must_be_mine_and_are_recorded(
    client: AsyncClient, operator: dict, picture: str, session: AsyncSession
):
    theirs = await own_image(session, OTHER)
    stolen = await post(client, operator, achievements=[achievement('cafe', VISIT_CAFE, image_id=theirs)])
    assert (stolen.status_code, stolen.json()['code']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'image_not_owned')
    character = await create(client, operator)
    patched = await patch(
        client, operator, character, {'achievements': [achievement('cafe', VISIT_CAFE, image_id=theirs)]}
    )
    assert patched.json()['code'] == 'image_not_owned'

    await patch(client, operator, character, {'achievements': [achievement('cafe', VISIT_CAFE, image_id=picture)]})
    version = (await publish(client, operator, character)).json()

    used = await session.scalars(select(ImageUse.image_id).where(ImageUse.version_id == uuid.UUID(version['id'])))
    assert picture in {str(image_id) for image_id in used}


# --- 게시를 막는 것 ---


@pytest.mark.parametrize(
    ('item', 'fields'),
    [
        ({'kind': 'visited_place', 'target': 'moon'}, {}),
        ({'kind': 'hold_item', 'target': 'ghost', 'count': 2}, {}),
        ({'kind': 'received_item', 'target': 'ghost'}, {}),
        ({'kind': 'scene_seen', 'target': 'ghost'}, {}),
        ({'kind': 'affection_stage', 'value': '원수'}, {}),
        ({'kind': 'affection_stage', 'value': '연인'}, {'affection': None}),
    ],
    ids=['place', 'held-item', 'received-item', 'scene', 'stage', 'stage-without-affection'],
)
async def test_conditions_that_point_at_nothing_block_publishing(
    client: AsyncClient, operator: dict, item: dict, fields: dict
):
    character = await create(client, operator, achievements=[achievement('a', item)], **fields)

    checked = await problems(client, operator, character)
    response = await publish(client, operator, character)

    assert checked == ['achievement_target_missing']
    assert response.status_code == status.HTTP_409_CONFLICT


async def test_conditions_that_point_at_something_publish(client: AsyncClient, operator: dict, session: AsyncSession):
    items = [
        VISIT_CAFE,
        {'kind': 'hold_item', 'target': 'cookie', 'count': 2},
        {'kind': 'received_item', 'target': 'cookie'},
        {'kind': 'scene_seen', 'target': 'first-date'},
        {'kind': 'affection_stage', 'value': '낯섦'},
    ]
    messages = achievement('talker', {'kind': 'messages_at_least', 'count': 100})
    character = await create(
        client,
        operator,
        event_scenes=[await scene_body(session)],
        achievements=[achievement('all', *items), messages],
    )

    assert await problems(client, operator, character) == []
    assert (await publish(client, operator, character)).status_code == status.HTTP_201_CREATED


async def test_counting_messages_needs_nothing_else(client: AsyncClient, operator: dict):
    talker = achievement('talker', {'kind': 'messages_at_least', 'count': 10})
    character = await create(
        client, operator, places=[], start_place=None, items=[], affection=None, achievements=[talker]
    )

    assert await problems(client, operator, character) == []


# --- 공개 소개와 chat ---


async def public(client: AsyncClient, headers: dict, **fields) -> dict:
    """공개로 두고 게시한 캐릭터."""
    character = await create(client, headers, **fields)
    assert (await patch(client, headers, character, {'visibility': 'public'})).status_code == status.HTTP_200_OK
    assert (await publish(client, headers, character)).status_code == status.HTTP_201_CREATED
    return character


async def test_the_public_intro_lists_achievements_and_veils_the_hidden(
    client: AsyncClient, operator: dict, picture: str
):
    achievements = [
        achievement('cafe', VISIT_CAFE, image_id=picture),
        achievement('secret', VISIT_CAFE, hidden=True, image_id=picture),
    ]
    character = await public(client, operator, achievements=achievements)

    detail = (await client.get(f'{LISTINGS_URL}/{character["id"]}')).json()

    assert detail['achievements'] == [
        {'id': 'cafe', 'hidden': False, 'name': 'cafe 업적', 'description': 'cafe 을 했다', 'image_id': picture},
        {'id': 'secret', 'hidden': True, 'name': None, 'description': None, 'image_id': None},
    ]
    assert detail['document']['achievements'] == []
    assert detail['document']['format'] == DOCUMENT_FORMAT


async def test_chat_gets_the_conditions_through_the_service_path(client: AsyncClient, operator: dict):
    character = await public(client, operator, achievements=[achievement('secret', VISIT_CAFE, hidden=True)])

    response = await signed_get(client, f'/characters/{character["id"]}/latest', operator)

    assert response.status_code == status.HTTP_200_OK, response.text
    copied = response.json()['document']['achievements']
    assert [(entry['id'], entry['name'], entry['when']['items']) for entry in copied] == [
        ('secret', 'secret 업적', [frozen(VISIT_CAFE)])
    ]


async def test_a_character_without_achievements_shows_none(client: AsyncClient, operator: dict):
    character = await public(client, operator)

    detail = (await client.get(f'{LISTINGS_URL}/{character["id"]}')).json()

    assert (detail['achievements'], detail['document']['achievements']) == ([], [])
