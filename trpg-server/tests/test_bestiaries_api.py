# trpg-server/tests/test_bestiaries_api.py

"""
몬스터 도감 API 를 검증한다.

모든 자산에 공통인 규칙은 세계관의 테스트가 이미 검증한다. 여기서는 도감만의 것을 본다.
도감에는 몬스터가 딸린다. 그래서 생기는 규칙이 셋이다.
  - 몬스터는 도감의 주인만 다룬다. 몬스터의 ID 를 알아도 남의 도감의 몬스터는 건드릴 수 없다.
  - 타입은 정해진 값 중 하나다. 도감 하나에 몬스터는 정해진 개수까지다.
  - 몬스터가 바뀌면 도감이 바뀐 것이다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.bestiaries import service
from app.assets.bestiaries.models import (
    MONSTER_CONTENT_MAX_LENGTH,
    MONSTER_NAME_MAX_LENGTH,
    Bestiary,
    Monster,
    MonsterKind,
)
from app.assets.models import Asset, AssetType
from app.main import API_PREFIX
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

BESTIARIES_URL = f'{API_PREFIX}/bestiaries'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'

# 테스트에 쓰는 예시 도감과 몬스터. 내용은 아무 뜻이 없다
TITLE = '지하 수로의 것들'
NAME = '수로 쥐'
CONTENT = '개만 한 쥐. 무리로 다니고 불빛을 싫어한다. 하나가 물면 나머지가 몰려든다.'


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


def monsters_url(bestiary: dict) -> str:
    """도감의 몬스터 주소."""
    return f'{BESTIARIES_URL}/{bestiary["id"]}/monsters'


async def create_bestiary(client: AsyncClient, headers: dict[str, str], **fields) -> dict:
    """API 로 도감 하나를 만들고 응답의 본문을 돌려준다."""
    body = {'title': TITLE}
    body.update(fields)
    response = await client.post(BESTIARIES_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def add_monster(client: AsyncClient, headers: dict[str, str], bestiary: dict, **fields) -> dict:
    """API 로 몬스터 하나를 더하고 응답의 본문을 돌려준다."""
    body = {'name': NAME}
    body.update(fields)
    response = await client.post(monsters_url(bestiary), json=body, headers=headers)
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
        ('POST', '/11111111-2222-4333-8444-555555555555/monsters'),
        ('GET', '/11111111-2222-4333-8444-555555555555/monsters'),
        ('PATCH', '/11111111-2222-4333-8444-555555555555/monsters/22222222-2222-4333-8444-555555555555'),
        ('DELETE', '/11111111-2222-4333-8444-555555555555/monsters/22222222-2222-4333-8444-555555555555'),
    ],
)
async def test_every_address_requires_login(client: AsyncClient, method: str, path: str):
    response = await client.request(method, f'{BESTIARIES_URL}{path}', json={'title': '도감', 'name': '몬스터'})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 도감 ---


async def test_creates_a_bestiary_with_no_monsters(client: AsyncClient, my_headers: dict[str, str]):
    bestiary = await create_bestiary(client, my_headers)

    assert bestiary['title'] == TITLE
    # 도감 자신에게는 공통 칸만 있다
    assert set(bestiary) == {'id', 'title', 'description', 'visibility', 'created_at', 'updated_at'}
    assert (await client.get(monsters_url(bestiary), headers=my_headers)).json() == []


async def test_a_bestiary_is_saved_as_the_bestiary_type(
    client: AsyncClient, my_headers: dict[str, str], session: AsyncSession
):
    bestiary = await create_bestiary(client, my_headers)

    saved_type = await session.scalar(text('SELECT type FROM assets WHERE id = :id'), {'id': bestiary['id']})

    assert saved_type == AssetType.BESTIARY


async def test_lists_only_my_bestiaries(client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]):
    mine = await create_bestiary(client, my_headers)
    await create_bestiary(client, their_headers)
    # 다른 종류의 자산은 도감의 목록에 나오지 않는다
    await client.post(LOREBOOKS_URL, json={'title': '로어북'}, headers=my_headers)

    response = await client.get(BESTIARIES_URL, headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    assert [item['id'] for item in response.json()['items']] == [mine['id']]
    assert response.json()['total'] == 1


async def test_updates_the_title_of_a_bestiary(client: AsyncClient, my_headers: dict[str, str]):
    bestiary = await create_bestiary(client, my_headers)

    response = await client.patch(f'{BESTIARIES_URL}/{bestiary["id"]}', json={'title': '새 제목'}, headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['title'] == '새 제목'


@pytest.mark.parametrize(
    'extra',
    [
        # 몬스터는 몬스터의 주소로만 더한다
        {'monsters': [{'name': NAME}]},
        # 등급은 시나리오에서만 정한다
        {'rating': 'adult'},
    ],
)
async def test_a_bestiary_takes_only_the_common_fields(client: AsyncClient, my_headers: dict[str, str], extra: dict):
    response = await client.post(BESTIARIES_URL, json={'title': TITLE, **extra}, headers=my_headers)

    # 모르는 칸을 조용히 버리지 않고 거부한다
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_deletes_a_bestiary(client: AsyncClient, my_headers: dict[str, str]):
    bestiary = await create_bestiary(client, my_headers)
    url = f'{BESTIARIES_URL}/{bestiary["id"]}'

    response = await client.delete(url, headers=my_headers)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert (await client.get(url, headers=my_headers)).status_code == status.HTTP_404_NOT_FOUND


# --- 몬스터 만들기 ---


async def test_adds_a_monster(client: AsyncClient, my_headers: dict[str, str]):
    bestiary = await create_bestiary(client, my_headers)

    response = await client.post(
        monsters_url(bestiary), json={'name': NAME, 'content': CONTENT, 'kind': 'beast'}, headers=my_headers
    )

    assert response.status_code == status.HTTP_201_CREATED
    monster = response.json()
    # 숫자(시트)는 몬스터에 없다. 시나리오가 룰북에 맞춰 적는다
    assert set(monster) == {'id', 'name', 'content', 'kind', 'unique', 'copied_from', 'created_at', 'updated_at'}
    assert monster['name'] == NAME
    assert monster['content'] == CONTENT
    assert monster['kind'] == MonsterKind.BEAST


@pytest.mark.parametrize('kind', list(MonsterKind))
async def test_a_monster_has_a_kind(client: AsyncClient, my_headers: dict[str, str], kind: MonsterKind):
    bestiary = await create_bestiary(client, my_headers)

    response = await client.post(monsters_url(bestiary), json={'name': NAME, 'kind': kind}, headers=my_headers)

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()['kind'] == kind
    assert (await client.get(monsters_url(bestiary), headers=my_headers)).json()[0]['kind'] == kind


async def test_a_monster_needs_only_a_name(client: AsyncClient, my_headers: dict[str, str]):
    bestiary = await create_bestiary(client, my_headers)

    monster = await add_monster(client, my_headers, bestiary)

    assert monster['content'] == ''
    # 타입을 적지 않으면 기타다
    assert monster['kind'] == MonsterKind.OTHER


async def test_the_name_is_trimmed(client: AsyncClient, my_headers: dict[str, str]):
    bestiary = await create_bestiary(client, my_headers)

    monster = await add_monster(client, my_headers, bestiary, name='  수로 쥐 ')

    assert monster['name'] == '수로 쥐'


@pytest.mark.parametrize(
    'body',
    [
        {},
        {'name': '   '},
        {'name': '가' * (MONSTER_NAME_MAX_LENGTH + 1)},
        {'name': '몬스터', 'content': '가' * (MONSTER_CONTENT_MAX_LENGTH + 1)},
        {'name': '몬스터', 'kind': 'dragon'},
        # 화면에 보이는 이름이 아니라 값으로 보낸다
        {'name': '몬스터', 'kind': '야수'},
        {'name': '몬스터', 'kind': None},
        # 숫자는 도감이 아니라 시나리오에 적는다
        {'name': '몬스터', 'sheet': {'abilities': {'str': 10}, 'max_hp': 5}},
        {'name': '몬스터', 'bestiary_id': NO_SUCH_ID},
    ],
)
async def test_rejects_a_bad_monster(client: AsyncClient, my_headers: dict[str, str], body: dict):
    bestiary = await create_bestiary(client, my_headers)

    response = await client.post(monsters_url(bestiary), json=body, headers=my_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert (await client.get(monsters_url(bestiary), headers=my_headers)).json() == []


async def test_accepts_the_longest_name_and_content(client: AsyncClient, my_headers: dict[str, str]):
    bestiary = await create_bestiary(client, my_headers)
    name = '가' * MONSTER_NAME_MAX_LENGTH
    content = '나' * MONSTER_CONTENT_MAX_LENGTH

    monster = await add_monster(client, my_headers, bestiary, name=name, content=content)

    assert monster['name'] == name
    assert monster['content'] == content


# --- 몬스터 읽기 ---


async def test_lists_monsters_in_the_order_they_were_added(client: AsyncClient, my_headers: dict[str, str]):
    bestiary = await create_bestiary(client, my_headers)
    first = await add_monster(client, my_headers, bestiary, name='첫째')
    second = await add_monster(client, my_headers, bestiary, name='둘째')
    third = await add_monster(client, my_headers, bestiary, name='셋째')

    response = await client.get(monsters_url(bestiary), headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    assert [monster['id'] for monster in response.json()] == [first['id'], second['id'], third['id']]


async def test_monsters_of_different_bestiaries_do_not_mix(client: AsyncClient, my_headers: dict[str, str]):
    sewers = await create_bestiary(client, my_headers, title='수로')
    tombs = await create_bestiary(client, my_headers, title='무덤')
    rat = await add_monster(client, my_headers, sewers, name='수로 쥐')
    skeleton = await add_monster(client, my_headers, tombs, name='해골', kind='undead')

    sewer_monsters = (await client.get(monsters_url(sewers), headers=my_headers)).json()
    tomb_monsters = (await client.get(monsters_url(tombs), headers=my_headers)).json()

    assert [monster['id'] for monster in sewer_monsters] == [rat['id']]
    assert [monster['id'] for monster in tomb_monsters] == [skeleton['id']]


# --- 몬스터 고치기 ---


async def test_updates_only_the_fields_that_were_sent(client: AsyncClient, my_headers: dict[str, str]):
    bestiary = await create_bestiary(client, my_headers)
    monster = await add_monster(client, my_headers, bestiary, content='옛 내용', kind='beast')

    response = await client.patch(
        f'{monsters_url(bestiary)}/{monster["id"]}', json={'content': CONTENT}, headers=my_headers
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body['content'] == CONTENT
    assert body['name'] == NAME
    assert body['kind'] == MonsterKind.BEAST
    assert body['updated_at'] > monster['updated_at']


async def test_updates_the_kind_of_a_monster(client: AsyncClient, my_headers: dict[str, str]):
    bestiary = await create_bestiary(client, my_headers)
    monster = await add_monster(client, my_headers, bestiary, content=CONTENT)
    url = f'{monsters_url(bestiary)}/{monster["id"]}'

    response = await client.patch(url, json={'kind': MonsterKind.UNDEAD}, headers=my_headers)
    unchanged = await client.patch(url, json={'kind': None, 'name': None}, headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['kind'] == MonsterKind.UNDEAD
    assert response.json()['content'] == CONTENT
    # null 은 "보내지 않았다"다. 타입도 이름도 지우지 않는다
    assert unchanged.json()['kind'] == MonsterKind.UNDEAD
    assert unchanged.json()['name'] == NAME


async def test_an_empty_string_clears_the_content(client: AsyncClient, my_headers: dict[str, str]):
    bestiary = await create_bestiary(client, my_headers)
    monster = await add_monster(client, my_headers, bestiary, content=CONTENT)

    response = await client.patch(f'{monsters_url(bestiary)}/{monster["id"]}', json={'content': ''}, headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['content'] == ''


async def test_rejects_a_bad_update(client: AsyncClient, my_headers: dict[str, str]):
    bestiary = await create_bestiary(client, my_headers)
    monster = await add_monster(client, my_headers, bestiary, content=CONTENT)
    url = f'{monsters_url(bestiary)}/{monster["id"]}'

    blank = await client.patch(url, json={'name': '  '}, headers=my_headers)
    unknown = await client.patch(url, json={'title': '제목'}, headers=my_headers)
    bad_kind = await client.patch(url, json={'kind': 'dragon'}, headers=my_headers)

    assert blank.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert unknown.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert bad_kind.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    stored = (await client.get(monsters_url(bestiary), headers=my_headers)).json()[0]
    assert stored['name'] == NAME
    assert stored['kind'] == MonsterKind.OTHER


# --- 몬스터 지우기 ---


async def test_deletes_a_monster(client: AsyncClient, my_headers: dict[str, str], session: AsyncSession):
    bestiary = await create_bestiary(client, my_headers)
    kept = await add_monster(client, my_headers, bestiary, name='남는 몬스터')
    removed = await add_monster(client, my_headers, bestiary, name='지울 몬스터')
    url = f'{monsters_url(bestiary)}/{removed["id"]}'

    response = await client.delete(url, headers=my_headers)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    listed = (await client.get(monsters_url(bestiary), headers=my_headers)).json()
    assert [monster['id'] for monster in listed] == [kept['id']]
    # 몬스터는 자산과 달리 행을 실제로 지운다
    assert await session.scalar(text('SELECT count(*) FROM monsters WHERE id = :id'), {'id': removed['id']}) == 0
    assert (await client.delete(url, headers=my_headers)).status_code == status.HTTP_404_NOT_FOUND


# --- 몬스터는 도감의 주인만 다룬다 ---


async def test_someone_elses_monsters_look_like_they_do_not_exist(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    theirs = await create_bestiary(client, their_headers)
    monster = await add_monster(client, their_headers, theirs, content=CONTENT)
    url = f'{monsters_url(theirs)}/{monster["id"]}'

    listed = await client.get(monsters_url(theirs), headers=my_headers)
    added = await client.post(monsters_url(theirs), json={'name': '끼워 넣음'}, headers=my_headers)
    updated = await client.patch(url, json={'name': '빼앗음'}, headers=my_headers)
    deleted = await client.delete(url, headers=my_headers)

    assert listed.status_code == status.HTTP_404_NOT_FOUND
    assert added.status_code == status.HTTP_404_NOT_FOUND
    assert updated.status_code == status.HTTP_404_NOT_FOUND
    assert deleted.status_code == status.HTTP_404_NOT_FOUND
    assert CONTENT not in listed.text
    # 그대로 남아 있다
    assert (await client.get(monsters_url(theirs), headers=their_headers)).json() == [monster]


async def test_a_monster_cannot_be_reached_through_my_own_bestiary(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    theirs = await create_bestiary(client, their_headers)
    their_monster = await add_monster(client, their_headers, theirs)
    mine = await create_bestiary(client, my_headers)

    # 주소의 도감은 내 것이고, 몬스터의 ID 는 남의 것이다
    url = f'{monsters_url(mine)}/{their_monster["id"]}'
    updated = await client.patch(url, json={'name': '빼앗음'}, headers=my_headers)
    deleted = await client.delete(url, headers=my_headers)

    assert updated.status_code == status.HTTP_404_NOT_FOUND
    assert deleted.status_code == status.HTTP_404_NOT_FOUND
    assert (await client.get(monsters_url(theirs), headers=their_headers)).json() == [their_monster]


async def test_monsters_cannot_be_added_to_another_type_of_asset(client: AsyncClient, my_headers: dict[str, str]):
    lorebook = (await client.post(LOREBOOKS_URL, json={'title': '로어북'}, headers=my_headers)).json()

    response = await client.post(f'{BESTIARIES_URL}/{lorebook["id"]}/monsters', json={'name': NAME}, headers=my_headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_a_bestiary_cannot_be_read_as_a_lorebook(client: AsyncClient, my_headers: dict[str, str]):
    bestiary = await create_bestiary(client, my_headers)

    response = await client.get(f'{LOREBOOKS_URL}/{bestiary["id"]}/entries', headers=my_headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_monsters_of_a_deleted_bestiary_cannot_be_reached(client: AsyncClient, my_headers: dict[str, str]):
    bestiary = await create_bestiary(client, my_headers)
    monster = await add_monster(client, my_headers, bestiary)
    await client.delete(f'{BESTIARIES_URL}/{bestiary["id"]}', headers=my_headers)

    listed = await client.get(monsters_url(bestiary), headers=my_headers)
    added = await client.post(monsters_url(bestiary), json={'name': NAME}, headers=my_headers)
    updated = await client.patch(f'{monsters_url(bestiary)}/{monster["id"]}', json={'name': '바꿈'}, headers=my_headers)

    assert listed.status_code == status.HTTP_404_NOT_FOUND
    assert added.status_code == status.HTTP_404_NOT_FOUND
    assert updated.status_code == status.HTTP_404_NOT_FOUND


# --- 몬스터가 바뀌면 도감이 바뀐 것이다 ---


async def test_changing_a_monster_updates_the_bestiary(client: AsyncClient, my_headers: dict[str, str]):
    bestiary = await create_bestiary(client, my_headers)
    url = f'{BESTIARIES_URL}/{bestiary["id"]}'

    monster = await add_monster(client, my_headers, bestiary)
    after_adding = (await client.get(url, headers=my_headers)).json()['updated_at']
    await client.patch(f'{monsters_url(bestiary)}/{monster["id"]}', json={'content': CONTENT}, headers=my_headers)
    after_updating = (await client.get(url, headers=my_headers)).json()['updated_at']
    await client.delete(f'{monsters_url(bestiary)}/{monster["id"]}', headers=my_headers)
    after_deleting = (await client.get(url, headers=my_headers)).json()['updated_at']

    assert bestiary['updated_at'] < after_adding < after_updating < after_deleting


# --- 몬스터의 수 ---


async def test_a_full_bestiary_takes_no_more_monsters(
    client: AsyncClient, my_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    # 100개를 만들지 않고 상한을 낮춰서 본다
    monkeypatch.setattr(service, 'BESTIARY_MAX_MONSTERS', 2)
    bestiary = await create_bestiary(client, my_headers)
    await add_monster(client, my_headers, bestiary, name='첫째')
    second = await add_monster(client, my_headers, bestiary, name='둘째')

    full = await client.post(monsters_url(bestiary), json={'name': '셋째'}, headers=my_headers)

    assert full.status_code == status.HTTP_409_CONFLICT
    assert len((await client.get(monsters_url(bestiary), headers=my_headers)).json()) == 2

    # 하나를 지우면 자리가 난다
    await client.delete(f'{monsters_url(bestiary)}/{second["id"]}', headers=my_headers)
    await add_monster(client, my_headers, bestiary, name='셋째')


async def test_the_limit_is_counted_for_each_bestiary(
    client: AsyncClient, my_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(service, 'BESTIARY_MAX_MONSTERS', 1)
    full = await create_bestiary(client, my_headers, title='가득 찬 도감')
    await add_monster(client, my_headers, full)
    empty = await create_bestiary(client, my_headers, title='빈 도감')

    response = await client.post(monsters_url(empty), json={'name': NAME}, headers=my_headers)

    assert response.status_code == status.HTTP_201_CREATED


# --- DB 의 마지막 방어선 ---


async def make_bestiary(session: AsyncSession) -> uuid.UUID:
    """서비스를 거치지 않고 도감 하나를 저장한다."""
    bestiary = Bestiary(asset=Asset(owner_id=ME, type=AssetType.BESTIARY, title='도감'))
    session.add(bestiary)
    await session.commit()
    return bestiary.asset_id


async def test_the_database_rejects_a_name_that_is_too_long(session: AsyncSession):
    bestiary_id = await make_bestiary(session)
    session.add(Monster(bestiary_id=bestiary_id, name='가' * (MONSTER_NAME_MAX_LENGTH + 1)))

    # 칸의 크기(varchar)를 넘는 값이다. 제약의 위반이 아니라 값의 오류로 거부된다
    with pytest.raises(DBAPIError):
        await session.commit()


async def test_the_database_rejects_content_that_is_too_long(session: AsyncSession):
    bestiary_id = await make_bestiary(session)
    session.add(Monster(bestiary_id=bestiary_id, name='몬스터', content='가' * (MONSTER_CONTENT_MAX_LENGTH + 1)))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_rejects_an_unknown_kind(session: AsyncSession):
    bestiary_id = await make_bestiary(session)
    session.add(Monster(bestiary_id=bestiary_id, name='몬스터', kind='dragon'))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_rejects_a_monster_without_a_bestiary(session: AsyncSession):
    session.add(Monster(bestiary_id=uuid.UUID(NO_SUCH_ID), name='몬스터'))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_rejects_an_unknown_asset_type(session: AsyncSession):
    # 자산의 종류도 정해진 값뿐이다. 도감이 더해진 뒤에도 그 밖의 값은 막는다
    session.add(Asset(owner_id=ME, type='monster', title='몬스터'))

    with pytest.raises(IntegrityError):
        await session.commit()
