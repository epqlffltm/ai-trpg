# game-server/tests/test_personas_api.py

"""
보관함 API 를 검증한다. 캐릭터를 만들고, 읽고, 고치고, 지운다.

보는 것은 넷이다.
  - 보관함은 주인만 본다. 남의 캐릭터는 없는 캐릭터다(404).
  - 능력치는 참고값이다. 모양만 보고, 어느 규칙에 맞는지는 보지 않는다.
  - 한 사람이 보관할 수 있는 수에 상한이 있다.
  - DB 가 마지막에 막는 것.
테이블에서 저장하는 것은 tests/test_persona_saving.py 가, 동시에 오는 요청은 tests/test_persona_locking.py 가 본다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from app.personas.models import PERSONA_MAX_PER_OWNER, Persona
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

PERSONAS_URL = f'{API_PREFIX}/personas'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
STRANGER = uuid.UUID('99999999-2222-4333-8444-555555555555')

DWARF = {'name': '드워프', 'description': '수염에 기름때가 묻었다.'}
STURDY = {'str': 12, 'dex': 12, 'con': 14, 'int': 12, 'wis': 12, 'cha': 12}


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말."""
    return bearer(signing_key, ME)


@pytest.fixture
def stranger(signing_key: SigningKey) -> dict[str, str]:
    """다른 사람의 머리말."""
    return bearer(signing_key, STRANGER)


