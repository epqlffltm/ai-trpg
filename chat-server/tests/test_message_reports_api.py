# chat-server/tests/test_message_reports_api.py

"""
대화 속 답의 신고와 운영자 API(app/reports/, app/operators/, #678)를 검증한다. 실제 DB(chat_test)에서 돈다.

보는 것.
  - 자기 대화의 캐릭터의 답을 신고한다. 그 답과 앞의 말(CONTEXT_MESSAGES 개), 캐릭터와 판, 모델이 굳혀진다.
    뒤에 그 답을 고쳐도 굳힌 글은 그대로다
  - 사람의 말은 422 not_reportable, 남의 대화의 말과 없는 말은 404, 두 번째는 409 already_reported, 기타는 설명이 필수다
  - 대화를 지운 것으로 적어도 신고는 남고, 대화의 행이 지워지면(탈퇴) 함께 지워진다
  - 운영자가 아니면 /admin 은 모두 404 다
  - 열린 신고의 목록: minor 가 먼저, 그다음 오래된 것부터. 대화의 글과 신고한 사람은 싣지 않는다
  - 신고 하나를 보려면 사유가 필수이고, 볼 때마다(없는 신고도) 감사 기록이 남는다
  - 처리: 204, 감사 기록, 두 번째는 409 already_handled, 없으면 404. 처리한 것은 목록에서 빠진다
  - 감사 기록은 고치지도 지우지도 못한다
"""

import asyncio
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation
from app.main import API_PREFIX
from app.operators.models import OperatorAction, OperatorRead
from app.reports.models import CONTEXT_MESSAGES, MessageReport
from tests.assets import FakeAsset, make_character
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, ME, bearer, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

MESSAGES_URL = f'{API_PREFIX}/messages'
ADMIN_URL = f'{API_PREFIX}/admin'
OPERATOR = uuid.UUID('22222222-2222-4333-8444-555555555555')
THEM = uuid.UUID('99999999-2222-4333-8444-555555555555')


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def theirs(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, THEM)


@pytest.fixture
def operator(signing_key: SigningKey) -> dict[str, str]:
    claims = make_access_claims(sub=str(OPERATOR))
    claims['roles'] = ['operator']
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter(ScriptedProvider(pieces=['위험한 답.']))
    app.state.model_router = fake
    return fake


async def start(client: AsyncClient, session: AsyncSession, asset: FakeAsset, headers: dict) -> dict:
    await turn_on_luna(session)
    character = asset.add_character(make_character())
    response = await client.post(
        CONVERSATIONS_URL, json={'character_id': str(character.id), 'model': 'luna'}, headers=headers
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def say(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict, content: str) -> None:
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    response = await client.post(url, json={'content': content}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))


async def messages(client: AsyncClient, headers: dict, conversation: dict) -> list[dict]:
    return (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)).json()['messages']


async def report(client: AsyncClient, headers: dict, message: dict, reason: str = 'minor', description: str = ''):
    body = {'reason': reason, 'description': description}
    return await client.post(f'{MESSAGES_URL}/{message["id"]}/reports', json=body, headers=headers)


@pytest.fixture
async def talked(client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router, mine) -> dict:
    """인사말 뒤에 말을 넷 주고받은 대화. 마지막 말은 캐릭터의 답이다."""
    conversation = await start(client, session, asset, mine)
    for number in range(4):
        await say(client, app, mine, conversation, f'말 {number}')
    return conversation


# --- 신고 ---


async def test_an_answer_is_reported_with_its_context(
    client: AsyncClient, session: AsyncSession, talked: dict, mine: dict
):
    path = await messages(client, mine, talked)

    response = await report(client, mine, path[-1], description='어린 인물')

    assert response.status_code == status.HTTP_201_CREATED
    stored = await session.scalar(select(MessageReport))
    assert (stored.reporter_id, stored.reason, stored.description, stored.content) == (
        ME,
        'minor',
        '어린 인물',
        '위험한 답.',
    )
    assert (stored.character_name, stored.character_version, stored.model_slug) == ('세라', 1, 'luna')
    assert stored.context == [
        {'role': item['role'], 'content': item['content']} for item in path[-1 - CONTEXT_MESSAGES : -1]
    ]
    assert len(stored.context) == CONTEXT_MESSAGES


async def test_the_frozen_text_survives_an_edit(client: AsyncClient, session: AsyncSession, talked: dict, mine: dict):
    answer = (await messages(client, mine, talked))[-1]
    await report(client, mine, answer)

    await client.patch(f'{MESSAGES_URL}/{answer["id"]}', json={'content': '고친 답'}, headers=mine)

    assert (await session.scalar(select(MessageReport.content))) == '위험한 답.'


