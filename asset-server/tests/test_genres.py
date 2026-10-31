# asset-server/tests/test_genres.py

"""
캐릭터와 세계관의 장르(app/genres.py)를 검증한다. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 장르는 정해진 목록에서 하나다. 비워 둘 수 있고(null), 고친 뒤 null 로 다시 비울 수 있다.
    목록에 없는 값, 남성향·여성향, 성인용, 여러 개는 받지 않는다(422)
  - 게시하면 판의 문서에 굳는다(캐릭터 형식 9, 세계관 형식 4). 그 뒤에 초안을 고쳐도 판의 장르는 그대로다
  - 공개 목록과 소개에 판의 장르가 실린다
  - 장르가 생기기 전의 판(캐릭터 8, 세계관 3)은 장르가 없는 것(null)으로 읽는다
"""

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey

from app.characters.documents import DOCUMENT_FORMAT as CHARACTER_FORMAT
from app.characters.documents import CharacterDocument
from app.main import API_PREFIX
from app.worlds.documents import DOCUMENT_FORMAT as WORLD_FORMAT
from tests.worlds import CHARACTERS_URL, OWNER, START, WORLDS_URL, bearer, character, create_world, full_world, publish

pytestmark = pytest.mark.usefixtures('clean_tables')

CHARACTER_LISTINGS_URL = f'{API_PREFIX}/listings/characters'
WORLD_LISTINGS_URL = f'{API_PREFIX}/listings/worlds'


@pytest.fixture
def owner(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OWNER)


async def public_character(client: AsyncClient, headers: dict, **fields) -> dict:
    """공개로 두고 게시한 캐릭터."""
    made = await character(client, headers, published=False, **fields)
    await client.patch(f'{CHARACTERS_URL}/{made["id"]}', json={'visibility': 'public'}, headers=headers)
    response = await client.post(f'{CHARACTERS_URL}/{made["id"]}/versions', json={}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return made


async def public_world(client: AsyncClient, headers: dict, **fields) -> dict:
    """공개로 두고 게시한 세계관."""
    ari, beo = await character(client, headers, '아리'), await character(client, headers, '버')
    world = await create_world(client, headers, {**full_world(ari['id'], beo['id']), **fields})
    await client.patch(f'{WORLDS_URL}/{world["id"]}', json={'visibility': 'public'}, headers=headers)
    response = await publish(client, headers, world)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return world


# --- 캐릭터 ---


async def test_a_character_has_no_genre_until_one_is_chosen(client: AsyncClient, owner: dict):
    made = await character(client, owner, published=False)

    assert made['genre'] is None


async def test_a_character_genre_can_be_chosen_changed_and_cleared(client: AsyncClient, owner: dict):
    made = await character(client, owner, published=False, genre='fantasy')
    url = f'{CHARACTERS_URL}/{made["id"]}'

    changed = await client.patch(url, json={'genre': 'horror'}, headers=owner)
    untouched = await client.patch(url, json={'name': '세라'}, headers=owner)
    cleared = await client.patch(url, json={'genre': None}, headers=owner)

    assert made['genre'] == 'fantasy'
    assert changed.json()['genre'] == 'horror'
    # 보내지 않으면 그대로다
    assert untouched.json()['genre'] == 'horror'
    # null 은 비우기다(그림처럼)
    assert cleared.json()['genre'] is None


@pytest.mark.parametrize('genre', ['없는장르', 'for_men', 'for_women', 'adult', ['fantasy'], ''])
async def test_a_bad_character_genre_is_refused(client: AsyncClient, owner: dict, genre: object):
    body = {'name': '세라', 'starts': [START], 'genre': genre}

    response = await client.post(CHARACTERS_URL, json=body, headers=owner)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_publishing_freezes_the_character_genre(client: AsyncClient, owner: dict):
    made = await public_character(client, owner, genre='wuxia')
    await client.patch(f'{CHARACTERS_URL}/{made["id"]}', json={'genre': 'romance'}, headers=owner)

    frozen = (await client.get(f'{CHARACTERS_URL}/{made["id"]}/versions/1', headers=owner)).json()['document']
    listed = (await client.get(CHARACTER_LISTINGS_URL)).json()['items']
    detail = (await client.get(f'{CHARACTER_LISTINGS_URL}/{made["id"]}')).json()['document']

    assert (frozen['format'], frozen['genre']) == (CHARACTER_FORMAT, 'wuxia') == (9, 'wuxia')
    # 공개 목록과 소개는 판의 장르다(그 뒤에 고친 초안이 아니다)
    assert [item['genre'] for item in listed] == ['wuxia']
    assert detail['genre'] == 'wuxia'


async def test_a_character_without_a_genre_is_published_without_one(client: AsyncClient, owner: dict):
    await public_character(client, owner)

    listed = (await client.get(CHARACTER_LISTINGS_URL)).json()['items']

    # 장르는 게시의 조건이 아니다. 고르지 않았으면 화면이 기본 테마를 쓴다
    assert [item['genre'] for item in listed] == [None]


def test_a_character_version_from_before_genres_reads_as_none():
    document = CharacterDocument.model_validate(
        {
            'format': 8,
            'name': '세라',
            'intro_html': '',
            'greeting': '',
            'speech_examples': '',
            'age': '',
            'gender': '',
            'tags': [],
            'starts': [START],
            'image_id': None,
            'rating': 'all',
        }
    )

    assert document.genre is None


# --- 세계관 ---


async def test_a_world_genre_can_be_chosen_changed_and_cleared(client: AsyncClient, owner: dict):
    world = await create_world(client, owner, {'name': '여름 학원', 'genre': 'romance'})
    url = f'{WORLDS_URL}/{world["id"]}'

    changed = await client.patch(url, json={'genre': 'slice_of_life'}, headers=owner)
    cleared = await client.patch(url, json={'genre': None}, headers=owner)

    assert world['genre'] == 'romance'
    assert changed.json()['genre'] == 'slice_of_life'
    assert cleared.json()['genre'] is None


@pytest.mark.parametrize('genre', ['없는장르', 'for_women', ['romance']])
async def test_a_bad_world_genre_is_refused(client: AsyncClient, owner: dict, genre: object):
    response = await client.post(WORLDS_URL, json={'name': '여름 학원', 'genre': genre}, headers=owner)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_publishing_freezes_the_world_genre(client: AsyncClient, owner: dict):
    world = await public_world(client, owner, genre='horror')
    await client.patch(f'{WORLDS_URL}/{world["id"]}', json={'genre': 'comedy'}, headers=owner)

    frozen = (await client.get(f'{WORLDS_URL}/{world["id"]}/versions/1', headers=owner)).json()['document']
    listed = (await client.get(WORLD_LISTINGS_URL)).json()['items']
    detail = (await client.get(f'{WORLD_LISTINGS_URL}/{world["id"]}')).json()

    assert (frozen['format'], frozen['genre']) == (WORLD_FORMAT, 'horror') == (4, 'horror')
    assert [item['genre'] for item in listed] == ['horror']
    assert detail['genre'] == 'horror'
