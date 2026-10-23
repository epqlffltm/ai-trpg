# asset-server/tests/test_characters_api.py

"""
캐릭터의 초안, 게시와 판, 공개 목록(#567)을 검증한다. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 만들기: 1~2단계에는 운영자만 만든다. 모두에게 열면 누구나 만든다. 공개로 두는 것은 늘 운영자만이다.
    성인 등급은 성인 확인을 한 사람(또는 운영자)만 쓴다. 칸의 검사(태그, 시작 상황, 소개의 크기, null).
  - 초안: 만든 사람만 보고 고친다. 남의 것은 404 다. 지우면 판도 지워진다.
  - 게시: 시작 상황이 없으면 409 다. 판은 1 부터 오르고, 소개는 걸러져 들어가고, 걸러 낸 것을 알린다.
    판은 바뀌지 않는다(초안을 고쳐도). 동시에 게시해도 번호가 겹치지 않는다. 게시해 보기는 판을 만들지 않는다.
  - 공개 목록: 공개이고 게시한 판이 있는 것만, 마지막 판의 값으로 낸다. 등급은 판의 것으로 거른다.
    로그인하지 않은 사람과 성인 확인을 하지 않은 사람에게 성인용은 없는 것(404)이다. 틀린 토큰은 401 이다.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import FakeAuthServer, SigningKey, make_access_claims, make_token
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.characters.documents import DOCUMENT_FORMAT
from app.characters.models import CHARACTER_MAX_TAGS, Character, CharacterVersion
from app.content.html import INTRO_MAX_BYTES
from app.main import API_PREFIX, create_app
from tests.conftest import make_client, make_test_settings

pytestmark = pytest.mark.usefixtures('clean_tables')

CHARACTERS_URL = f'{API_PREFIX}/characters'
LISTINGS_URL = f'{API_PREFIX}/listings/characters'
OPERATOR = uuid.UUID('11111111-2222-4333-8444-555555555555')
PLAYER = uuid.UUID('99999999-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'
START = {'title': '비 오는 밤', 'situation': '문을 두드리는 소리가 난다.', 'hour': 21}
FULL = {
    'name': '세라',
    'intro_html': '<p>도서관의 <strong>사서</strong>.</p><script>alert(1)</script><a href="javascript:x">링크</a>',
    'greeting': '어서 와요. 찾는 책이 있나요?',
    'speech_examples': '"조용히 해 주세요."',
    'age': '스물넷',
    'gender': '여성',
    'tags': ['사서', '조용함'],
    'starts': [START],
    'rating': 'all',
}


def bearer(signing_key: SigningKey, user_id: uuid.UUID, operator: bool = False, adult: bool = False) -> dict:
    claims = make_access_claims(sub=str(user_id))
    if operator:
        claims['roles'] = ['operator']
    if adult:
        claims['adult_content'] = True
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


@pytest.fixture
def operator(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OPERATOR, operator=True)


@pytest.fixture
def player(signing_key: SigningKey) -> dict:
    return bearer(signing_key, PLAYER)


@pytest.fixture
def adult(signing_key: SigningKey) -> dict:
    return bearer(signing_key, PLAYER, adult=True)


@pytest.fixture
async def open_app(auth_server: FakeAuthServer, engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    """누구나 캐릭터를 만드는 앱(3단계)."""
    app = create_app(
        make_test_settings(characters_for_everyone=True), http_client=auth_server.make_client(), engine=engine
    )
    yield app
    await app.state.http_client.aclose()


async def create(client: AsyncClient, headers: dict, **fields) -> dict:
    response = await client.post(CHARACTERS_URL, json={**FULL, **fields}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def publish(client: AsyncClient, headers: dict, character: dict, note: str = '') -> dict:
    response = await client.post(f'{CHARACTERS_URL}/{character["id"]}/versions', json={'note': note}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def make_public(client: AsyncClient, headers: dict, **fields) -> dict:
    """공개로 두고 게시한 캐릭터."""
    character = await create(client, headers, **fields)
    await client.patch(f'{CHARACTERS_URL}/{character["id"]}', json={'visibility': 'public'}, headers=headers)
    await publish(client, headers, character)
    return character


async def listed_names(client: AsyncClient, headers: dict | None = None) -> list[str]:
    response = await client.get(LISTINGS_URL, headers=headers or {})
    assert response.status_code == status.HTTP_200_OK, response.text
    return [item['name'] for item in response.json()['items']]


# --- 만들기 ---


@pytest.mark.parametrize(('method', 'path'), [('POST', ''), ('GET', ''), ('GET', f'/{NO_SUCH_ID}')])
async def test_drafts_need_login(client: AsyncClient, method: str, path: str):
    response = await client.request(method, f'{CHARACTERS_URL}{path}', json={})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_only_operators_make_characters_for_now(client: AsyncClient, operator: dict, player: dict):
    refused = await client.post(CHARACTERS_URL, json=FULL, headers=player)
    made = await create(client, operator)

    assert refused.status_code == status.HTTP_403_FORBIDDEN
    assert refused.json() == {'detail': '지금은 운영자만 할 수 있습니다.', 'code': 'operator_only'}
    assert {key: made[key] for key in FULL} == FULL
    assert (made['visibility'], made['latest_version'], made['published_at']) == ('private', None, None)


async def test_when_open_anyone_makes_but_only_operators_make_public(open_app: FastAPI, player: dict, operator: dict):
    async with make_client(open_app) as client:
        mine = await create(client, player)
        public = await client.patch(f'{CHARACTERS_URL}/{mine["id"]}', json={'visibility': 'public'}, headers=player)
        theirs = await create(client, operator)
        made_public = await client.patch(
            f'{CHARACTERS_URL}/{theirs["id"]}', json={'visibility': 'public'}, headers=operator
        )

    assert public.status_code == status.HTTP_403_FORBIDDEN
    assert made_public.json()['visibility'] == 'public'


async def test_adult_characters_need_adult_content(open_app: FastAPI, player: dict, adult: dict):
    async with make_client(open_app) as client:
        refused = await client.post(CHARACTERS_URL, json={**FULL, 'rating': 'adult'}, headers=player)
        mine = await create(client, player)
        raised = await client.patch(f'{CHARACTERS_URL}/{mine["id"]}', json={'rating': 'adult'}, headers=player)
        allowed = await client.post(CHARACTERS_URL, json={**FULL, 'rating': 'adult'}, headers=adult)

    assert refused.status_code == raised.status_code == status.HTTP_403_FORBIDDEN
    assert refused.json()['code'] == 'adult_content_required'
    assert allowed.status_code == status.HTTP_201_CREATED


@pytest.mark.parametrize(
    'body',
    [
        {'name': '  '},
        {'tags': [f'태그{number}' for number in range(CHARACTER_MAX_TAGS + 1)]},
        {'tags': ['Cat', 'cat']},
        {'starts': [START, {**START, 'situation': '다른 상황'}]},
        {'starts': [{'title': '제목', 'situation': ''}]},
        {'intro_html': 'a' * (INTRO_MAX_BYTES + 1)},
        {'intro_html': '가' * (INTRO_MAX_BYTES // 3 + 1)},
        {'visibility': 'public'},
        {'owner_id': str(PLAYER)},
        {'rating': 'teen'},
    ],
)
async def test_a_bad_character_is_refused(client: AsyncClient, operator: dict, body: dict):
    response = await client.post(CHARACTERS_URL, json={**FULL, **body}, headers=operator)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_null_is_taken_only_for_the_image(client: AsyncClient, operator: dict):
    character = await create(client, operator)
    url = f'{CHARACTERS_URL}/{character["id"]}'

    taken_off = await client.patch(url, json={'image_id': None}, headers=operator)
    refused = await client.patch(url, json={'tags': None}, headers=operator)

    assert taken_off.json()['image_id'] is None
    assert refused.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 초안 ---


async def test_drafts_are_only_the_makers(client: AsyncClient, operator: dict, signing_key: SigningKey):
    other_operator = bearer(signing_key, PLAYER, operator=True)
    character = await create(client, operator)
    url = f'{CHARACTERS_URL}/{character["id"]}'

    responses = [
        await client.get(url, headers=other_operator),
        await client.patch(url, json={'name': '남'}, headers=other_operator),
        await client.delete(url, headers=other_operator),
        await client.post(f'{url}/versions', json={}, headers=other_operator),
        await client.get(f'{url}/versions', headers=other_operator),
        await client.get(f'{url}/publish-check', headers=other_operator),
    ]

    assert {response.status_code for response in responses} == {status.HTTP_404_NOT_FOUND}
    assert (await client.get(CHARACTERS_URL, headers=other_operator)).json() == {'items': [], 'total': 0}


async def test_my_list_has_the_latest_edit_first(client: AsyncClient, operator: dict):
    first = await create(client, operator, name='하나')
    await create(client, operator, name='둘')
    await client.patch(f'{CHARACTERS_URL}/{first["id"]}', json={'greeting': '안녕'}, headers=operator)

    page = (await client.get(CHARACTERS_URL, params={'limit': 1}, headers=operator)).json()

    assert page['total'] == 2
    assert [item['name'] for item in page['items']] == ['하나']


async def test_deleting_a_character_deletes_its_versions(client: AsyncClient, operator: dict, session: AsyncSession):
    character = await create(client, operator)
    await publish(client, operator, character)

    response = await client.delete(f'{CHARACTERS_URL}/{character["id"]}', headers=operator)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await session.scalar(select(func.count()).select_from(CharacterVersion)) == 0


# --- 게시 ---


async def test_a_character_without_a_start_is_not_published(client: AsyncClient, operator: dict):
    character = await create(client, operator, starts=[])
    url = f'{CHARACTERS_URL}/{character["id"]}'

    check = await client.get(f'{url}/publish-check', headers=operator)
    refused = await client.post(f'{url}/versions', json={}, headers=operator)

    assert check.json() == {
        'ready': False,
        'problems': ['start_missing'],
        'removed': [{'kind': 'tag', 'name': 'script'}, {'kind': 'link', 'name': 'javascript:x'}],
    }
    assert refused.status_code == status.HTTP_409_CONFLICT
    assert refused.json() == {'detail': '게시할 조건을 갖추지 못했습니다.', 'problems': ['start_missing']}
    assert (await client.get(f'{url}/versions', headers=operator)).json() == []


async def test_publishing_freezes_a_cleaned_document(client: AsyncClient, operator: dict):
    character = await create(client, operator)
    url = f'{CHARACTERS_URL}/{character["id"]}'

    first = await publish(client, operator, character, note='처음')
    await client.patch(url, json={'name': '세라 2', 'starts': []}, headers=operator)
    frozen = (await client.get(f'{url}/versions/1', headers=operator)).json()
    draft = (await client.get(url, headers=operator)).json()

    assert (first['number'], first['note']) == (1, '처음')
    assert (
        first['document']['intro_html'] == '<p>도서관의 <strong>사서</strong>.</p><a rel="noopener noreferrer">링크</a>'
    )
    assert first['removed'] == [{'kind': 'tag', 'name': 'script'}, {'kind': 'link', 'name': 'javascript:x'}]
    assert first['document']['format'] == DOCUMENT_FORMAT and first['document']['starts'] == [START]
    # 판은 바뀌지 않는다. 초안은 쓴 그대로다(거르지 않는다)
    assert frozen['document'] == first['document']
    assert draft['name'] == '세라 2' and '<script>' in draft['intro_html']
    assert (draft['latest_version'], draft['published_at'] is not None) == (1, True)


async def test_publishing_waits_for_another_publish_and_takes_the_next_number(
    client: AsyncClient, operator: dict, session: AsyncSession
):
    character = await create(client, operator)
    # 다른 게시가 그 행을 잠그고 4 번째 판까지 냈다
    locked = await session.scalar(select(Character).where(Character.id == uuid.UUID(character['id'])).with_for_update())
    locked.latest_version = 4
    locked.published_at = func.now()
    await session.flush()

    waiting = asyncio.create_task(
        client.post(f'{CHARACTERS_URL}/{character["id"]}/versions', json={}, headers=operator)
    )
    await asyncio.sleep(0.3)
    assert not waiting.done()
    await session.commit()
    response = await waiting

    # 기다렸다가 4 를 읽고 5 를 쓴다. 잠그지 않으면 처음 읽은 것(없음)으로 1 을 쓴다
    assert response.json()['number'] == 5


async def test_versions_are_listed_newest_first(client: AsyncClient, operator: dict):
    character = await create(client, operator)
    await publish(client, operator, character)
    await publish(client, operator, character)

    listed = (await client.get(f'{CHARACTERS_URL}/{character["id"]}/versions', headers=operator)).json()

    assert [version['number'] for version in listed] == [2, 1]


async def test_an_unknown_version_is_not_found(client: AsyncClient, operator: dict):
    character = await create(client, operator)

    response = await client.get(f'{CHARACTERS_URL}/{character["id"]}/versions/1', headers=operator)

    assert response.status_code == status.HTTP_404_NOT_FOUND


# --- 공개 목록 ---


async def test_only_public_published_characters_are_listed(client: AsyncClient, operator: dict):
    await create(client, operator, name='비공개')
    unpublished = await create(client, operator, name='게시 전')
    await client.patch(f'{CHARACTERS_URL}/{unpublished["id"]}', json={'visibility': 'public'}, headers=operator)
    await make_public(client, operator, name='먼저')
    await make_public(client, operator, name='나중')

    page = (await client.get(LISTINGS_URL)).json()

    assert [item['name'] for item in page['items']] == ['나중', '먼저']
    assert page['total'] == 2
    assert page['items'][0]['version'] == 1 and page['items'][0]['tags'] == FULL['tags']
    versions = (await client.get(f'{CHARACTERS_URL}/{page["items"][0]["id"]}/versions', headers=operator)).json()
    assert page['items'][0]['published_at'] == versions[0]['created_at']


async def test_the_listing_shows_the_latest_version_not_the_draft(client: AsyncClient, operator: dict):
    character = await make_public(client, operator)
    await client.patch(f'{CHARACTERS_URL}/{character["id"]}', json={'name': '고친 이름'}, headers=operator)

    before = await listed_names(client)
    await publish(client, operator, character)
    after = (await client.get(f'{LISTINGS_URL}/{character["id"]}')).json()

    assert before == [FULL['name']]
    assert (after['version'], after['document']['name']) == (2, '고친 이름')


async def test_adult_characters_are_hidden_from_those_who_cannot_see_them(
    client: AsyncClient, operator: dict, player: dict, adult: dict
):
    shown = await make_public(client, operator, name='전체')
    hidden = await make_public(client, operator, name='성인', rating='adult')

    assert await listed_names(client) == ['전체']
    assert await listed_names(client, player) == ['전체']
    assert await listed_names(client, adult) == ['성인', '전체']
    assert await listed_names(client, operator) == ['성인', '전체']
    assert (await client.get(f'{LISTINGS_URL}/{hidden["id"]}', headers=player)).status_code == status.HTTP_404_NOT_FOUND
    assert (await client.get(f'{LISTINGS_URL}/{hidden["id"]}', headers=adult)).status_code == status.HTTP_200_OK
    assert (await client.get(f'{LISTINGS_URL}/{shown["id"]}')).status_code == status.HTTP_200_OK


async def test_the_rating_of_the_published_version_decides(client: AsyncClient, operator: dict):
    lowered = await make_public(client, operator, name='낮춤', rating='adult')
    raised = await make_public(client, operator, name='올림')
    await client.patch(f'{CHARACTERS_URL}/{lowered["id"]}', json={'rating': 'all'}, headers=operator)
    await client.patch(f'{CHARACTERS_URL}/{raised["id"]}', json={'rating': 'adult'}, headers=operator)

    before = await listed_names(client)
    await publish(client, operator, lowered)
    await publish(client, operator, raised)
    after = await listed_names(client)

    # 초안의 등급을 바꿔도 다음 판까지는 게시한 판의 등급으로 거른다
    assert before == ['올림']
    assert after == ['낮춤']


async def test_making_a_character_private_hides_it(client: AsyncClient, operator: dict):
    character = await make_public(client, operator)

    await client.patch(f'{CHARACTERS_URL}/{character["id"]}', json={'visibility': 'private'}, headers=operator)

    assert await listed_names(client) == []
    assert (await client.get(f'{LISTINGS_URL}/{character["id"]}')).status_code == status.HTTP_404_NOT_FOUND


async def test_a_wrong_token_on_the_listing_is_refused(client: AsyncClient):
    response = await client.get(LISTINGS_URL, headers={'Authorization': 'Bearer not-a-token'})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_the_listing_pages(client: AsyncClient, operator: dict):
    for number in range(3):
        await make_public(client, operator, name=f'캐릭터 {number}')

    page = (await client.get(LISTINGS_URL, params={'limit': 1, 'offset': 1})).json()

    assert page['total'] == 3
    assert [item['name'] for item in page['items']] == ['캐릭터 1']
