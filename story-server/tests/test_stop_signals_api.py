# story-server/tests/test_stop_signals_api.py

"""
다른 서버에서 도는 생성의 멈추기(#674)를 API 로 검증한다. 실제 DB(story_test)의 NOTIFY 와 LISTEN 을 쓴다.
asset 서버, 모델은 가짜다(tests/assets.py, tests/models.py).

"다른 서버"는 이 앱의 스위치 목록(app.state.stops)에서 생성을 빼서, 따로 듣는 쪽(StopListener)의 목록에 옮겨 흉내 낸다.
테스트에서는 lifespan 이 돌지 않으니 이 앱 자신은 듣지 않는다.

보는 것.
  - 이 서버에 없는 내 생성이 도는 중이면 204 이고, 그 생성을 돌리는 쪽이 알림을 받아 멈춘다(받은 만큼 partial)
  - 남의 생성, 다 끝난 생성, 오래되어 서버가 꺼진 것으로 보는 생성은 404 이고 알리지 않는다
  - 다른 스키마의 채널은 듣지 않는다
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core import loops, stop_signals
from server_core.testing.tokens import SigningKey
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.main import API_PREFIX
from app.turns.models import Generation
from app.turns.stops import Stops, stop_here
from tests.assets import FakeAsset
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, bearer, parse_sse, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')
# 알림이 닿기를 기다리는 시간(초)
WAIT_SECONDS = 5


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def theirs(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, SOMEONE_ELSE)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter(ScriptedProvider(pieces=['@narration: 바람이 '], hold=asyncio.Event()))
    app.state.model_router = fake
    return fake


@pytest.fixture
async def conversation(clean_tables: None, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict):
    await turn_on_luna(session)
    return await start_with_luna(client, asset, mine)


@pytest.fixture
def elsewhere() -> Stops:
    """다른 서버의 스위치 목록."""
    return {}


async def listening(settings: Settings, channel: str, stops: Stops) -> tuple[loops.Running, stop_signals.StopListener]:
    """다른 서버처럼 채널을 듣기 시작한다. 연결을 맺을 때까지 기다린다."""
    listener = stop_signals.StopListener(
        stop_signals.listen_dsn(settings.database_url),
        channel,
        on_stop=lambda generation_id: stop_here(stops, generation_id),
    )
    running = loops.start(listener, 'test-stop-listener')
    async with asyncio.timeout(WAIT_SECONDS):
        while not listener.is_listening():
            await asyncio.sleep(0.01)
    return running, listener


@pytest.fixture
async def other_server(app: FastAPI, settings: Settings, elsewhere: Stops):
    running, _ = await listening(settings, app.state.stop_channel, elsewhere)
    yield
    await running.halt()


async def run_elsewhere(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    router: FakeRouter,
    headers: dict,
    conversation: dict,
    to: Stops,
) -> tuple[asyncio.Task, uuid.UUID]:
    """말을 보내고, 모델이 도는 동안 그 생성의 스위치를 다른 서버로 옮긴다."""
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    sending = asyncio.create_task(client.post(url, json={'content': '안녕'}, headers=headers))
    while not router.provider.calls:
        await asyncio.sleep(0.01)
    session.expire_all()
    generation_id = (await session.scalars(select(Generation.id))).one()
    to[generation_id] = app.state.stops.pop(generation_id)
    return sending, generation_id


def stop(client: AsyncClient, headers: dict, generation_id: uuid.UUID):
    return client.post(f'{API_PREFIX}/generations/{generation_id}/stop', headers=headers)


async def finish(app: FastAPI, router: FakeRouter, sending: asyncio.Task) -> dict:
    """모델을 놓아 주고 끝까지 기다린 답."""
    router.provider.hold.set()
    response = await sending
    await asyncio.gather(*list(app.state.turns))
    return parse_sse(response.text)[-1][1]['message']


@pytest.mark.usefixtures('other_server')
async def test_a_generation_on_another_server_is_stopped_through_the_db(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    elsewhere: Stops,
    mine: dict,
):
    sending, generation_id = await run_elsewhere(client, app, session, router, mine, conversation, elsewhere)

    response = await stop(client, mine, generation_id)
    switch = elsewhere[generation_id][1]
    async with asyncio.timeout(WAIT_SECONDS):
        while not switch.requested:
            await asyncio.sleep(0.01)
    done = await asyncio.wait_for(sending, WAIT_SECONDS)
    await asyncio.gather(*list(app.state.turns))

    assert response.status_code == status.HTTP_204_NO_CONTENT
    answer = parse_sse(done.text)[-1][1]['message']
    assert answer['status'] == 'partial'


@pytest.mark.usefixtures('other_server')
async def test_someone_elses_generation_on_another_server_is_404(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    elsewhere: Stops,
    mine: dict,
    theirs: dict,
):
    sending, generation_id = await run_elsewhere(client, app, session, router, mine, conversation, elsewhere)

    response = await stop(client, theirs, generation_id)
    answer = await finish(app, router, sending)

    assert (response.status_code, response.json()['code']) == (status.HTTP_404_NOT_FOUND, 'generation_not_running')
    assert not elsewhere[generation_id][1].requested
    assert answer['status'] == 'complete'


@pytest.mark.usefixtures('other_server')
async def test_a_stale_generation_is_404(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    elsewhere: Stops,
    mine: dict,
):
    sending, generation_id = await run_elsewhere(client, app, session, router, mine, conversation, elsewhere)
    # 서버가 꺼진 채 남은 것처럼 오래전에 시작한 것으로 바꾼다
    long_ago = datetime.now(UTC) - timedelta(hours=1)
    await session.execute(update(Generation).where(Generation.id == generation_id).values(created_at=long_ago))
    await session.commit()

    response = await stop(client, mine, generation_id)
    await finish(app, router, sending)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert not elsewhere[generation_id][1].requested


async def test_a_finished_generation_is_404(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    router.provider.hold.set()
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    await client.post(url, json={'content': '안녕'}, headers=mine)
    await asyncio.gather(*list(app.state.turns))
    generation_id = (await session.scalars(select(Generation.id))).one()

    response = await stop(client, mine, generation_id)

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_another_schemas_channel_is_not_heard(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    settings: Settings,
    conversation: dict,
    router: FakeRouter,
    elsewhere: Stops,
    mine: dict,
):
    running, _ = await listening(settings, stop_signals.channel_name('chat_test'), elsewhere)
    try:
        sending, generation_id = await run_elsewhere(client, app, session, router, mine, conversation, elsewhere)
        response = await stop(client, mine, generation_id)
        await asyncio.sleep(0.2)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not elsewhere[generation_id][1].requested
        await finish(app, router, sending)
    finally:
        await running.halt()