async def create(client: AsyncClient, headers: dict[str, str], **body) -> dict:
    """보관함에 캐릭터를 만들고, 돌아온 것을 돌려준다."""
    response = await client.post(PERSONAS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def persona_url(persona: dict) -> str:
    return f'{PERSONAS_URL}/{persona["id"]}'


def fill_vault(session: AsyncSession, owner_id: uuid.UUID, count: int) -> None:
    """API 를 거치지 않고 보관함을 채운다. 상한을 보는 테스트가 요청을 쉰 번 보내지 않으려는 것이다."""
    session.add_all(Persona(owner_id=owner_id, name=f'엑스트라 {number}') for number in range(count))


# --- 만들기 ---


async def test_keeps_a_character(client: AsyncClient, me: dict[str, str]):
    response = await client.post(PERSONAS_URL, json={**DWARF, 'abilities': STURDY}, headers=me)

    assert response.status_code == status.HTTP_201_CREATED
    persona = response.json()
    assert (persona['name'], persona['description'], persona['abilities']) == (
        DWARF['name'],
        DWARF['description'],
        STURDY,
    )
    # 룰북의 제목은 테이블에서 저장할 때만 적힌다
    assert persona['rulebook_title'] is None


async def test_a_character_may_be_kept_as_words_only(client: AsyncClient, me: dict[str, str]):
    persona = await create(client, me, name='드워프')

    # 숫자는 그 테이블의 방식으로 그 자리에서 정한다
    assert (persona['description'], persona['abilities']) == ('', None)


async def test_the_numbers_are_not_checked_against_any_rules(client: AsyncClient, me: dict[str, str]):
    # 보관함에는 규칙이 없다. 이 숫자가 맞는지는 가져가는 테이블의 규칙이 정한다
    odd = {'luck': 1, 'sanity': 99}

    persona = await create(client, me, name='탐정', abilities=odd)

    assert persona['abilities'] == odd


@pytest.mark.parametrize(
    'body',
    [
        {},
        {'name': ''},
        {'name': '   '},
        {'name': '가' * 51},
        {'name': '드워프', 'description': '가' * 1001},
        {'name': '드워프', 'abilities': {'str': -1}},
        {'name': '드워프', 'abilities': {'Str': 10}},
        {'name': '드워프', 'abilities': {f'a{number}': 10 for number in range(13)}},
        # 룰북의 제목은 서버가 적는다. 받지 않는다
        {'name': '드워프', 'rulebook_title': '룰북'},
        {'name': '드워프', 'sheet': {'max_hp': 99}},
    ],
)
async def test_refuses_a_malformed_character(client: AsyncClient, me: dict[str, str], body: dict):
    response = await client.post(PERSONAS_URL, json=body, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_vault_has_a_limit(client: AsyncClient, me: dict[str, str], session: AsyncSession):
    fill_vault(session, ME, PERSONA_MAX_PER_OWNER)
    await session.commit()

    response = await client.post(PERSONAS_URL, json=DWARF, headers=me)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'vault_full'


async def test_the_limit_is_per_person(
    client: AsyncClient, me: dict[str, str], stranger: dict[str, str], session: AsyncSession
):
    fill_vault(session, STRANGER, PERSONA_MAX_PER_OWNER)
    await session.commit()

    response = await client.post(PERSONAS_URL, json=DWARF, headers=me)

    assert response.status_code == status.HTTP_201_CREATED


async def test_deleting_makes_room(client: AsyncClient, me: dict[str, str], session: AsyncSession):
    fill_vault(session, ME, PERSONA_MAX_PER_OWNER - 1)
    await session.commit()
    last = await create(client, me, **DWARF)

    await client.delete(persona_url(last), headers=me)
    response = await client.post(PERSONAS_URL, json=DWARF, headers=me)

    assert response.status_code == status.HTTP_201_CREATED


async def test_someone_without_a_token_has_no_vault(client: AsyncClient):
    response = await client.post(PERSONAS_URL, json=DWARF)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 읽기 ---


async def test_lists_my_characters_newest_first(client: AsyncClient, me: dict[str, str], stranger: dict[str, str]):
    first = await create(client, me, name='드워프')
    second = await create(client, me, name='엘프')
    await create(client, stranger, name='남의 캐릭터')

    page = (await client.get(PERSONAS_URL, headers=me)).json()

    assert page['total'] == 2
    assert [persona['id'] for persona in page['items']] == [second['id'], first['id']]


async def test_lists_one_page_at_a_time(client: AsyncClient, me: dict[str, str]):
    for name in ['드워프', '엘프', '오크']:
        await create(client, me, name=name)

    page = (await client.get(PERSONAS_URL, params={'limit': 2, 'offset': 2}, headers=me)).json()

    assert page['total'] == 3
    assert [persona['name'] for persona in page['items']] == ['드워프']


async def test_reads_one_of_my_characters(client: AsyncClient, me: dict[str, str]):
    persona = await create(client, me, **DWARF, abilities=STURDY)

    response = await client.get(persona_url(persona), headers=me)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == persona


async def test_someone_elses_character_does_not_exist(
    client: AsyncClient, me: dict[str, str], stranger: dict[str, str]
):
    persona = await create(client, me, **DWARF)

    # 남의 것도 없는 것과 같은 404 다. 403 이면 그 ID 의 캐릭터가 있다는 것이 드러난다
    read = await client.get(persona_url(persona), headers=stranger)
    changed = await client.put(persona_url(persona), json={'name': '오크'}, headers=stranger)
    deleted = await client.delete(persona_url(persona), headers=stranger)
    missing = await client.get(f'{PERSONAS_URL}/{uuid.uuid4()}', headers=me)

    assert [read.status_code, changed.status_code, deleted.status_code, missing.status_code] == [404] * 4
    assert (await client.get(persona_url(persona), headers=me)).json()['name'] == '드워프'


# --- 고치기, 지우기 ---


async def test_changing_replaces_the_whole_character(client: AsyncClient, me: dict[str, str]):
    persona = await create(client, me, **DWARF, abilities=STURDY)

    response = await client.put(persona_url(persona), json={'name': '오크'}, headers=me)

    # 보내지 않은 칸은 기본값으로 돌아간다. 능력치도 지워진다
    assert response.status_code == status.HTTP_200_OK
    changed = response.json()
    assert (changed['name'], changed['description'], changed['abilities']) == ('오크', '', None)
    assert changed['created_at'] == persona['created_at']


async def test_deletes_a_character(client: AsyncClient, me: dict[str, str], session: AsyncSession):
    persona = await create(client, me, **DWARF)

    deleted = await client.delete(persona_url(persona), headers=me)
    again = await client.delete(persona_url(persona), headers=me)

    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    assert again.status_code == status.HTTP_404_NOT_FOUND
    # 지웠다는 표시만 남기지 않고 행을 지운다. 아무도 가리키지 않는 행이다
    assert await session.scalar(text('SELECT count(*) FROM personas')) == 0


# --- DB 의 마지막 방어선 ---


async def test_words_only_are_kept_as_no_numbers_in_the_database(
    client: AsyncClient, me: dict[str, str], session: AsyncSession
):
    persona = await create(client, me, **DWARF, abilities=STURDY)
    await client.put(persona_url(persona), json=DWARF, headers=me)

    # 지운 능력치는 DB 에서도 없는 것(NULL)이어야 한다. JSON 의 null 이라는 값으로 남으면 DB 의 조건이 있다고 본다
    assert await session.scalar(text('SELECT abilities IS NULL FROM personas')) is True


@pytest.mark.parametrize(
    ('change', 'constraint'),
    [
        ("abilities = '5'", 'abilities_is_object'),
        ("abilities = 'null'", 'abilities_is_object'),
        ("description = repeat('가', 1001)", 'description_length'),
    ],
)
async def test_the_database_rejects_impossible_characters(
    client: AsyncClient, me: dict[str, str], session: AsyncSession, change: str, constraint: str
):
    await create(client, me, **DWARF)

    with pytest.raises(IntegrityError, match=constraint):
        await session.execute(text(f'UPDATE personas SET {change}'))
