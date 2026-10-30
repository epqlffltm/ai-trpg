# story-server/tests/test_session_delete_api.py

"""
세션 지우기(DELETE /conversations/{id}, chat 과 같다)를 API 로 검증한다. 실제 DB(story_test)에서 돈다.
asset 서버, 모델은 가짜다(tests/assets.py, tests/models.py).

보는 것.
  - 지우면 지운 시각만 적고 말과 사본은 남는다. 다시 지우거나 남의 것을 지우면 404 다
  - 지운 세션은 목록과 읽기에 나오지 않고, 말을 보낼 수도 없다(404)
  - 지운 세션은 요약하지 않는다
  - "지난번에 고른 모델"은 지운 세션도 센다
  - 탈퇴하면 지운 세션의 행도 지워진다
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations import repository
from app.conversations.models import Conversation, ImportedWorld
from app.core.config import Settings
from app.withdrawal.service import erase_user
from tests.assets import FakeAsset
from tests.turns import CONVERSATIONS_URL, ME, bearer, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def theirs(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, SOMEONE_ELSE)


@pytest.fixture
async def conversation(clean_tables: None, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict):
    await turn_on_luna(session)
    return await start_with_luna(client, asset, mine)


def url_of(conversation: dict) -> str:
    return f'{CONVERSATIONS_URL}/{conversation["id"]}'


async def count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model))


async def test_deleting_needs_login(client: AsyncClient, conversation: dict):
    assert (await client.delete(url_of(conversation))).status_code == status.HTTP_401_UNAUTHORIZED


async def test_deleting_marks_the_time_and_keeps_the_rows(
    client: AsyncClient, session: AsyncSession, conversation: dict, mine: dict, theirs: dict
):
    refused = await client.delete(url_of(conversation), headers=theirs)
    deleted = await client.delete(url_of(conversation), headers=mine)
    again = await client.delete(url_of(conversation), headers=mine)

    assert (refused.status_code, deleted.status_code, again.status_code) == (404, 204, 404)
    stored = await session.get(Conversation, uuid.UUID(conversation['id']))
    assert stored.deleted_at is not None
    assert await count(session, ImportedWorld) == 1


async def test_a_deleted_session_is_not_listed_read_or_played(
    client: AsyncClient, asset: FakeAsset, conversation: dict, mine: dict
):
    kept = await start_with_luna(client, asset, mine)
    await client.delete(url_of(conversation), headers=mine)

    listed = (await client.get(CONVERSATIONS_URL, headers=mine)).json()
    read = await client.get(url_of(conversation), headers=mine)
    said = await client.post(f'{url_of(conversation)}/messages', json={'content': '안녕'}, headers=mine)

    assert [item['id'] for item in listed['items']] == [kept['id']]
    assert listed['total'] == 1
    assert (read.status_code, said.status_code) == (status.HTTP_404_NOT_FOUND, status.HTTP_404_NOT_FOUND)


async def test_a_deleted_session_is_not_summarized(
    client: AsyncClient, app: FastAPI, settings: Settings, conversation: dict, mine: dict
):
    app.state.settings = settings.model_copy(update={'summary_model': 'luna', 'summary_after_messages': 1})
    await client.delete(url_of(conversation), headers=mine)

    assert await app.state.summarizer.plan(uuid.UUID(conversation['id'])) is None


async def test_the_last_model_counts_deleted_sessions(
    client: AsyncClient, session: AsyncSession, conversation: dict, mine: dict
):
    await client.delete(url_of(conversation), headers=mine)

    assert await repository.last_model(session, ME) == 'luna'


async def test_withdrawal_erases_deleted_sessions_too(
    client: AsyncClient, session: AsyncSession, conversation: dict, mine: dict
):
    await client.delete(url_of(conversation), headers=mine)

    await erase_user(session, ME)

    assert await count(session, Conversation) == 0
