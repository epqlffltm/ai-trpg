# trpg-server/tests/test_operator_reads.py

"""
운영자 API 와 감사 기록(#391).

보는 것.
  - 운영자가 아니면 404 다. 앉은 사람, 만든 사람도 그렇다. 운영자의 주소가 있다는 것을 알리지 않는다
  - 사유가 없거나 비었거나 길면 422 다
  - 운영자는 앉지 않은 테이블의 굳힌 내용, 기록, 대화, 귓속말 전부를 본다. 남의 시나리오의 초안과 판도 본다
  - 볼 때마다 감사 기록이 한 줄 남는다. 없는 것을 본 시도도 남는다
  - 감사 기록은 고치거나 지울 수 없다(DB 의 트리거)
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from app.operators.models import OperatorRead
from tests.narration_model import with_model
from tests.signing import SigningKey, make_access_claims, make_token
from tests.test_whispers import FRIEND, ME, REPLY, SECRET, open_trio, start, whisper

pytestmark = pytest.mark.usefixtures('clean_tables')

ADMIN_URL = f'{API_PREFIX}/admin'
OPERATOR = uuid.UUID('77777777-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'
REASON = '신고 #12'
CHAT = '다들 준비됐어?'


def bearer(signing_key: SigningKey, user_id: uuid.UUID, **claims) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id), **claims))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """테이블을 여는 방장의 머리말."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """두 번째로 앉는 사람의 머리말."""
    return bearer(signing_key, FRIEND)


@pytest.fixture
def operator(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 앉지 않은 운영자의 머리말."""
    return bearer(signing_key, OPERATOR, roles=['operator'])


@pytest.fixture
async def played(client: AsyncClient, me: dict, friend: dict) -> dict:
    """둘이 앉아 시작하고, 대화 한 줄과 귓속말을 주고받은 테이블."""
    table = await open_trio(client, me, friend)
    await start(client, table, {ME: me, FRIEND: friend})
    sent = await client.post(f'{API_PREFIX}/tables/{table["id"]}/messages', json={'content': CHAT}, headers=me)
    assert sent.status_code == status.HTTP_201_CREATED, sent.text
    await whisper(client, me, table, FRIEND)
    await whisper(client, friend, table, ME, content=REPLY)
    return table


async def admin_get(client: AsyncClient, headers: dict, path: str, **params) -> object:
    """운영자 API 를 사유와 함께 부른다."""
    return await client.get(f'{ADMIN_URL}{path}', params={'reason': REASON, **params}, headers=headers)


async def reads(session: AsyncSession) -> list[OperatorRead]:
    """감사 기록 전부. 적힌 순서대로다."""
    return list(await session.scalars(select(OperatorRead).order_by(OperatorRead.id)))


# --- 운영자만 ---


@pytest.mark.parametrize(
    'path', ['/tables/{id}', '/tables/{id}/events', '/tables/{id}/messages', '/tables/{id}/whispers']
)
async def test_a_player_of_the_table_gets_not_found(
    client: AsyncClient, played: dict, me: dict, session: AsyncSession, path: str
):
    response = await admin_get(client, me, path.format(id=played['id']))

    # 앉은 사람이라도 운영자의 주소는 없는 것으로 보인다. 기록도 남지 않는다
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert await reads(session) == []


@pytest.mark.parametrize('reason', ['', '   ', 'x' * 201])
async def test_a_reason_is_required(client: AsyncClient, played: dict, operator: dict, session: AsyncSession, reason):
    response = await client.get(f'{ADMIN_URL}/tables/{played["id"]}', params={'reason': reason}, headers=operator)
    missing = await client.get(f'{ADMIN_URL}/tables/{played["id"]}', headers=operator)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert missing.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert await reads(session) == []


# --- 테이블 ---


async def test_an_operator_reads_a_table_they_do_not_sit_at(client: AsyncClient, played: dict, operator: dict):
    response = await admin_get(client, operator, f'/tables/{played["id"]}')

    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert {member['user_id'] for member in body['members']} == {str(ME), str(FRIEND)}
    # 앉은 사람에게는 나가지 않는 굳힌 판의 내용을 통째로 본다
    assert body['content']['openings']


async def test_an_operator_reads_the_events_and_the_chat(client: AsyncClient, played: dict, operator: dict):
    found_events = await admin_get(client, operator, f'/tables/{played["id"]}/events')
    found_chat = await admin_get(client, operator, f'/tables/{played["id"]}/messages')

    assert found_events.status_code == status.HTTP_200_OK
    assert found_events.json()['items']
    assert [message['content'] for message in found_chat.json()['items']] == [CHAT]


