# asset-server/tests/test_operator_reports.py

"""
운영자가 신고를 보고 캐릭터를 숨기는 API(app/operators/, #678)를 검증한다. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 운영자가 아니면 모두 404 다
  - 열린 신고의 묶음: 캐릭터마다 한 줄, 사유마다의 수, minor 가 있는 것이 먼저. 처리한 것은 빠진다
  - 한 캐릭터의 신고: 처리한 것까지, 신고한 사람의 id 는 없다. 없는 캐릭터는 404
  - 받아들이면(actioned) 숨긴다. 숨긴 캐릭터는 공개 목록, 공개 소개, 남에게 내주는 판에서 빠지고 주인은 계속 본다.
    주인이 공개로 돌려도 숨김이 앞선다. 받아들이지 않으면(dismissed) 그대로다
  - 숨기기와 풀기. 사유가 없으면 422. 조치마다 감사 기록이 한 줄(사유, 요청 식별자)
  - 감사 기록은 고치지도 지우지도 못한다(트리거)
  - PUBLIC_FOR_EVERYONE 을 켜면 일반 사용자도 공개로 둔다. 끄면 403 operator_only
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.auth.tokens import AccessClaims
from server_core.testing.tokens import FakeAuthServer, SigningKey, make_access_claims, make_token
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.characters import service as characters
from app.characters.service import CharacterNotFoundError
from app.main import API_PREFIX, create_app
from app.operators.models import OperatorAction
from tests.conftest import make_client, make_test_settings

pytestmark = pytest.mark.usefixtures('clean_tables')

CHARACTERS_URL = f'{API_PREFIX}/characters'
LISTINGS_URL = f'{API_PREFIX}/listings/characters'
ADMIN_URL = f'{API_PREFIX}/admin'
OPERATOR = uuid.UUID('11111111-2222-4333-8444-555555555555')
READERS = [uuid.UUID(f'{number}9999999-2222-4333-8444-555555555555') for number in range(1, 5)]
START = {'title': '비 오는 밤', 'situation': '문을 두드리는 소리가 난다.'}


def headers_for(signing_key: SigningKey, user_id: uuid.UUID, operator: bool = False) -> dict:
    claims = make_access_claims(sub=str(user_id))
    if operator:
        claims['roles'] = ['operator']
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


@pytest.fixture
def operator(signing_key: SigningKey) -> dict:
    return headers_for(signing_key, OPERATOR, operator=True)


@pytest.fixture
def readers(signing_key: SigningKey) -> list[dict]:
    return [headers_for(signing_key, reader) for reader in READERS]


async def public_character(client: AsyncClient, headers: dict, name: str = '세라') -> dict:
    made = (
        await client.post(CHARACTERS_URL, json={'genre': 'romance', 'name': name, 'starts': [START]}, headers=headers)
    ).json()
    await client.patch(f'{CHARACTERS_URL}/{made["id"]}', json={'visibility': 'public'}, headers=headers)
    await client.post(f'{CHARACTERS_URL}/{made["id"]}/versions', json={}, headers=headers)
    return made


async def report(client: AsyncClient, headers: dict, made: dict, reason: str = 'spam') -> None:
    response = await client.post(
        f'{LISTINGS_URL}/{made["id"]}/reports', json={'reason': reason, 'description': '설명'}, headers=headers
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text


async def outcome(client: AsyncClient, headers: dict, made: dict, result: str, reason: str = '신고 3건 확인'):
    body = {'outcome': result, 'reason': reason}
    return await client.put(f'{ADMIN_URL}/characters/{made["id"]}/reports/outcome', json=body, headers=headers)


async def listed_ids(client: AsyncClient) -> list[str]:
    return [item['id'] for item in (await client.get(LISTINGS_URL)).json()['items']]


def viewer(user_id: uuid.UUID) -> AccessClaims:
    return AccessClaims(user_id=user_id, expires_at=datetime.now(UTC) + timedelta(minutes=5))


# --- 운영자만 ---


async def test_everything_is_404_for_others(client: AsyncClient, operator: dict, readers: list[dict]):
    made = await public_character(client, operator)
    body = {'hidden': True, 'reason': '사유'}

    responses = [
        await client.get(f'{ADMIN_URL}/character-reports', headers=readers[0]),
        await client.get(f'{ADMIN_URL}/characters/{made["id"]}/reports', headers=readers[0]),
        await outcome(client, readers[0], made, 'actioned'),
        await client.put(f'{ADMIN_URL}/characters/{made["id"]}/hidden', json=body, headers=readers[0]),
    ]

    assert {response.status_code for response in responses} == {status.HTTP_404_NOT_FOUND}


# --- 신고 보기 ---


async def test_open_reports_are_grouped_with_minor_first(client: AsyncClient, operator: dict, readers: list[dict]):
    first = await public_character(client, operator, '먼저')
    second = await public_character(client, operator, '나중')
    await report(client, readers[0], first, 'minor')
    for headers in readers[:3]:
        await report(client, headers, second, 'spam' if headers is not readers[2] else 'abuse')

    page = (await client.get(f'{ADMIN_URL}/character-reports', headers=operator)).json()

    assert page['total'] == 2
    assert [(item['name'], item['open_count']) for item in page['items']] == [('먼저', 1), ('나중', 3)]
    assert page['items'][1]['reasons'] == {'spam': 2, 'abuse': 1, 'sexual': 0, 'minor': 0, 'illegal': 0, 'other': 0}
    assert page['items'][0]['hidden'] is False


async def test_a_characters_reports_include_handled_ones(client: AsyncClient, operator: dict, readers: list[dict]):
    made = await public_character(client, operator)
    await report(client, readers[0], made)
    await outcome(client, operator, made, 'dismissed')
    await report(client, readers[1], made, 'illegal')

    found = (await client.get(f'{ADMIN_URL}/characters/{made["id"]}/reports', headers=operator)).json()
    missing = await client.get(f'{ADMIN_URL}/characters/{uuid.uuid4()}/reports', headers=operator)

    assert [(item['reason'], item['outcome']) for item in found] == [('illegal', None), ('spam', 'dismissed')]
    assert 'reporter_id' not in found[0]
    assert missing.status_code == status.HTTP_404_NOT_FOUND


# --- 처리 ---


async def test_actioning_hides_the_character_from_everyone_but_the_owner(
    client: AsyncClient, session: AsyncSession, operator: dict, readers: list[dict]
):
    made = await public_character(client, operator)
    await report(client, readers[0], made)
    await report(client, readers[1], made)

    response = await outcome(client, operator, made, 'actioned')

    assert (response.status_code, response.json()) == (status.HTTP_200_OK, {'handled': 2, 'hidden': True})
    assert await listed_ids(client) == []
    assert (await client.get(f'{LISTINGS_URL}/{made["id"]}')).status_code == status.HTTP_404_NOT_FOUND
    with pytest.raises(CharacterNotFoundError):
        await characters.get_usable_latest(session, viewer(READERS[0]), uuid.UUID(made['id']))
    mine = (await client.get(f'{CHARACTERS_URL}/{made["id"]}', headers=operator)).json()
    assert mine['hidden_at'] is not None
    groups = (await client.get(f'{ADMIN_URL}/character-reports', headers=operator)).json()
    assert groups == {'items': [], 'total': 0}


async def test_the_owner_cannot_unhide_by_making_it_public_again(
    client: AsyncClient, operator: dict, readers: list[dict]
):
    made = await public_character(client, operator)
    await report(client, readers[0], made)
    await outcome(client, operator, made, 'actioned')

    await client.patch(f'{CHARACTERS_URL}/{made["id"]}', json={'visibility': 'private'}, headers=operator)
    await client.patch(f'{CHARACTERS_URL}/{made["id"]}', json={'visibility': 'public'}, headers=operator)

    assert await listed_ids(client) == []


async def test_dismissing_keeps_the_character(
    client: AsyncClient, session: AsyncSession, operator: dict, readers: list[dict]
):
    made = await public_character(client, operator)
    await report(client, readers[0], made)

    response = await outcome(client, operator, made, 'dismissed')

    assert response.json() == {'handled': 1, 'hidden': False}
    assert await listed_ids(client) == [made['id']]
    action = await session.scalar(select(OperatorAction))
    assert (action.action, action.operator_id, action.reason) == ('reports_dismiss', OPERATOR, '신고 3건 확인')


async def test_handling_again_keeps_earlier_outcomes(client: AsyncClient, operator: dict, readers: list[dict]):
    made = await public_character(client, operator)
    await report(client, readers[0], made)
    await outcome(client, operator, made, 'dismissed')
    await report(client, readers[1], made, 'minor')

    second = await outcome(client, operator, made, 'actioned')

    found = (await client.get(f'{ADMIN_URL}/characters/{made["id"]}/reports', headers=operator)).json()
    assert second.json() == {'handled': 1, 'hidden': True}
    assert [(item['reason'], item['outcome']) for item in found] == [('minor', 'actioned'), ('spam', 'dismissed')]


async def test_hiding_twice_keeps_the_first_time(client: AsyncClient, operator: dict):
    made = await public_character(client, operator)
    url = f'{ADMIN_URL}/characters/{made["id"]}/hidden'

    await client.put(url, json={'hidden': True, 'reason': '처음'}, headers=operator)
    first = (await client.get(f'{CHARACTERS_URL}/{made["id"]}', headers=operator)).json()['hidden_at']
    await client.put(url, json={'hidden': True, 'reason': '다시'}, headers=operator)

    assert (await client.get(f'{CHARACTERS_URL}/{made["id"]}', headers=operator)).json()['hidden_at'] == first


async def test_hiding_and_unhiding_are_recorded(client: AsyncClient, session: AsyncSession, operator: dict):
    made = await public_character(client, operator)
    url = f'{ADMIN_URL}/characters/{made["id"]}/hidden'

    hidden = await client.put(url, json={'hidden': True, 'reason': '직접 확인'}, headers=operator)
    hidden_list = await listed_ids(client)
    shown = await client.put(url, json={'hidden': False, 'reason': '오인'}, headers=operator)

    assert (hidden.json(), shown.json()) == ({'hidden': True}, {'hidden': False})
    assert (hidden_list, await listed_ids(client)) == ([], [made['id']])
    actions = list(await session.scalars(select(OperatorAction).order_by(OperatorAction.id)))
    assert [(action.action, action.reason) for action in actions] == [
        ('character_hide', '직접 확인'),
        ('character_unhide', '오인'),
    ]
    assert all(action.request_id for action in actions)


@pytest.mark.parametrize('reason', ['', '   ', 'x' * 201])
async def test_a_reason_is_required(client: AsyncClient, operator: dict, reason: str):
    made = await public_character(client, operator)

    response = await outcome(client, operator, made, 'actioned', reason)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_a_missing_character_is_404(client: AsyncClient, operator: dict):
    response = await outcome(client, operator, {'id': str(uuid.uuid4())}, 'actioned')

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_the_audit_record_is_append_only(client: AsyncClient, session: AsyncSession, operator: dict):
    made = await public_character(client, operator)
    await client.put(
        f'{ADMIN_URL}/characters/{made["id"]}/hidden', json={'hidden': True, 'reason': '사유'}, headers=operator
    )

    for statement in ("UPDATE operator_actions SET reason = '고침'", 'DELETE FROM operator_actions'):
        with pytest.raises(DBAPIError):
            await session.execute(text(statement))
        await session.rollback()


# --- 일반 사용자의 공개 ---


@pytest.fixture
async def open_app(auth_server: FakeAuthServer, engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    """누구나 캐릭터를 만들고 공개로 두는 앱."""
    settings = make_test_settings(characters_for_everyone=True, public_for_everyone=True)
    app = create_app(settings, http_client=auth_server.make_client(), engine=engine)
    yield app
    await app.state.http_client.aclose()


@pytest.fixture
async def half_open_app(auth_server: FakeAuthServer, engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    """누구나 만들지만 공개는 운영자만인 앱(지금의 3단계)."""
    app = create_app(
        make_test_settings(characters_for_everyone=True), http_client=auth_server.make_client(), engine=engine
    )
    yield app
    await app.state.http_client.aclose()


async def make_public_as_user(app: FastAPI, headers: dict) -> int:
    async with make_client(app) as client:
        made = (await client.post(CHARACTERS_URL, json={'genre': 'romance', 'name': '세라'}, headers=headers)).json()
        response = await client.patch(f'{CHARACTERS_URL}/{made["id"]}', json={'visibility': 'public'}, headers=headers)
    return response.status_code


async def test_everyone_may_go_public_when_opened(open_app: FastAPI, half_open_app: FastAPI, readers: list[dict]):
    assert await make_public_as_user(open_app, readers[0]) == status.HTTP_200_OK
    assert await make_public_as_user(half_open_app, readers[1]) == status.HTTP_403_FORBIDDEN
