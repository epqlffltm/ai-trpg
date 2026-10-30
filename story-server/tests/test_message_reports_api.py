# story-server/tests/test_message_reports_api.py

"""
세션 속 답의 신고(app/reports/, chat 의 #678 과 같다)를 검증한다. 실제 DB(story_test)에서 돈다.
asset 서버, 모델은 가짜다(tests/assets.py, tests/models.py).

보는 것.
  - 자기 세션의 모델의 답을 신고한다. 그 답과 앞의 말(CONTEXT_MESSAGES 개), 세계관과 판, 모델이 굳혀진다.
    뒤에 그 답을 고쳐도 굳힌 글은 그대로다
  - 사람의 말과 행동 말은 422 not_reportable, 남의 세션의 말과 없는 말은 404, 두 번째는 409 already_reported,
    기타는 설명이 필수다
  - 세션을 지운 것으로 적어도 신고는 남고, 세션의 행이 지워지면(탈퇴) 함께 지워진다
"""

import asyncio
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from app.reports.models import CONTEXT_MESSAGES, MessageReport
from app.withdrawal.service import erase_user
from tests.assets import FakeAsset
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, ME, bearer, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

MESSAGES_URL = f'{API_PREFIX}/messages'
THEM = uuid.UUID('99999999-2222-4333-8444-555555555555')
ANSWER = '@narration: 바람이 분다.\n@mina: 위험한 답.'


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def theirs(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, THEM)


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


async def reports(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(MessageReport))


@pytest.fixture
async def talked(clean_tables: None, client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, mine):
    """말을 넷 주고받은 세션. 마지막 말은 모델의 답이다."""
    app.state.model_router = FakeRouter(ScriptedProvider(pieces=[ANSWER]))
    await turn_on_luna(session)
    conversation = await start_with_luna(client, asset, mine)
    for number in range(4):
        await say(client, app, mine, conversation, f'말 {number}')
    return conversation


async def test_an_answer_is_reported_with_its_context(
    client: AsyncClient, session: AsyncSession, talked: dict, mine: dict
):
    path = await messages(client, mine, talked)

    response = await report(client, mine, path[-1], description='어린 인물')

    assert response.status_code == status.HTTP_201_CREATED
    stored = await session.scalar(select(MessageReport))
    assert str(stored.id) == response.json()['id']
    assert (stored.reporter_id, stored.reason, stored.description, stored.content) == (ME, 'minor', '어린 인물', ANSWER)
    assert (stored.world_name, stored.world_version, stored.model_slug) == ('여름 마을', 1, 'luna')
    assert stored.context == [
        {'role': item['role'], 'content': item['content']} for item in path[-1 - CONTEXT_MESSAGES : -1]
    ]
    assert len(stored.context) == CONTEXT_MESSAGES


async def test_the_frozen_text_survives_an_edit(client: AsyncClient, session: AsyncSession, talked: dict, mine: dict):
    answer = (await messages(client, mine, talked))[-1]
    await report(client, mine, answer)

    edited = await client.patch(f'{MESSAGES_URL}/{answer["id"]}', json={'segments': ['고침', '고친 답']}, headers=mine)

    assert edited.status_code == status.HTTP_200_OK, edited.text
    assert (await session.scalar(select(MessageReport.content))) == ANSWER


async def test_what_cannot_be_reported(client: AsyncClient, app: FastAPI, talked: dict, mine: dict, theirs: dict):
    path = await messages(client, mine, talked)
    mine_said = next(item for item in path if item['role'] == 'user')
    acted = await client.post(f'{CONVERSATIONS_URL}/{talked["id"]}/actions', json={'kind': 'pass_time'}, headers=mine)
    assert acted.status_code == status.HTTP_200_OK, acted.text
    await asyncio.gather(*list(app.state.turns))
    action = next(item for item in await messages(client, mine, talked) if item['role'] == 'action')

    human = await report(client, mine, mine_said)
    server = await report(client, mine, action)
    foreign = await report(client, theirs, path[-1])
    missing = await report(client, mine, {'id': str(uuid.uuid4())})
    vague = await report(client, mine, path[-1], 'other')

    assert (human.status_code, human.json()['code']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'not_reportable')
    assert (server.status_code, server.json()['code']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'not_reportable')
    assert foreign.status_code == missing.status_code == status.HTTP_404_NOT_FOUND
    assert vague.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_reporting_twice_is_409(client: AsyncClient, talked: dict, mine: dict):
    answer = (await messages(client, mine, talked))[-1]
    await report(client, mine, answer)

    again = await report(client, mine, answer, 'spam')

    assert (again.status_code, again.json()['code']) == (status.HTTP_409_CONFLICT, 'already_reported')


async def test_reports_go_only_with_the_session_row(
    client: AsyncClient, session: AsyncSession, talked: dict, mine: dict
):
    await report(client, mine, (await messages(client, mine, talked))[-1])

    await client.delete(f'{CONVERSATIONS_URL}/{talked["id"]}', headers=mine)
    kept = await reports(session)
    await erase_user(session, ME)

    assert (kept, await reports(session)) == (1, 0)
