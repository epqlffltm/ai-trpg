# asset-server/tests/test_character_lorebooks.py

"""
캐릭터가 가리키는 로어북(#672, 판의 형식 8)을 검증한다. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 초안은 자기 로어북만 가리킨다(남의 것, 없는 것은 422 lorebook_not_owned). 같은 것 둘, 넷 이상은 422
  - 게시하면 가리킨 로어북마다 그 마지막 판(id, 판 번호, 이름, 항목)이 캐릭터의 판에 복사된다(가리킨 차례)
  - 로어북을 고치고 다시 게시해도 이미 게시한 캐릭터의 판은 그대로다. 캐릭터를 다시 게시하면 새 판이 들어간다
  - 게시한 적이 없는 로어북이나 지운 로어북을 가리키면 게시가 막힌다(게시해 보기에도 보인다). 같은 까닭은 한 번만 적는다
  - 초안에 남의 로어북이 들어가 있어도(그사이 바뀐 것과 같다) 복사하지 않고 막는다
  - 형식 7 의 판(로어북이 없다)도 읽힌다
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.documents import DOCUMENT_FORMAT
from app.characters.models import CHARACTER_MAX_LOREBOOKS, Character, CharacterVersion
from app.main import API_PREFIX

pytestmark = pytest.mark.usefixtures('clean_tables')

CHARACTERS_URL = f'{API_PREFIX}/characters'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
OPERATOR = uuid.UUID('11111111-2222-4333-8444-555555555555')
OTHER = uuid.UUID('99999999-2222-4333-8444-555555555555')
START = {'title': '비 오는 밤', 'situation': '문을 두드리는 소리가 난다.'}
CITY = {'id': 'city', 'name': '가나폴리아', 'kind': 'place', 'keywords': ['수도'], 'content': '제국의 수도.'}


def headers_for(signing_key: SigningKey, user_id: uuid.UUID) -> dict:
    claims = make_access_claims(sub=str(user_id))
    claims['roles'] = ['operator']
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


@pytest.fixture
def mine(signing_key: SigningKey) -> dict:
    return headers_for(signing_key, OPERATOR)


@pytest.fixture
def theirs(signing_key: SigningKey) -> dict:
    return headers_for(signing_key, OTHER)


async def lorebook(client: AsyncClient, headers: dict, name: str = '제국', published: bool = True) -> dict:
    response = await client.post(LOREBOOKS_URL, json={'name': name, 'entries': [CITY]}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    made = response.json()
    if published:
        await client.post(f'{LOREBOOKS_URL}/{made["id"]}/versions', json={}, headers=headers)
    return made


async def character(client: AsyncClient, headers: dict, lorebooks: list[dict]):
    body = {'genre': 'romance', 'name': '세라', 'starts': [START], 'lorebooks': [item['id'] for item in lorebooks]}
    return await client.post(CHARACTERS_URL, json=body, headers=headers)


async def publish(client: AsyncClient, headers: dict, made: dict):
    return await client.post(f'{CHARACTERS_URL}/{made["id"]}/versions', json={}, headers=headers)


def copied(document: dict) -> list[tuple]:
    return [(item['id'], item['version'], item['name'], len(item['entries'])) for item in document['lorebooks']]


# --- 가리키기 ---


async def test_a_character_points_at_my_lorebooks(client: AsyncClient, mine: dict):
    first, second = await lorebook(client, mine), await lorebook(client, mine, '둘째')

    response = await character(client, mine, [second, first])

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()['lorebooks'] == [second['id'], first['id']]


async def test_someone_elses_or_a_missing_lorebook_is_refused(client: AsyncClient, mine: dict, theirs: dict):
    made = (await character(client, mine, [])).json()

    for target in (await lorebook(client, theirs), {'id': str(uuid.uuid4())}):
        response = await client.patch(
            f'{CHARACTERS_URL}/{made["id"]}', json={'lorebooks': [target['id']]}, headers=mine
        )
        assert (response.status_code, response.json()['code']) == (
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            'lorebook_not_owned',
        )


async def test_repeated_or_too_many_lorebooks_are_refused(client: AsyncClient, mine: dict):
    made = [await lorebook(client, mine, f'{number}') for number in range(CHARACTER_MAX_LOREBOOKS + 1)]

    repeated = await character(client, mine, [made[0], made[0]])
    too_many = await character(client, mine, made)

    assert repeated.status_code == too_many.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 게시 ---


async def test_publishing_copies_the_latest_lorebook_versions(client: AsyncClient, mine: dict):
    first, second = await lorebook(client, mine), await lorebook(client, mine, '둘째')
    await client.post(f'{LOREBOOKS_URL}/{second["id"]}/versions', json={}, headers=mine)
    made = (await character(client, mine, [second, first])).json()

    document = (await publish(client, mine, made)).json()['document']

    assert document['format'] == DOCUMENT_FORMAT == 9
    assert copied(document) == [(second['id'], 2, '둘째', 1), (first['id'], 1, '제국', 1)]
    assert document['lorebooks'][0]['entries'] == [{**CITY, 'constant': False}]


async def test_a_published_character_keeps_its_copy(client: AsyncClient, mine: dict):
    book = await lorebook(client, mine)
    made = (await character(client, mine, [book])).json()
    await publish(client, mine, made)
    await client.patch(f'{LOREBOOKS_URL}/{book["id"]}', json={'entries': []}, headers=mine)
    await client.post(f'{LOREBOOKS_URL}/{book["id"]}/versions', json={}, headers=mine)

    kept = (await client.get(f'{CHARACTERS_URL}/{made["id"]}/versions/1', headers=mine)).json()['document']
    renewed = (await publish(client, mine, made)).json()['document']

    assert copied(kept) == [(book['id'], 1, '제국', 1)]
    assert copied(renewed) == [(book['id'], 2, '제국', 0)]


async def test_an_unpublished_or_deleted_lorebook_blocks_publishing(client: AsyncClient, mine: dict):
    draft, gone = await lorebook(client, mine, published=False), await lorebook(client, mine, '지울 것')
    made = (await character(client, mine, [draft, gone])).json()
    await client.delete(f'{LOREBOOKS_URL}/{gone["id"]}', headers=mine)

    check = (await client.get(f'{CHARACTERS_URL}/{made["id"]}/publish-check', headers=mine)).json()
    response = await publish(client, mine, made)

    assert (check['ready'], check['problems']) == (False, ['lorebook_unpublished', 'lorebook_missing'])
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == ['lorebook_unpublished', 'lorebook_missing']
    # 지운 로어북의 id 는 초안에 남는다(다시 고칠 때까지)
    assert (await client.get(f'{CHARACTERS_URL}/{made["id"]}', headers=mine)).json()['lorebooks'] == [
        draft['id'],
        gone['id'],
    ]


async def test_the_same_problem_is_listed_once(client: AsyncClient, mine: dict):
    drafts = [await lorebook(client, mine, f'{number}', published=False) for number in range(2)]
    made = (await character(client, mine, drafts)).json()

    response = await publish(client, mine, made)

    assert response.json()['problems'] == ['lorebook_unpublished']


async def test_someone_elses_lorebook_in_the_draft_is_not_copied(
    client: AsyncClient, session: AsyncSession, mine: dict, theirs: dict
):
    foreign = await lorebook(client, theirs)
    made = (await character(client, mine, [])).json()
    # 붙일 때는 자기 것이었다고 치고 초안에 바로 적는다
    row = await session.get(Character, uuid.UUID(made['id']))
    row.lorebooks = [uuid.UUID(foreign['id'])]
    await session.commit()

    response = await publish(client, mine, made)

    assert (response.status_code, response.json()['problems']) == (status.HTTP_409_CONFLICT, ['lorebook_missing'])


async def test_without_lorebooks_nothing_is_copied(client: AsyncClient, mine: dict):
    made = (await character(client, mine, [])).json()

    assert (await publish(client, mine, made)).json()['document']['lorebooks'] == []


# --- 형식 7 ---


async def test_a_format_seven_version_is_still_read(client: AsyncClient, session: AsyncSession, mine: dict):
    made = (await character(client, mine, [await lorebook(client, mine)])).json()
    published = (await publish(client, mine, made)).json()
    version = await session.get(CharacterVersion, uuid.UUID(published['id']))
    version.document = {
        **{key: value for key, value in version.document.items() if key != 'lorebooks'},
        'format': 7,
    }
    await session.commit()

    response = await client.get(f'{CHARACTERS_URL}/{made["id"]}/versions/1', headers=mine)

    assert response.status_code == status.HTTP_200_OK
    assert (response.json()['document']['format'], response.json()['document']['lorebooks']) == (7, [])