async def test_what_cannot_be_reported(client: AsyncClient, talked: dict, mine: dict, theirs: dict):
    path = await messages(client, mine, talked)
    mine_said = next(item for item in path if item['role'] == 'user')

    human = await report(client, mine, mine_said)
    foreign = await report(client, theirs, path[-1])
    missing = await report(client, mine, {'id': str(uuid.uuid4())})
    vague = await report(client, mine, path[-1], 'other')

    assert (human.status_code, human.json()['code']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'not_reportable')
    assert foreign.status_code == missing.status_code == status.HTTP_404_NOT_FOUND
    assert vague.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_reporting_twice_is_409(client: AsyncClient, talked: dict, mine: dict):
    answer = (await messages(client, mine, talked))[-1]
    await report(client, mine, answer)

    again = await report(client, mine, answer, 'spam')

    assert (again.status_code, again.json()['code']) == (status.HTTP_409_CONFLICT, 'already_reported')


async def test_reports_go_only_with_the_conversation_row(
    client: AsyncClient, session: AsyncSession, talked: dict, mine: dict
):
    await report(client, mine, (await messages(client, mine, talked))[-1])

    await client.delete(f'{CONVERSATIONS_URL}/{talked["id"]}', headers=mine)
    kept = len((await session.scalars(select(MessageReport))).all())
    await session.execute(delete(Conversation))
    await session.commit()

    assert (kept, len((await session.scalars(select(MessageReport))).all())) == (1, 0)


# --- 운영자 ---


async def test_admin_is_404_for_others(client: AsyncClient, talked: dict, mine: dict):
    answer = (await messages(client, mine, talked))[-1]
    report_id = (await report(client, mine, answer)).json()['id']

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
    assert not {'content', 'context', 'reporter_id', 'description'} & set(page['items'][0])


async def test_reading_a_report_is_recorded(
    client: AsyncClient, session: AsyncSession, talked: dict, mine: dict, operator: dict
):
    report_id = (await report(client, mine, (await messages(client, mine, talked))[-1])).json()['id']
    url = f'{ADMIN_URL}/message-reports/{report_id}'

    without = await client.get(url, headers=operator)
    found = await client.get(url, params={'reason': '신고 확인'}, headers=operator)
    missing = await client.get(
        f'{ADMIN_URL}/message-reports/{uuid.uuid4()}', params={'reason': '없는 것'}, headers=operator
    )

    assert without.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert found.status_code == status.HTTP_200_OK
    assert (found.json()['content'], len(found.json()['context'])) == ('위험한 답.', CONTEXT_MESSAGES)
    assert (missing.status_code, missing.json()['code']) == (status.HTTP_404_NOT_FOUND, 'report_not_found')
    reads = list(await session.scalars(select(OperatorRead).order_by(OperatorRead.id)))
    assert [(read.operator_id, read.target_kind, read.reason) for read in reads] == [
        (OPERATOR, 'message_report', '신고 확인'),
        (OPERATOR, 'message_report', '없는 것'),
    ]
    assert str(reads[0].target_id) == report_id and reads[0].request_id


async def test_handling_a_report(client: AsyncClient, session: AsyncSession, talked: dict, mine: dict, operator: dict):
    report_id = (await report(client, mine, (await messages(client, mine, talked))[-1])).json()['id']
    url = f'{ADMIN_URL}/message-reports/{report_id}/outcome'
    body = {'outcome': 'actioned', 'reason': '캐릭터를 숨김'}

    first = await client.put(url, json=body, headers=operator)
    again = await client.put(url, json={**body, 'outcome': 'dismissed'}, headers=operator)
    missing = await client.put(f'{ADMIN_URL}/message-reports/{uuid.uuid4()}/outcome', json=body, headers=operator)

    assert first.status_code == status.HTTP_204_NO_CONTENT
    assert (again.status_code, again.json()['code']) == (status.HTTP_409_CONFLICT, 'already_handled')
    assert missing.status_code == status.HTTP_404_NOT_FOUND
    stored = await session.scalar(select(MessageReport))
    assert (stored.outcome, stored.handled_by) == ('actioned', OPERATOR)
    actions = list(await session.scalars(select(OperatorAction)))
    assert [(action.action, action.reason) for action in actions] == [('report_action', '캐릭터를 숨김')]
    assert (await client.get(f'{ADMIN_URL}/message-reports', headers=operator)).json()['total'] == 0


async def test_the_audit_records_are_append_only(
    client: AsyncClient, session: AsyncSession, talked: dict, mine: dict, operator: dict
):
    report_id = (await report(client, mine, (await messages(client, mine, talked))[-1])).json()['id']
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
