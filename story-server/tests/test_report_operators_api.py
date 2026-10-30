# story-server/tests/test_report_operators_api.py

"""
운영자 API(app/operators/, chat 의 #678 과 같다)를 검증한다. 실제 DB(story_test)에서 돈다.

보는 것.
  - 운영자가 아니면 /admin 은 모두 404 다
  - 열린 신고의 목록: minor 가 먼저, 그다음 오래된 것부터. 세션의 글과 신고한 사람은 싣지 않는다
  - 신고 하나를 보려면 사유가 필수이고, 볼 때마다(없는 신고도) 감사 기록이 남는다
  - 처리: 204, 감사 기록, 두 번째는 409 already_handled, 없으면 404. 처리한 것은 목록에서 빠진다
  - 감사 기록은 고치지도 지우지도 못한다. 탈퇴해도 남는다
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from app.operators.models import OperatorAction, OperatorRead
from app.reports.models import CONTEXT_MESSAGES, MessageReport
from app.withdrawal.service import erase_user
from tests.assets import FakeAsset
from tests.reporting import ANSWER, messages, report, talk
from tests.turns import ME, bearer

pytestmark = pytest.mark.usefixtures('clean_tables')

ADMIN_URL = f'{API_PREFIX}/admin'
OPERATOR = uuid.UUID('22222222-2222-4333-8444-555555555555')


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def operator(signing_key: SigningKey) -> dict[str, str]:
    claims = make_access_claims(sub=str(OPERATOR))
    claims['roles'] = ['operator']
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


@pytest.fixture
async def talked(clean_tables: None, client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, mine):
    """말을 넷 주고받은 세션. 마지막 말은 모델의 답이다."""
    return await talk(client, app, session, asset, mine)


async def last_reported(client: AsyncClient, headers: dict, conversation: dict) -> str:
    """마지막 답을 신고하고 신고의 id 를 돌려준다."""
    response = await report(client, headers, (await messages(client, headers, conversation))[-1])
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()['id']


async def test_admin_is_404_for_others(client: AsyncClient, talked: dict, mine: dict):
    report_id = await last_reported(client, mine, talked)

    responses = [
        await client.get(f'{ADMIN_URL}/message-reports', headers=mine),
        await client.get(f'{ADMIN_URL}/message-reports/{report_id}', params={'reason': '확인'}, headers=mine),
        await client.put(
            f'{ADMIN_URL}/message-reports/{report_id}/outcome',
            json={'outcome': 'dismissed', 'reason': '확인'},
            headers=mine,
        ),
    ]

    assert {response.status_code for response in responses} == {status.HTTP_404_NOT_FOUND}


async def test_open_reports_put_minor_first_without_text(client: AsyncClient, talked: dict, mine: dict, operator: dict):
    path = await messages(client, mine, talked)
    answers = [item for item in path if item['role'] == 'assistant']
    await report(client, mine, answers[1], 'spam')
    await report(client, mine, answers[2], 'abuse')
    await report(client, mine, answers[3], 'minor')

    page = (await client.get(f'{ADMIN_URL}/message-reports', headers=operator)).json()

    assert page['total'] == 3
    assert [item['reason'] for item in page['items']] == ['minor', 'spam', 'abuse']
    assert (page['items'][0]['world_name'], page['items'][0]['model_slug']) == ('여름 마을', 'luna')
    assert not {'content', 'context', 'reporter_id', 'description'} & set(page['items'][0])


async def test_reading_a_report_is_recorded(
    client: AsyncClient, session: AsyncSession, talked: dict, mine: dict, operator: dict
):
    report_id = await last_reported(client, mine, talked)
    url = f'{ADMIN_URL}/message-reports/{report_id}'

    without = await client.get(url, headers=operator)
    found = await client.get(url, params={'reason': '신고 확인'}, headers=operator)
    missing = await client.get(
        f'{ADMIN_URL}/message-reports/{uuid.uuid4()}', params={'reason': '없는 것'}, headers=operator
    )

    assert without.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert found.status_code == status.HTTP_200_OK
    assert (found.json()['content'], len(found.json()['context'])) == (ANSWER, CONTEXT_MESSAGES)
    assert (missing.status_code, missing.json()['code']) == (status.HTTP_404_NOT_FOUND, 'report_not_found')
    reads = list(await session.scalars(select(OperatorRead).order_by(OperatorRead.id)))
    assert [(read.operator_id, read.target_kind, read.reason) for read in reads] == [
        (OPERATOR, 'message_report', '신고 확인'),
        (OPERATOR, 'message_report', '없는 것'),
    ]
    assert str(reads[0].target_id) == report_id and reads[0].request_id


async def test_handling_a_report(client: AsyncClient, session: AsyncSession, talked: dict, mine: dict, operator: dict):
    report_id = await last_reported(client, mine, talked)
    url = f'{ADMIN_URL}/message-reports/{report_id}/outcome'
    body = {'outcome': 'actioned', 'reason': '세계관 확인'}

    first = await client.put(url, json=body, headers=operator)
    again = await client.put(url, json={**body, 'outcome': 'dismissed'}, headers=operator)
    missing = await client.put(f'{ADMIN_URL}/message-reports/{uuid.uuid4()}/outcome', json=body, headers=operator)
    blank = await client.put(url, json={**body, 'reason': '  '}, headers=operator)

    assert first.status_code == status.HTTP_204_NO_CONTENT
    assert (again.status_code, again.json()['code']) == (status.HTTP_409_CONFLICT, 'already_handled')
    assert (missing.status_code, missing.json()['code']) == (status.HTTP_404_NOT_FOUND, 'report_not_found')
    assert blank.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    stored = await session.scalar(select(MessageReport))
    assert (stored.outcome, stored.handled_by) == ('actioned', OPERATOR)
    actions = list(await session.scalars(select(OperatorAction)))
    assert [(action.action, action.reason) for action in actions] == [('report_action', '세계관 확인')]
    assert (await client.get(f'{ADMIN_URL}/message-reports', headers=operator)).json()['total'] == 0


async def test_the_audit_records_are_append_only_and_outlive_the_reporter(
    client: AsyncClient, session: AsyncSession, talked: dict, mine: dict, operator: dict
):
    report_id = await last_reported(client, mine, talked)
    await client.get(f'{ADMIN_URL}/message-reports/{report_id}', params={'reason': '확인'}, headers=operator)
    await client.put(
        f'{ADMIN_URL}/message-reports/{report_id}/outcome',
        json={'outcome': 'dismissed', 'reason': '아님'},
        headers=operator,
    )

    for statement in (
        "UPDATE operator_reads SET reason = 'x'",
        'DELETE FROM operator_reads',
        "UPDATE operator_actions SET reason = 'x'",
        'DELETE FROM operator_actions',
    ):
        with pytest.raises(DBAPIError):
            await session.execute(text(statement))
        await session.rollback()
    await erase_user(session, ME)

    assert await session.scalar(select(func.count()).select_from(MessageReport)) == 0
    assert await session.scalar(select(func.count()).select_from(OperatorRead)) == 1
    assert await session.scalar(select(func.count()).select_from(OperatorAction)) == 1
