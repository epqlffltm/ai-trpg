# game-server/tests/test_lorebooks_api.py

"""
로어북 API 를 검증한다.

모든 자산에 공통인 규칙은 세계관의 테스트가 이미 검증한다. 여기서는 로어북만의 것을 본다.
로어북에는 항목이 딸린다. 그래서 생기는 규칙이 셋이다.
  - 항목은 로어북의 주인만 다룬다. 항목의 ID 를 알아도 남의 로어북의 항목은 건드릴 수 없다.
  - 키워드는 다섯 개까지, 로어북 하나에 항목은 정해진 개수까지다.
  - 항목이 바뀌면 로어북이 바뀐 것이다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.lorebooks import service
from app.assets.models import (
    LORE_ENTRY_CONTENT_MAX_LENGTH,
    LORE_ENTRY_MAX_KEYWORDS,
    LORE_ENTRY_NAME_MAX_LENGTH,
    LORE_KEYWORD_MAX_LENGTH,
    Asset,
    AssetType,
    Lorebook,
    LoreEntry,
    LoreKind,
)
from app.main import API_PREFIX
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
WORLDS_URL = f'{API_PREFIX}/worlds'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'

# 테스트에 쓰는 예시 로어북과 항목. 내용은 아무 뜻이 없다
TITLE = '폭주족 인명사전'
NAME = '매지컬 스미스'
KEYWORDS = ['스미스', '마법소년', '드워프']
CONTENT = '둘을 쫓는 추격자. 마법소년 차림의 드워프다. 변신할 때마다 망치가 커진다.'


@pytest.fixture
def my_headers(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말."""
    return bearer(signing_key, ME)


@pytest.fixture
def their_headers(signing_key: SigningKey) -> dict[str, str]:
    """다른 사람의 토큰이 실린 머리말."""
    return bearer(signing_key, SOMEONE_ELSE)


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


def entries_url(lorebook: dict) -> str:
    """로어북의 항목 주소."""
    return f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'


