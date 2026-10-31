# story-server/tests/test_cleared_endings.py

"""
회차 혜택(조건의 ending_seen, 판의 형식 5)을 검증한다.
상태를 읽고 쓰는 모양은 DB 없이, API 는 실제 DB(story_test)에서 돈다.

보는 것.
  - 계정의 본 엔딩은 세션을 시작할 때 굳힌다(conversations.cleared_endings). 그 뒤에 본 엔딩은 다음 세션부터다
  - 굳힌 엔딩은 저장한 상태에 적지 않고 읽을 때 붙인다. 처음의 상태에도 붙는다
  - 굳힌 엔딩이 조건(ending_seen)에 맞으면 이벤트가 열리고, 아니면 열리지 않는다
"""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation
from app.engine.state import start_state
from app.records.models import EndingRecord
from app.turns.states import state_on_path, state_to_json
from tests.assets import FakeAsset, make_world
from tests.engine_worlds import condition, event, member, world
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, ME, WORLD_FIELDS, bearer, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

PATHS = [{'a': 'home', 'b': 'beach', 'minutes': 30}]
# 혼자인 여름(solo)을 본 적이 있으면 해변에서 열리는 이벤트
SECRET = event('secret', condition('reach_place', 'beach'), condition('ending_seen', 'solo'), cast=['mina'])


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter()
    app.state.model_router = fake
    return fake


def test_cleared_endings_are_attached_not_stored():
    plain = world([member('mina')])
    stored = state_to_json(start_state(plain, frozenset({'solo'})))

    assert 'cleared' not in stored
    assert state_on_path(plain, [None, stored], frozenset({'solo'})).cleared == frozenset({'solo'})
    assert state_on_path(plain, [None], frozenset({'solo'})).cleared == frozenset({'solo'})
    assert state_on_path(plain, [stored]).cleared == frozenset()


async def record(session: AsyncSession, world_id: uuid.UUID, ending_id: str) -> None:
    session.add(EndingRecord(owner_id=ME, world_source=world_id, ending_id=ending_id, first_seen_at=datetime.now(UTC)))
    await session.commit()


async def start(client: AsyncClient, headers: dict, world_id: uuid.UUID) -> dict:
    body = {'world_id': str(world_id), 'model': 'luna'}
    response = await client.post(CONVERSATIONS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def move_to_beach(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict) -> str | None:
    """해변으로 가고 그 행동 말에 열린 이벤트를 돌려준다."""
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/actions'
    response = await client.post(url, json={'kind': 'move', 'place': 'beach'}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))
    detail = (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)).json()
    return next(message['event_id'] for message in detail['messages'] if message['role'] == 'action')


async def test_an_ending_seen_before_the_session_opens_the_event(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router: FakeRouter, mine: dict
):
    await turn_on_luna(session)
    copy = asset.add_world(make_world(fields={**WORLD_FIELDS, 'format': 5, 'paths': PATHS, 'events': [SECRET]}))
    first = await start(client, mine, copy.id)
    await record(session, copy.id, 'solo')
    second = await start(client, mine, copy.id)

    opened_first = await move_to_beach(client, app, mine, first)
    opened_second = await move_to_beach(client, app, mine, second)

    stored = {row.id: row.cleared_endings for row in await session.scalars(select(Conversation))}
    assert (stored[uuid.UUID(first['id'])], stored[uuid.UUID(second['id'])]) == ([], ['solo'])
    # 첫 세션은 시작할 때 본 엔딩이 없었다. 그 뒤에 본 엔딩은 다음 세션부터다
    assert (opened_first, opened_second) == (None, 'secret')
