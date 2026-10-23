# asset-server/tests/test_lorebooks_api.py

"""
로어북의 초안과 판(app/lorebooks/, #672)을 검증한다. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 만들고 읽고 고치고 지운다. 항목의 기본값(종류 기타, 키워드 없음, 상시 아님)이 채워진다. 보낸 칸만 바뀐다
  - 칸의 검사: 같은 항목 id, 대소문자만 다른 같은 키워드, 키워드의 수, 빈 내용, 내용의 길이, 모르는 종류, null
  - 1~2단계에는 운영자만 만든다
  - 남의 로어북은 읽기, 고치기, 지우기, 게시, 판 모두 404 다. 목록은 내 것만이고 항목 수를 싣는다
  - 게시하면 판이 생기고 번호가 오른다. 판은 형식 1 의 문서이고 설명은 들어가지 않는다. 초안을 고쳐도 판은 그대로다
  - 지우면 판도 함께 지워진다
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lorebooks.documents import LOREBOOK_FORMAT
from app.lorebooks.models import (
    LORE_ENTRY_CONTENT_MAX_LENGTH,
    LORE_ENTRY_MAX_KEYWORDS,
    LOREBOOK_MAX_ENTRIES,
    LorebookVersion,
)
from app.main import API_PREFIX

pytestmark = pytest.mark.usefixtures('clean_tables')

LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
OPERATOR = uuid.UUID('11111111-2222-4333-8444-555555555555')
OTHER = uuid.UUID('99999999-2222-4333-8444-555555555555')
CITY = {'id': 'city', 'name': '가나폴리아', 'content': '제국의 수도. 일곱 언덕 위에 있다.', 'keywords': ['수도']}
EMPEROR = {'id': 'emperor', 'name': '황제', 'kind': 'person', 'content': '늙은 황제.', 'constant': True}


def headers_for(signing_key: SigningKey, user_id: uuid.UUID, operator: bool = True) -> dict:
    claims = make_access_claims(sub=str(user_id))
    if operator:
        claims['roles'] = ['operator']
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


@pytest.fixture
def mine(signing_key: SigningKey) -> dict:
    return headers_for(signing_key, OPERATOR)


@pytest.fixture
def theirs(signing_key: SigningKey) -> dict:
    return headers_for(signing_key, OTHER)


async def create(client: AsyncClient, headers: dict, **fields) -> dict:
    body = {'name': '제국의 설정', 'description': '메모', 'entries': [CITY, EMPEROR], **fields}
    response = await client.post(LOREBOOKS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def url(lorebook: dict, *rest: str) -> str:
    return '/'.join([f'{LOREBOOKS_URL}/{lorebook["id"]}', *rest])


async def publish(client: AsyncClient, headers: dict, lorebook: dict, note: str = ''):
    return await client.post(url(lorebook, 'versions'), json={'note': note}, headers=headers)


# --- 초안 ---


async def test_a_lorebook_is_created_with_defaults(client: AsyncClient, mine: dict):
    lorebook = await create(client, mine)

    assert (lorebook['name'], lorebook['description'], lorebook['latest_version']) == ('제국의 설정', '메모', None)
    assert lorebook['entries'] == [
        {**CITY, 'kind': 'other', 'constant': False},
        {**EMPEROR, 'keywords': []},
    ]


async def test_only_operators_make_lorebooks_for_now(client: AsyncClient, signing_key: SigningKey):
    response = await client.post(
        LOREBOOKS_URL, json={'name': '설정'}, headers=headers_for(signing_key, OPERATOR, operator=False)
    )

    assert (response.status_code, response.json()['code']) == (status.HTTP_403_FORBIDDEN, 'operator_only')


async def test_only_sent_fields_change(client: AsyncClient, mine: dict):
    lorebook = await create(client, mine)

    renamed = (await client.patch(url(lorebook), json={'name': '새 이름'}, headers=mine)).json()
    emptied = (await client.patch(url(lorebook), json={'entries': []}, headers=mine)).json()

    assert (renamed['name'], len(renamed['entries']), renamed['description']) == ('새 이름', 2, '메모')
    assert emptied['entries'] == []


@pytest.mark.parametrize(
    'entries',
    [
        [CITY, {**EMPEROR, 'id': 'city'}],
        [{**CITY, 'keywords': ['수도', '수도 ']}],
        [{**CITY, 'keywords': ['Rome', 'rome']}],
        [{**CITY, 'keywords': [f'k{number}' for number in range(LORE_ENTRY_MAX_KEYWORDS + 1)]}],
        [{**CITY, 'content': '  '}],
        [{**CITY, 'content': 'x' * (LORE_ENTRY_CONTENT_MAX_LENGTH + 1)}],
        [{**CITY, 'kind': 'weapon'}],
        [{**CITY, 'id': '한글'}],
        [{**CITY, 'id': f'e{number}'} for number in range(LOREBOOK_MAX_ENTRIES + 1)],
    ],
)
async def test_bad_entries_are_refused(client: AsyncClient, mine: dict, entries: list):
    response = await client.post(LOREBOOKS_URL, json={'name': '설정', 'entries': entries}, headers=mine)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize('body', [{'name': None}, {'entries': None}, {'description': None}, {'name': ''}])
async def test_nulls_and_empty_names_are_refused(client: AsyncClient, mine: dict, body: dict):
    lorebook = await create(client, mine)

    response = await client.patch(url(lorebook), json=body, headers=mine)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_list_is_mine_with_entry_counts(client: AsyncClient, mine: dict, theirs: dict):
    await create(client, mine)
    await create(client, theirs)
    latest = await create(client, mine, name='두 번째', entries=[])

    page = (await client.get(LOREBOOKS_URL, headers=mine)).json()

    assert page['total'] == 2
    assert [(item['name'], item['entry_count']) for item in page['items']] == [('두 번째', 0), ('제국의 설정', 2)]
    assert page['items'][0]['id'] == latest['id']


async def test_someone_elses_lorebook_is_404_everywhere(client: AsyncClient, mine: dict, theirs: dict):
    lorebook = await create(client, theirs)
    await publish(client, theirs, lorebook)

    responses = [
        await client.get(url(lorebook), headers=mine),
        await client.patch(url(lorebook), json={'name': '뺏기'}, headers=mine),
        await client.delete(url(lorebook), headers=mine),
        await publish(client, mine, lorebook),
        await client.get(url(lorebook, 'versions'), headers=mine),
        await client.get(url(lorebook, 'versions', '1'), headers=mine),
    ]

    assert {response.status_code for response in responses} == {status.HTTP_404_NOT_FOUND}
    assert responses[0].json()['code'] == 'lorebook_not_found'


# --- 판 ---


async def test_publishing_freezes_the_entries(client: AsyncClient, mine: dict):
    lorebook = await create(client, mine)

    first = await publish(client, mine, lorebook, note='처음')
    await client.patch(url(lorebook), json={'entries': [CITY]}, headers=mine)
    second = (await publish(client, mine, lorebook)).json()

    assert first.status_code == status.HTTP_201_CREATED
    body = first.json()
    assert (body['number'], body['note']) == (1, '처음')
    assert body['document'] == {
        'format': LOREBOOK_FORMAT,
        'name': '제국의 설정',
        'entries': [{**CITY, 'kind': 'other', 'constant': False}, {**EMPEROR, 'keywords': []}],
    }
    assert (second['number'], len(second['document']['entries'])) == (2, 1)
    kept = (await client.get(url(lorebook, 'versions', '1'), headers=mine)).json()
    assert len(kept['document']['entries']) == 2
    listed = (await client.get(url(lorebook, 'versions'), headers=mine)).json()
    assert [version['number'] for version in listed] == [2, 1]
    assert (await client.get(url(lorebook), headers=mine)).json()['latest_version'] == 2


async def test_a_missing_version_is_404(client: AsyncClient, mine: dict):
    lorebook = await create(client, mine)

    response = await client.get(url(lorebook, 'versions', '1'), headers=mine)

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_deleting_removes_the_versions(client: AsyncClient, session: AsyncSession, mine: dict):
    lorebook = await create(client, mine)
    await publish(client, mine, lorebook)

    response = await client.delete(url(lorebook), headers=mine)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert (await client.get(url(lorebook), headers=mine)).status_code == status.HTTP_404_NOT_FOUND
    assert await session.scalar(select(func.count()).select_from(LorebookVersion)) == 0
