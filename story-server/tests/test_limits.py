# story-server/tests/test_limits.py

"""
요청 수 제한(app/limits/)을 검증한다. API 는 실제 DB(story_test)에서 돈다.

보는 것.
  - 제한들: 모델을 부르는 요청과 쓰기는 따로 센다
  - API: 모델을 부르는 요청(말, 행동, 다시 생성)과 쓰기를 사람마다 따로 센다.
    넘으면 429 too_many_attempts 와 Retry-After.
    멈추기와 읽기는 세지 않는다
세는 곳과 규칙(메모리, Redis, 닿지 못할 때, 응답)은 server-core 의 tests/test_limits.py 가 본다(#1266).
"""

import asyncio
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy.ext.asyncio import AsyncSession

from app.limits.setup import build_limiting
from app.main import API_PREFIX
from tests.assets import FakeAsset
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, bearer, start_with_luna, turn_on_luna

SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')


# --- 제한들 ---


async def test_generations_and_writes_do_not_share_a_count(app: FastAPI):
    settings = app.state.settings.model_copy(update={'limits_enabled': True, 'generation_limit': 2, 'write_limit': 1})
    limiting = build_limiting(settings, None)

    await limiting.limiter.count_attempt(limiting.limits.generations, 'me')
    await limiting.limiter.count_attempt(limiting.limits.generations, 'me')
    await limiting.limiter.count_attempt(limiting.limits.writes, 'me')


# --- API ---


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def limited(app: FastAPI) -> None:
    """제한을 켠다. 모델을 부르는 요청은 둘, 쓰기는 하나까지(1 분)."""
    settings = app.state.settings.model_copy(update={'limits_enabled': True, 'generation_limit': 2, 'write_limit': 1})
    app.state.limiting = build_limiting(settings, None)


@pytest.fixture
async def conversation(clean_tables: None, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict):
    await turn_on_luna(session)
    return await start_with_luna(client, asset, mine, {'paths': [{'a': 'home', 'b': 'beach', 'minutes': 30}]})


@pytest.mark.usefixtures('clean_tables')
async def test_generations_over_the_limit_are_429(
    client: AsyncClient,
    app: FastAPI,
    conversation: dict,
    mine: dict,
    signing_key: SigningKey,
    limited: None,
):
    app.state.model_router = FakeRouter()
    base = f'{CONVERSATIONS_URL}/{conversation["id"]}'
    answers = []
    # 말 보내기와 행동과 다시 생성을 함께 센다
    for url, body in [(f'{base}/messages', {'content': '안녕'}), (f'{base}/actions', {'kind': 'pass_time'})]:
        answers.append(await client.post(url, json=body, headers=mine))
        await asyncio.gather(*list(app.state.turns))
    regenerate = f'{API_PREFIX}/messages/{uuid.uuid4()}/regenerate'
    answers.append(await client.post(regenerate, headers=mine))

    assert [answer.status_code for answer in answers] == [200, 200, status.HTTP_429_TOO_MANY_REQUESTS]
    assert answers[-1].json()['code'] == 'too_many_attempts'
    assert int(answers[-1].headers['Retry-After']) >= 1
    # 다른 사람은 따로 센다(세션은 남의 것이라 404 지만 막히지는 않았다)
    other = await client.post(f'{base}/messages', json={'content': '안녕'}, headers=bearer(signing_key, SOMEONE_ELSE))
    assert other.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.usefixtures('clean_tables')
async def test_writes_are_counted_apart_from_generations(
    client: AsyncClient, conversation: dict, mine: dict, limited: None
):
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/model'

    first = await client.put(url, json={'model': 'luna'}, headers=mine)
    second = await client.put(url, json={'model': 'luna'}, headers=mine)
    read = await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)

    assert (first.status_code, second.status_code) == (status.HTTP_200_OK, status.HTTP_429_TOO_MANY_REQUESTS)
    # 읽기는 세지 않는다
    assert read.status_code == status.HTTP_200_OK


@pytest.mark.usefixtures('clean_tables')
async def test_stopping_is_not_counted(client: AsyncClient, mine: dict, limited: None):
    stops = [await client.post(f'{API_PREFIX}/generations/{uuid.uuid4()}/stop', headers=mine) for _ in range(3)]

    assert [stop.status_code for stop in stops] == [status.HTTP_404_NOT_FOUND] * 3