async def create_lorebook(client: AsyncClient, headers: dict[str, str], **fields) -> dict:
    """API 로 로어북 하나를 만들고 응답의 본문을 돌려준다."""
    body = {'title': TITLE}
    body.update(fields)
    response = await client.post(LOREBOOKS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def add_entry(client: AsyncClient, headers: dict[str, str], lorebook: dict, **fields) -> dict:
    """API 로 항목 하나를 더하고 응답의 본문을 돌려준다."""
    body = {'name': NAME}
    body.update(fields)
    response = await client.post(entries_url(lorebook), json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


# --- 로그인 ---


@pytest.mark.parametrize(
    ('method', 'path'),
    [
        ('POST', ''),
        ('GET', ''),
        ('GET', '/11111111-2222-4333-8444-555555555555'),
        ('PATCH', '/11111111-2222-4333-8444-555555555555'),
        ('DELETE', '/11111111-2222-4333-8444-555555555555'),
        ('POST', '/11111111-2222-4333-8444-555555555555/entries'),
        ('GET', '/11111111-2222-4333-8444-555555555555/entries'),
        ('PATCH', '/11111111-2222-4333-8444-555555555555/entries/22222222-2222-4333-8444-555555555555'),
        ('DELETE', '/11111111-2222-4333-8444-555555555555/entries/22222222-2222-4333-8444-555555555555'),
    ],
)
async def test_every_address_requires_login(client: AsyncClient, method: str, path: str):
    response = await client.request(method, f'{LOREBOOKS_URL}{path}', json={'title': '로어북', 'name': '항목'})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 로어북 ---


async def test_creates_a_lorebook_with_no_entries(client: AsyncClient, my_headers: dict[str, str]):
    lorebook = await create_lorebook(client, my_headers)

    assert lorebook['title'] == TITLE
    # 로어북 자신에게는 공통 칸만 있다
    assert set(lorebook) == {'id', 'title', 'description', 'visibility', 'created_at', 'updated_at'}
    assert (await client.get(entries_url(lorebook), headers=my_headers)).json() == []


async def test_a_lorebook_is_saved_as_the_lorebook_type(
    client: AsyncClient, my_headers: dict[str, str], session: AsyncSession
):
    lorebook = await create_lorebook(client, my_headers)

    saved_type = await session.scalar(text('SELECT type FROM assets WHERE id = :id'), {'id': lorebook['id']})

    assert saved_type == AssetType.LOREBOOK


async def test_updates_the_title_of_a_lorebook(client: AsyncClient, my_headers: dict[str, str]):
    lorebook = await create_lorebook(client, my_headers)

    response = await client.patch(f'{LOREBOOKS_URL}/{lorebook["id"]}', json={'title': '새 제목'}, headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['title'] == '새 제목'


@pytest.mark.parametrize(
    'extra',
    [
        # 항목은 항목의 주소로만 더한다
        {'entries': [{'name': NAME}]},
        # 등급은 시나리오에서만 정한다
        {'rating': 'adult'},
    ],
)
async def test_a_lorebook_takes_only_the_common_fields(client: AsyncClient, my_headers: dict[str, str], extra: dict):
    response = await client.post(LOREBOOKS_URL, json={'title': TITLE, **extra}, headers=my_headers)

    # 모르는 칸을 조용히 버리지 않고 거부한다
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 항목 만들기 ---


async def test_adds_an_entry(client: AsyncClient, my_headers: dict[str, str]):
    lorebook = await create_lorebook(client, my_headers)

    response = await client.post(
        entries_url(lorebook), json={'name': NAME, 'keywords': KEYWORDS, 'content': CONTENT}, headers=my_headers
    )

    assert response.status_code == status.HTTP_201_CREATED
    entry = response.json()
    assert set(entry) == {'id', 'name', 'kind', 'keywords', 'content', 'created_at', 'updated_at'}
    assert entry['name'] == NAME
    assert entry['keywords'] == KEYWORDS
    assert entry['content'] == CONTENT


@pytest.mark.parametrize('kind', list(LoreKind))
async def test_an_entry_has_a_kind(client: AsyncClient, my_headers: dict[str, str], kind: LoreKind):
    lorebook = await create_lorebook(client, my_headers)

    response = await client.post(entries_url(lorebook), json={'name': NAME, 'kind': kind}, headers=my_headers)

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()['kind'] == kind
    assert (await client.get(entries_url(lorebook), headers=my_headers)).json()[0]['kind'] == kind


async def test_an_entry_needs_only_a_name(client: AsyncClient, my_headers: dict[str, str]):
    lorebook = await create_lorebook(client, my_headers)

    entry = await add_entry(client, my_headers, lorebook)

    assert entry['keywords'] == []
    assert entry['content'] == ''
    # 종류를 적지 않으면 기타다. 종류가 생기기 전의 항목과 같게 다뤄진다
    assert entry['kind'] == LoreKind.OTHER


async def test_keywords_are_trimmed(client: AsyncClient, my_headers: dict[str, str]):
    lorebook = await create_lorebook(client, my_headers)

    entry = await add_entry(client, my_headers, lorebook, keywords=['  스미스 ', '드워프'])

    assert entry['keywords'] == ['스미스', '드워프']


@pytest.mark.parametrize(
    'body',
    [
        {},
        {'name': '   '},
        {'name': '가' * (LORE_ENTRY_NAME_MAX_LENGTH + 1)},
        {'name': '항목', 'content': '가' * (LORE_ENTRY_CONTENT_MAX_LENGTH + 1)},
        {'name': '항목', 'keywords': [f'키워드{number}' for number in range(LORE_ENTRY_MAX_KEYWORDS + 1)]},
        {'name': '항목', 'keywords': ['가' * (LORE_KEYWORD_MAX_LENGTH + 1)]},
        {'name': '항목', 'keywords': ['   ']},
        {'name': '항목', 'keywords': ['스미스', '스미스']},
        # 대소문자만 다른 것도 같은 키워드다
        {'name': '항목', 'keywords': ['Smith', 'smith']},
        # 앞뒤 공백을 떼면 같아진다
        {'name': '항목', 'keywords': ['스미스', ' 스미스 ']},
        {'name': '항목', 'keywords': '스미스'},
        {'name': '항목', 'lorebook_id': NO_SUCH_ID},
        {'name': '항목', 'kind': 'monster'},
        # 화면에 보이는 이름이 아니라 값으로 보낸다
        {'name': '항목', 'kind': '인물'},
        {'name': '항목', 'kind': None},
    ],
)
async def test_rejects_a_bad_entry(client: AsyncClient, my_headers: dict[str, str], body: dict):
    lorebook = await create_lorebook(client, my_headers)

    response = await client.post(entries_url(lorebook), json=body, headers=my_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert (await client.get(entries_url(lorebook), headers=my_headers)).json() == []


async def test_accepts_the_most_keywords_allowed(client: AsyncClient, my_headers: dict[str, str]):
    lorebook = await create_lorebook(client, my_headers)
    keywords = [f'키워드{number}' for number in range(LORE_ENTRY_MAX_KEYWORDS)]

    entry = await add_entry(client, my_headers, lorebook, keywords=keywords)

    assert entry['keywords'] == keywords


# --- 항목 읽기 ---


async def test_lists_entries_in_the_order_they_were_added(client: AsyncClient, my_headers: dict[str, str]):
    lorebook = await create_lorebook(client, my_headers)
    first = await add_entry(client, my_headers, lorebook, name='첫째')
    second = await add_entry(client, my_headers, lorebook, name='둘째')
    third = await add_entry(client, my_headers, lorebook, name='셋째')

    response = await client.get(entries_url(lorebook), headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    assert [entry['id'] for entry in response.json()] == [first['id'], second['id'], third['id']]


async def test_entries_of_different_lorebooks_do_not_mix(client: AsyncClient, my_headers: dict[str, str]):
    people = await create_lorebook(client, my_headers, title='인물')
    places = await create_lorebook(client, my_headers, title='장소')
    person = await add_entry(client, my_headers, people, name='인물 항목')
    place = await add_entry(client, my_headers, places, name='장소 항목')

    people_entries = (await client.get(entries_url(people), headers=my_headers)).json()
    places_entries = (await client.get(entries_url(places), headers=my_headers)).json()

    assert [entry['id'] for entry in people_entries] == [person['id']]
    assert [entry['id'] for entry in places_entries] == [place['id']]


# --- 항목 고치기 ---


async def test_updates_only_the_fields_that_were_sent(client: AsyncClient, my_headers: dict[str, str]):
    lorebook = await create_lorebook(client, my_headers)
    entry = await add_entry(client, my_headers, lorebook, keywords=KEYWORDS, content='옛 내용')

    response = await client.patch(
        f'{entries_url(lorebook)}/{entry["id"]}', json={'content': CONTENT}, headers=my_headers
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body['content'] == CONTENT
    assert body['name'] == NAME
    assert body['keywords'] == KEYWORDS
    assert body['kind'] == LoreKind.OTHER
    assert body['updated_at'] > entry['updated_at']


async def test_updates_the_kind_of_an_entry(client: AsyncClient, my_headers: dict[str, str]):
    lorebook = await create_lorebook(client, my_headers)
    entry = await add_entry(client, my_headers, lorebook, keywords=KEYWORDS, content=CONTENT)
    url = f'{entries_url(lorebook)}/{entry["id"]}'

    response = await client.patch(url, json={'kind': LoreKind.PERSON}, headers=my_headers)
    unchanged = await client.patch(url, json={'kind': None}, headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['kind'] == LoreKind.PERSON
    assert response.json()['content'] == CONTENT
    # null 은 "보내지 않았다"다. 종류를 지우지 않는다
    assert unchanged.json()['kind'] == LoreKind.PERSON


async def test_an_empty_list_clears_the_keywords(client: AsyncClient, my_headers: dict[str, str]):
    lorebook = await create_lorebook(client, my_headers)
    entry = await add_entry(client, my_headers, lorebook, keywords=KEYWORDS)
    url = f'{entries_url(lorebook)}/{entry["id"]}'

    response = await client.patch(url, json={'keywords': []}, headers=my_headers)

    # 빈 목록은 "전부 없앤다"다. null("보내지 않았다")과 다르다
    assert response.status_code == status.HTTP_200_OK
    assert response.json()['keywords'] == []


async def test_null_does_not_clear_the_keywords(client: AsyncClient, my_headers: dict[str, str]):
    lorebook = await create_lorebook(client, my_headers)
    entry = await add_entry(client, my_headers, lorebook, keywords=KEYWORDS)

    response = await client.patch(
        f'{entries_url(lorebook)}/{entry["id"]}', json={'keywords': None, 'name': None}, headers=my_headers
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['keywords'] == KEYWORDS
    assert response.json()['name'] == NAME


async def test_rejects_a_bad_update(client: AsyncClient, my_headers: dict[str, str]):
    lorebook = await create_lorebook(client, my_headers)
    entry = await add_entry(client, my_headers, lorebook, keywords=KEYWORDS)
    url = f'{entries_url(lorebook)}/{entry["id"]}'

    too_many = await client.patch(url, json={'keywords': ['가', '나', '다', '라', '마', '바']}, headers=my_headers)
    unknown = await client.patch(url, json={'title': '제목'}, headers=my_headers)
    bad_kind = await client.patch(url, json={'kind': 'monster'}, headers=my_headers)

    assert too_many.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert unknown.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert bad_kind.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    stored = (await client.get(entries_url(lorebook), headers=my_headers)).json()[0]
    assert stored['keywords'] == KEYWORDS
    assert stored['kind'] == LoreKind.OTHER


# --- 항목 지우기 ---


async def test_deletes_an_entry(client: AsyncClient, my_headers: dict[str, str], session: AsyncSession):
    lorebook = await create_lorebook(client, my_headers)
    kept = await add_entry(client, my_headers, lorebook, name='남는 항목')
    removed = await add_entry(client, my_headers, lorebook, name='지울 항목')
    url = f'{entries_url(lorebook)}/{removed["id"]}'

    response = await client.delete(url, headers=my_headers)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert [entry['id'] for entry in (await client.get(entries_url(lorebook), headers=my_headers)).json()] == [
        kept['id']
    ]
    # 항목은 자산과 달리 행을 실제로 지운다
    assert await session.scalar(text('SELECT count(*) FROM lore_entries WHERE id = :id'), {'id': removed['id']}) == 0
    assert (await client.delete(url, headers=my_headers)).status_code == status.HTTP_404_NOT_FOUND


# --- 항목은 로어북의 주인만 다룬다 ---


async def test_someone_elses_entries_look_like_they_do_not_exist(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    theirs = await create_lorebook(client, their_headers)
    entry = await add_entry(client, their_headers, theirs, content=CONTENT)
    url = f'{entries_url(theirs)}/{entry["id"]}'

    listed = await client.get(entries_url(theirs), headers=my_headers)
    added = await client.post(entries_url(theirs), json={'name': '끼워 넣음'}, headers=my_headers)
    updated = await client.patch(url, json={'name': '빼앗음'}, headers=my_headers)
    deleted = await client.delete(url, headers=my_headers)

    assert listed.status_code == status.HTTP_404_NOT_FOUND
    assert added.status_code == status.HTTP_404_NOT_FOUND
    assert updated.status_code == status.HTTP_404_NOT_FOUND
    assert deleted.status_code == status.HTTP_404_NOT_FOUND
    assert CONTENT not in listed.text
    # 그대로 남아 있다
    assert (await client.get(entries_url(theirs), headers=their_headers)).json() == [entry]


async def test_an_entry_cannot_be_reached_through_my_own_lorebook(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    theirs = await create_lorebook(client, their_headers)
    their_entry = await add_entry(client, their_headers, theirs)
    mine = await create_lorebook(client, my_headers)

    # 주소의 로어북은 내 것이고, 항목의 ID 는 남의 것이다
    url = f'{entries_url(mine)}/{their_entry["id"]}'
    updated = await client.patch(url, json={'name': '빼앗음'}, headers=my_headers)
    deleted = await client.delete(url, headers=my_headers)

    assert updated.status_code == status.HTTP_404_NOT_FOUND
    assert deleted.status_code == status.HTTP_404_NOT_FOUND
    assert (await client.get(entries_url(theirs), headers=their_headers)).json() == [their_entry]


async def test_entries_cannot_be_added_to_another_type_of_asset(client: AsyncClient, my_headers: dict[str, str]):
    world = (await client.post(WORLDS_URL, json={'title': '세계'}, headers=my_headers)).json()

    response = await client.post(f'{LOREBOOKS_URL}/{world["id"]}/entries', json={'name': NAME}, headers=my_headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_entries_of_a_deleted_lorebook_cannot_be_reached(client: AsyncClient, my_headers: dict[str, str]):
    lorebook = await create_lorebook(client, my_headers)
    entry = await add_entry(client, my_headers, lorebook)
    await client.delete(f'{LOREBOOKS_URL}/{lorebook["id"]}', headers=my_headers)

    listed = await client.get(entries_url(lorebook), headers=my_headers)
    added = await client.post(entries_url(lorebook), json={'name': NAME}, headers=my_headers)
    updated = await client.patch(f'{entries_url(lorebook)}/{entry["id"]}', json={'name': '바꿈'}, headers=my_headers)

    assert listed.status_code == status.HTTP_404_NOT_FOUND
    assert added.status_code == status.HTTP_404_NOT_FOUND
    assert updated.status_code == status.HTTP_404_NOT_FOUND


# --- 항목이 바뀌면 로어북이 바뀐 것이다 ---


async def test_changing_an_entry_updates_the_lorebook(client: AsyncClient, my_headers: dict[str, str]):
    lorebook = await create_lorebook(client, my_headers)
    url = f'{LOREBOOKS_URL}/{lorebook["id"]}'

    entry = await add_entry(client, my_headers, lorebook)
    after_adding = (await client.get(url, headers=my_headers)).json()['updated_at']
    await client.patch(f'{entries_url(lorebook)}/{entry["id"]}', json={'content': CONTENT}, headers=my_headers)
    after_updating = (await client.get(url, headers=my_headers)).json()['updated_at']
    await client.delete(f'{entries_url(lorebook)}/{entry["id"]}', headers=my_headers)
    after_deleting = (await client.get(url, headers=my_headers)).json()['updated_at']

    assert lorebook['updated_at'] < after_adding < after_updating < after_deleting


# --- 항목의 개수 ---


async def test_a_full_lorebook_takes_no_more_entries(
    client: AsyncClient, my_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    # 100개를 만들지 않고 상한을 낮춰서 본다
    monkeypatch.setattr(service, 'LOREBOOK_MAX_ENTRIES', 2)
    lorebook = await create_lorebook(client, my_headers)
    await add_entry(client, my_headers, lorebook, name='첫째')
    second = await add_entry(client, my_headers, lorebook, name='둘째')

    full = await client.post(entries_url(lorebook), json={'name': '셋째'}, headers=my_headers)

    assert full.status_code == status.HTTP_409_CONFLICT
    assert len((await client.get(entries_url(lorebook), headers=my_headers)).json()) == 2

    # 하나를 지우면 자리가 난다
    await client.delete(f'{entries_url(lorebook)}/{second["id"]}', headers=my_headers)
    await add_entry(client, my_headers, lorebook, name='셋째')


async def test_the_limit_is_counted_for_each_lorebook(
    client: AsyncClient, my_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(service, 'LOREBOOK_MAX_ENTRIES', 1)
    full = await create_lorebook(client, my_headers, title='가득 찬 로어북')
    await add_entry(client, my_headers, full)
    empty = await create_lorebook(client, my_headers, title='빈 로어북')

    response = await client.post(entries_url(empty), json={'name': NAME}, headers=my_headers)

    assert response.status_code == status.HTTP_201_CREATED


# --- DB 의 마지막 방어선 ---


async def make_lorebook(session: AsyncSession) -> uuid.UUID:
    """서비스를 거치지 않고 로어북 하나를 저장한다."""
    lorebook = Lorebook(asset=Asset(owner_id=ME, type=AssetType.LOREBOOK, title='로어북'))
    session.add(lorebook)
    await session.commit()
    return lorebook.asset_id


async def test_the_database_rejects_content_that_is_too_long(session: AsyncSession):
    lorebook_id = await make_lorebook(session)
    session.add(LoreEntry(lorebook_id=lorebook_id, name='항목', content='가' * (LORE_ENTRY_CONTENT_MAX_LENGTH + 1)))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_rejects_too_many_keywords(session: AsyncSession):
    lorebook_id = await make_lorebook(session)
    keywords = [f'키워드{number}' for number in range(LORE_ENTRY_MAX_KEYWORDS + 1)]
    session.add(LoreEntry(lorebook_id=lorebook_id, name='항목', keywords=keywords))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_rejects_an_unknown_kind(session: AsyncSession):
    lorebook_id = await make_lorebook(session)
    session.add(LoreEntry(lorebook_id=lorebook_id, name='항목', kind='monster'))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_fills_in_the_kind(session: AsyncSession):
    lorebook_id = await make_lorebook(session)

    # 종류 칸이 생기기 전처럼 종류 없이 넣은 줄은 기타가 된다(이미 있던 항목들이 이렇게 기타가 됐다)
    await session.execute(
        text(
            'INSERT INTO lore_entries (id, lorebook_id, name, keywords, content) '
            "VALUES (:id, :lorebook_id, :name, '{}', '')"
        ),
        {'id': uuid.uuid4(), 'lorebook_id': lorebook_id, 'name': '항목'},
    )
    kind = (await session.execute(text('SELECT kind FROM lore_entries'))).scalar_one()

    assert kind == LoreKind.OTHER


async def test_the_database_rejects_an_entry_without_a_lorebook(session: AsyncSession):
    session.add(LoreEntry(lorebook_id=uuid.UUID(NO_SUCH_ID), name='항목'))

    with pytest.raises(IntegrityError):
        await session.commit()
