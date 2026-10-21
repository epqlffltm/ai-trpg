# asset-server/tests/test_personas_api.py

"""
계정 페르소나 API(#565)를 검증한다. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 만들기: 이름만 필수다. 처음 만든 것이 기본이다. 모르는 칸(owner_id, revision, is_default)은 거부한다.
    나이와 성별은 적는 글이다. 무엇을 적어도 거르지 않는다.
  - 읽기: 자기 것만. 기본이 먼저, 그다음 만든 차례다. 남의 것은 없는 것과 같다(404).
  - 고치기: 보낸 칸만 바뀐다. 내용이 바뀔 때만 revision 이 오른다. 글의 칸에 null 은 거부하고, 그림은 null 로 뗀다.
  - 기본으로 두기: 하나만 기본이다. revision 은 그대로다.
  - 지우기: 행을 지운다. 기본을 지우면 가장 먼저 만든 것이 기본이 된다.
  - 상한: 한 사람마다 센다. 동시에 만들어도 넘지 않는다. 동시에 기본을 바꿔도 기본은 하나다.
  - DB: 한 사람의 기본은 하나, 글의 길이.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import TEST_USER_ID, FakeAuthServer, SigningKey, make_access_claims, make_token
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.main import API_PREFIX, create_app
from app.personas.models import (
    PERSONA_ADDRESS_MAX_LENGTH,
    PERSONA_DESCRIPTION_MAX_LENGTH,
    PERSONA_NAME_MAX_LENGTH,
    Persona,
)
from tests.conftest import make_client, make_test_settings

pytestmark = pytest.mark.usefixtures('clean_tables')

PERSONAS_URL = f'{API_PREFIX}/personas'
SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'
FULL = {
    'name': '한서윤',
    'description': '서울의 작은 출판사에서 일한다.',
    'image_id': '0b7c6f1e-2d3a-4b5c-8d9e-0f1a2b3c4d5e',
    'age': '스물일곱',
    'gender': '여성',
    'form_of_address': '선배',
    'speech_examples': '"그거 진짜야? 말도 안 돼."',
    'personality': '호기심이 많고 말이 빠르다.',
}


def bearer(signing_key: SigningKey, user_id: uuid.UUID = TEST_USER_ID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def theirs(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, SOMEONE_ELSE)


async def create(client: AsyncClient, headers: dict, **fields) -> dict:
    response = await client.post(PERSONAS_URL, json={'name': '나', **fields}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def url_of(persona: dict | str, suffix: str = '') -> str:
    persona_id = persona['id'] if isinstance(persona, dict) else persona
    return f'{PERSONAS_URL}/{persona_id}{suffix}'


async def names(client: AsyncClient, headers: dict) -> list[tuple[str, bool]]:
    response = await client.get(PERSONAS_URL, headers=headers)
    return [(persona['name'], persona['is_default']) for persona in response.json()]


# --- 로그인 ---


@pytest.mark.parametrize(
    ('method', 'path'),
    [
        ('POST', ''),
        ('GET', ''),
        ('GET', f'/{NO_SUCH_ID}'),
        ('PATCH', f'/{NO_SUCH_ID}'),
        ('PUT', f'/{NO_SUCH_ID}/default'),
        ('DELETE', f'/{NO_SUCH_ID}'),
    ],
)
async def test_every_address_requires_login(client: AsyncClient, method: str, path: str):
    response = await client.request(method, f'{PERSONAS_URL}{path}', json={})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 만들기 ---


async def test_the_first_persona_is_the_default(client: AsyncClient, mine: dict):
    first = await create(client, mine, **FULL)
    second = await create(client, mine, name='둘째')

    assert {key: first[key] for key in FULL} == FULL
    assert (first['is_default'], first['revision']) == (True, 1)
    assert (second['is_default'], second['revision']) == (False, 1)
    assert second['description'] == '' and second['image_id'] is None and second['age'] == ''


async def test_short_fields_are_trimmed_and_anything_can_be_written(client: AsyncClient, mine: dict):
    persona = await create(
        client, mine, name='  나  ', age=' 열두 살 ', gender=' 알 수 없음 ', form_of_address=' 주인님 '
    )

    # 나이와 성별은 적는 글이다. 무엇을 적어도 거르지 않는다
    assert (persona['name'], persona['age'], persona['gender'], persona['form_of_address']) == (
        '나',
        '열두 살',
        '알 수 없음',
        '주인님',
    )


@pytest.mark.parametrize(
    'body',
    [
        {},
        {'name': '   '},
        {'name': '가' * (PERSONA_NAME_MAX_LENGTH + 1)},
        {'name': '나', 'description': '가' * (PERSONA_DESCRIPTION_MAX_LENGTH + 1)},
        {'name': '나', 'form_of_address': '가' * (PERSONA_ADDRESS_MAX_LENGTH + 1)},
        {'name': '나', 'image_id': 'not-a-uuid'},
        {'name': '나', 'owner_id': str(SOMEONE_ELSE)},
        {'name': '나', 'revision': 9},
        {'name': '나', 'is_default': True},
    ],
)
async def test_a_bad_persona_is_refused(client: AsyncClient, mine: dict, body: dict, session: AsyncSession):
    response = await client.post(PERSONAS_URL, json=body, headers=mine)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert await session.scalar(select(func.count()).select_from(Persona)) == 0


# --- 읽기 ---


async def test_the_list_has_the_default_first_then_the_order_of_making(client: AsyncClient, mine: dict, theirs: dict):
    await create(client, mine, name='하나')
    second = await create(client, mine, name='둘')
    await create(client, mine, name='셋')
    await create(client, theirs, name='남의 것')
    await client.put(url_of(second, '/default'), headers=mine)

    assert await names(client, mine) == [('둘', True), ('하나', False), ('셋', False)]
    assert await names(client, theirs) == [('남의 것', True)]


async def test_someone_elses_persona_looks_like_it_does_not_exist(client: AsyncClient, mine: dict, theirs: dict):
    persona = await create(client, theirs, name='남의 것')

    responses = [
        await client.get(url_of(persona), headers=mine),
        await client.patch(url_of(persona), json={'name': '내 것'}, headers=mine),
        await client.put(url_of(persona, '/default'), headers=mine),
        await client.delete(url_of(persona), headers=mine),
        await client.get(url_of(NO_SUCH_ID), headers=mine),
    ]

    assert {response.status_code for response in responses} == {status.HTTP_404_NOT_FOUND}
    assert responses[0].json() == {'detail': '찾을 수 없습니다.'}
    assert (await client.get(url_of(persona), headers=theirs)).json()['name'] == '남의 것'


# --- 고치기 ---


async def test_only_the_sent_fields_change_and_the_revision_rises(client: AsyncClient, mine: dict):
    persona = await create(client, mine, **FULL)

    response = await client.patch(url_of(persona), json={'personality': '느긋하다.', 'age': ''}, headers=mine)

    body = response.json()
    assert response.status_code == status.HTTP_200_OK
    assert (body['personality'], body['age'], body['name'], body['revision']) == ('느긋하다.', '', FULL['name'], 2)
    assert body['updated_at'] >= persona['updated_at']


async def test_the_same_values_do_not_raise_the_revision(client: AsyncClient, mine: dict):
    persona = await create(client, mine, **FULL)

    same = await client.patch(url_of(persona), json={'name': FULL['name'], 'gender': FULL['gender']}, headers=mine)
    nothing = await client.patch(url_of(persona), json={}, headers=mine)

    assert same.json()['revision'] == nothing.json()['revision'] == 1


async def test_the_image_is_taken_off_with_null_but_text_fields_are_not(client: AsyncClient, mine: dict):
    persona = await create(client, mine, **FULL)

    taken_off = await client.patch(url_of(persona), json={'image_id': None}, headers=mine)
    refused = await client.patch(url_of(persona), json={'name': None}, headers=mine)
    default = await client.patch(url_of(persona), json={'is_default': False}, headers=mine)

    assert taken_off.json()['image_id'] is None and taken_off.json()['revision'] == 2
    assert refused.status_code == default.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'name' in refused.text


async def test_an_update_waits_for_another_and_reads_its_revision(
    client: AsyncClient, mine: dict, session: AsyncSession
):
    persona = await create(client, mine)
    # 다른 요청이 그 행을 잠그고 고치는 중이다(revision 을 5 로)
    locked = await session.scalar(select(Persona).where(Persona.id == uuid.UUID(persona['id'])).with_for_update())
    locked.revision = 5
    await session.flush()

    waiting = asyncio.create_task(client.patch(url_of(persona), json={'age': '하나'}, headers=mine))
    await asyncio.sleep(0.3)
    assert not waiting.done()
    await session.commit()
    response = await waiting

    # 기다렸다가 고친 뒤의 revision(5)을 읽고 올린다. 잠그지 않으면 처음 읽은 1 에서 올린 2 로 덮는다
    assert response.json()['revision'] == 6


# --- 기본으로 두기 ---


async def test_one_persona_is_the_default_and_the_revision_stays(client: AsyncClient, mine: dict):
    first = await create(client, mine, name='하나')
    second = await create(client, mine, name='둘')

    response = await client.put(url_of(second, '/default'), headers=mine)
    again = await client.put(url_of(second, '/default'), headers=mine)

    assert response.status_code == again.status_code == status.HTTP_200_OK
    assert (response.json()['is_default'], response.json()['revision']) == (True, 1)
    assert (await client.get(url_of(first), headers=mine)).json()['is_default'] is False


async def test_concurrent_defaults_leave_one_default(app: FastAPI, mine: dict, session: AsyncSession):
    async with make_client(app) as one, make_client(app) as two:
        personas = [await create(one, mine, name=f'{number}') for number in range(3)]

        await asyncio.gather(
            one.put(url_of(personas[1], '/default'), headers=mine),
            two.put(url_of(personas[2], '/default'), headers=mine),
        )

    defaults = await session.scalar(select(func.count()).select_from(Persona).where(Persona.is_default))
    assert defaults == 1


# --- 지우기 ---


async def test_deleting_the_default_makes_the_oldest_the_default(client: AsyncClient, mine: dict):
    await create(client, mine, name='하나')
    await create(client, mine, name='둘')
    third = await create(client, mine, name='셋')
    await client.put(url_of(third, '/default'), headers=mine)

    deleted = await client.delete(url_of(third), headers=mine)
    after_default = await names(client, mine)
    plain = await client.delete(url_of(await create(client, mine, name='넷')), headers=mine)

    assert deleted.status_code == plain.status_code == status.HTTP_204_NO_CONTENT
    assert after_default == [('하나', True), ('둘', False)]
    assert await names(client, mine) == [('하나', True), ('둘', False)]
    assert (await client.get(url_of(third), headers=mine)).status_code == status.HTTP_404_NOT_FOUND


async def test_deleting_the_last_one_leaves_nothing(client: AsyncClient, mine: dict):
    persona = await create(client, mine)

    await client.delete(url_of(persona), headers=mine)
    again = await create(client, mine, name='새로')

    assert await names(client, mine) == [('새로', True)]
    assert again['is_default'] is True


# --- 상한 ---


@pytest.fixture
async def small_app(auth_server: FakeAuthServer, engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    """한 사람에 둘까지만 만드는 앱."""
    app = create_app(make_test_settings(persona_max_per_owner=2), http_client=auth_server.make_client(), engine=engine)
    yield app
    await app.state.http_client.aclose()


async def test_the_limit_is_counted_for_each_person(small_app: FastAPI, mine: dict, theirs: dict):
    async with make_client(small_app) as client:
        await create(client, mine)
        await create(client, mine)
        full = await client.post(PERSONAS_URL, json={'name': '셋'}, headers=mine)
        others = await client.post(PERSONAS_URL, json={'name': '남'}, headers=theirs)

    assert full.status_code == status.HTTP_409_CONFLICT
    assert full.json() == {'detail': '페르소나는 2개까지 만들 수 있습니다.', 'code': 'persona_limit'}
    assert others.status_code == status.HTTP_201_CREATED


async def test_concurrent_creates_do_not_pass_the_limit(small_app: FastAPI, mine: dict, session: AsyncSession):
    async with make_client(small_app) as one, make_client(small_app) as two, make_client(small_app) as three:
        responses = await asyncio.gather(
            *(client.post(PERSONAS_URL, json={'name': '나'}, headers=mine) for client in (one, two, three))
        )

    assert sorted(response.status_code for response in responses) == [201, 201, 409]
    assert await session.scalar(select(func.count()).select_from(Persona)) == 2
    defaults = [response.json()['is_default'] for response in responses if response.status_code == 201]
    assert sorted(defaults) == [False, True]


# --- DB ---


async def test_the_database_keeps_one_default_per_person(session: AsyncSession):
    session.add_all([Persona(owner_id=TEST_USER_ID, name='하나', is_default=True)])
    await session.commit()
    session.add(Persona(owner_id=TEST_USER_ID, name='둘', is_default=True))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_rejects_a_long_description(session: AsyncSession):
    session.add(Persona(owner_id=TEST_USER_ID, name='나', description='가' * (PERSONA_DESCRIPTION_MAX_LENGTH + 1)))

    with pytest.raises(IntegrityError):
        await session.commit()
