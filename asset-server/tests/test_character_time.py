# asset-server/tests/test_character_time.py

"""
시작 상황의 시작 시각(hour)과 장소의 시간대 배경(backgrounds)을 검증한다(#668, 판의 형식 4).
실제 DB(asset_test)에서 돈다.

보는 것.
  - 시작 시각은 초안과 판에 남는다. 적지 않으면 정오다. 0~23 만 받는다
  - 시간대 배경은 다섯 시간대(dawn, morning, day, evening, night)의 열쇠만 받는다
  - 시간대 배경도 자기 그림만 붙인다. 게시하면 판에 쓰인 그림으로 적힌다. 초안에 남은 남의 그림은 게시를 막는다
  - 형식 3 의 판(시작 시각과 시간대 배경이 없다)도 읽힌다
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.documents import DOCUMENT_FORMAT
from app.characters.models import START_HOUR_DEFAULT, Character, CharacterVersion
from app.images.models import ImageUse
from app.main import API_PREFIX
from tests.images import own_image

pytestmark = pytest.mark.usefixtures('clean_tables')

CHARACTERS_URL = f'{API_PREFIX}/characters'
OPERATOR = uuid.UUID('11111111-2222-4333-8444-555555555555')
OTHER = uuid.UUID('99999999-2222-4333-8444-555555555555')
NIGHT_START = {'title': '비 오는 밤', 'situation': '문을 두드리는 소리가 난다.', 'hour': 21}
SOME_ID = str(uuid.UUID('22222222-3333-4444-8555-666666666666'))
LIBRARY = {'id': 'library', 'name': '도서관', 'description': '', 'image_id': None, 'backgrounds': {}}


@pytest.fixture
def operator(signing_key: SigningKey) -> dict:
    claims = make_access_claims(sub=str(OPERATOR))
    claims['roles'] = ['operator']
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


async def create(client: AsyncClient, headers: dict, **fields) -> dict:
    body = {
        'genre': 'romance',
        'name': '세라',
        'starts': [NIGHT_START],
        'places': [LIBRARY],
        'start_place': 'library',
        **fields,
    }
    response = await client.post(CHARACTERS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def patch(client: AsyncClient, headers: dict, character: dict, body: dict):
    return await client.patch(f'{CHARACTERS_URL}/{character["id"]}', json=body, headers=headers)


async def publish(client: AsyncClient, headers: dict, character: dict):
    return await client.post(f'{CHARACTERS_URL}/{character["id"]}/versions', json={}, headers=headers)


# --- 시작 시각 ---


async def test_the_start_hour_is_kept_and_frozen(client: AsyncClient, operator: dict):
    character = await create(client, operator)

    document = (await publish(client, operator, character)).json()['document']

    assert character['starts'] == [NIGHT_START]
    assert (document['format'], document['starts']) == (DOCUMENT_FORMAT, [NIGHT_START])


async def test_a_start_without_an_hour_begins_at_noon(client: AsyncClient, operator: dict):
    character = await create(client, operator, starts=[{'title': '오후', 'situation': '햇살이 든다.'}])

    assert character['starts'][0]['hour'] == START_HOUR_DEFAULT == 12


@pytest.mark.parametrize('hour', [0, 23])
async def test_the_first_and_last_hours_are_accepted(client: AsyncClient, operator: dict, hour: int):
    character = await create(client, operator, starts=[{**NIGHT_START, 'hour': hour}])

    assert character['starts'][0]['hour'] == hour


@pytest.mark.parametrize('hour', [-1, 24, 1.5, '밤', None])
async def test_a_bad_start_hour_is_refused(client: AsyncClient, operator: dict, hour):
    character = await create(client, operator)

    response = await patch(client, operator, character, {'starts': [{**NIGHT_START, 'hour': hour}]})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 시간대 배경 ---


async def test_backgrounds_for_each_time_of_day_are_kept(client: AsyncClient, operator: dict, session: AsyncSession):
    night = await own_image(session, OPERATOR)
    dawn = await own_image(session, OPERATOR)
    backgrounds = {'night': night, 'dawn': dawn}
    character = await create(client, operator, places=[{**LIBRARY, 'backgrounds': backgrounds}])

    document = (await publish(client, operator, character)).json()['document']

    assert character['places'][0]['backgrounds'] == backgrounds
    assert document['places'][0]['backgrounds'] == backgrounds


@pytest.mark.parametrize(
    'backgrounds',
    [{'noon': SOME_ID}, {'Night': SOME_ID}, {'night': 'not-an-id'}, {'night': None}, ['night', SOME_ID]],
)
async def test_bad_backgrounds_are_refused(client: AsyncClient, operator: dict, backgrounds):
    character = await create(client, operator)

    response = await patch(client, operator, character, {'places': [{**LIBRARY, 'backgrounds': backgrounds}]})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_backgrounds_must_be_my_images(client: AsyncClient, operator: dict, session: AsyncSession):
    theirs = await own_image(session, OTHER)
    character = await create(client, operator)

    response = await patch(client, operator, character, {'places': [{**LIBRARY, 'backgrounds': {'night': theirs}}]})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['code'] == 'image_not_owned'


async def test_publishing_records_background_images(client: AsyncClient, operator: dict, session: AsyncSession):
    base = await own_image(session, OPERATOR)
    night = await own_image(session, OPERATOR)
    place = {**LIBRARY, 'image_id': base, 'backgrounds': {'night': night, 'evening': base}}
    character = await create(client, operator, places=[place])

    await publish(client, operator, character)

    used = [str(image) for image in (await session.scalars(select(ImageUse.image_id))).all()]
    assert sorted(used) == sorted([base, night])


async def test_a_foreign_background_left_in_the_draft_blocks_publishing(
    client: AsyncClient, operator: dict, session: AsyncSession
):
    theirs = await own_image(session, OTHER)
    character = await create(client, operator)
    # 붙일 때는 자기 그림이었다고 치고 초안에 바로 적는다(그사이 주인이 바뀐 것과 같다)
    row = await session.get(Character, uuid.UUID(character['id']))
    row.places = [{**LIBRARY, 'backgrounds': {'night': theirs}}]
    await session.commit()

    response = await publish(client, operator, character)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == ['image_not_owned']


# --- 형식 3 ---


async def test_a_format_three_version_is_still_read(client: AsyncClient, operator: dict, session: AsyncSession):
    character = await create(client, operator)
    published = (await publish(client, operator, character)).json()
    version = await session.get(CharacterVersion, uuid.UUID(published['id']))
    old = version.document
    starts = [{'title': start['title'], 'situation': start['situation']} for start in old['starts']]
    places = [{key: value for key, value in place.items() if key != 'backgrounds'} for place in old['places']]
    version.document = {**old, 'format': 3, 'starts': starts, 'places': places}
    await session.commit()

    response = await client.get(f'{CHARACTERS_URL}/{character["id"]}/versions/1', headers=operator)

    assert response.status_code == status.HTTP_200_OK
    document = response.json()['document']
    assert (document['format'], document['starts'][0]['hour'], document['places'][0]['backgrounds']) == (3, 12, {})