async def test_an_operator_reads_every_whisper_once(client: AsyncClient, played: dict, operator: dict):
    response = await admin_get(client, operator, f'/tables/{played["id"]}/whispers')

    # 쪽지는 두 사람의 쪽지함에 한 장씩 적히지만 운영자에게는 한 장씩 보인다. 보낸 순서다
    body = response.json()
    assert body['total'] == 2
    assert [(item['sender_id'], item['content']) for item in body['items']] == [
        (str(ME), SECRET),
        (str(FRIEND), REPLY),
    ]


async def test_an_unknown_table_is_not_found_but_the_attempt_is_kept(
    client: AsyncClient, operator: dict, session: AsyncSession
):
    response = await admin_get(client, operator, f'/tables/{NO_SUCH_ID}')
    whispers = await admin_get(client, operator, f'/tables/{NO_SUCH_ID}/whispers')

    # 빈 목록이 아니라 404 다. 없는 테이블과 귓속말이 없는 테이블을 가른다
    assert (response.status_code, whispers.status_code) == (status.HTTP_404_NOT_FOUND, status.HTTP_404_NOT_FOUND)
    lines = [(read.target_kind, str(read.target_id)) for read in await reads(session)]
    assert lines == [('table', NO_SUCH_ID), ('table_whispers', NO_SUCH_ID)]


# --- 시나리오 ---


async def test_an_operator_reads_someone_elses_scenario_and_its_version(
    client: AsyncClient, played: dict, me: dict, operator: dict, session: AsyncSession
):
    scenario_id = (await client.get(f'{API_PREFIX}/scenarios', headers=me)).json()['items'][0]['id']

    draft = await admin_get(client, operator, f'/scenarios/{scenario_id}')
    version = await admin_get(client, operator, f'/scenarios/{scenario_id}/versions/1')
    no_version = await admin_get(client, operator, f'/scenarios/{scenario_id}/versions/9')

    assert draft.status_code == status.HTTP_200_OK, draft.text
    assert draft.json()['id'] == scenario_id
    assert version.status_code == status.HTTP_200_OK, version.text
    assert version.json()['snapshot']['openings']
    assert no_version.status_code == status.HTTP_404_NOT_FOUND
    lines = [(read.target_kind, read.target_number) for read in await reads(session)]
    assert lines == [('scenario', None), ('scenario_version', 1), ('scenario_version', 9)]


async def test_a_deleted_scenario_draft_is_not_found(client: AsyncClient, me: dict, operator: dict):
    rulebook = await client.post(f'{API_PREFIX}/rulebooks', json={'title': '룰북'}, headers=me)
    body = with_model({'title': '지울 것', 'rulebook_id': rulebook.json()['id']})
    scenario = (await client.post(f'{API_PREFIX}/scenarios', json=body, headers=me)).json()
    await client.delete(f'{API_PREFIX}/scenarios/{scenario["id"]}', headers=me)

    response = await admin_get(client, operator, f'/scenarios/{scenario["id"]}')

    # 지운 초안은 어디에도 나오지 않는다. 판은 테이블이 쓰므로 남는다(판의 주소로 본다)
    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_an_operator_cannot_read_a_scenario_as_a_player(client: AsyncClient, played: dict, me: dict):
    scenario_id = (await client.get(f'{API_PREFIX}/scenarios', headers=me)).json()['items'][0]['id']

    # 만든 사람이라도 운영자의 주소로는 없는 것으로 보인다
    assert (await admin_get(client, me, f'/scenarios/{scenario_id}')).status_code == status.HTTP_404_NOT_FOUND


# --- 감사 기록 ---


async def test_every_read_leaves_one_line(client: AsyncClient, played: dict, operator: dict, session: AsyncSession):
    await admin_get(client, operator, f'/tables/{played["id"]}')
    await admin_get(client, operator, f'/tables/{played["id"]}/whispers')

    lines = await reads(session)

    assert [(read.target_kind, read.target_id, read.operator_id, read.reason) for read in lines] == [
        ('table', uuid.UUID(played['id']), OPERATOR, REASON),
        ('table_whispers', uuid.UUID(played['id']), OPERATOR, REASON),
    ]
    assert all(read.request_id for read in lines)


@pytest.mark.parametrize('statement', ['update', 'delete'])
async def test_the_audit_trail_cannot_be_rewritten(
    client: AsyncClient, played: dict, operator: dict, session: AsyncSession, statement: str
):
    await admin_get(client, operator, f'/tables/{played["id"]}')
    rewrite = update(OperatorRead).values(reason='고쳤다') if statement == 'update' else delete(OperatorRead)

    with pytest.raises(DBAPIError):
        await session.execute(rewrite)
    await session.rollback()

    assert [read.reason for read in await reads(session)] == [REASON]
