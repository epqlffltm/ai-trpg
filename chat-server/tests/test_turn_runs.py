# chat-server/tests/test_turn_runs.py

"""
말 한 번의 따로 도는 작업(app/turns/service.py 의 run_generation)과,
서버가 꺼질 때 멈추는 것(app/main.py 의 stop_turns), 조용한 통로의 하트비트(app/conversation/relay.py).
실제 DB(chat_test)에서 돈다. 모델은 가짜(tests/models.py), 결제 서버는 받지 않는 것(FreeBilling)이다.

보는 것.
  - 사람이 떠나도(아무도 통로를 읽지 않아도) 끝까지 돌아 답을 저장하고 확정한다
  - 서버가 꺼지며 멈추면 받은 만큼 partial 로 저장하고 맡길 것(capture_due)으로 둔다.
    확정은 다음 서버의 정리 작업이 한다
  - 받은 글이 없이 멈추면 답이 없고 돌려줄 것(release_due)이다
  - 답을 저장하지 못하면(DB 가 없다) 통로에 실패를 알리고 끝난다
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from ai_core.provider import GenerationParams
from fastapi import FastAPI
from server_core.auth.tokens import AccessClaims
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.free_billing import FreeBilling
from app.conversation.relay import Relay
from app.conversation.sse import Comment
from app.conversations.models import Conversation
from app.core.dependencies import Viewer, utc_now
from app.main import stop_turns
from app.turns import service
from app.turns.models import Generation
from tests.billing import FakeBillingServer
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import ME, bearer, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

PARAMS = GenerationParams(max_tokens=100, temperature=0.5)


@pytest.fixture
async def conversation(clean_tables: None, session: AsyncSession, client, asset, signing_key) -> dict:
    """luna 로 시작한 내 대화."""
    await turn_on_luna(session)
    return await start_with_luna(client, asset, bearer(signing_key))


@pytest.fixture
def viewer() -> Viewer:
    claims = AccessClaims(user_id=ME, expires_at=datetime.now(UTC) + timedelta(minutes=15))
    return Viewer(claims=claims, token='t')


@pytest.fixture
async def started(app: FastAPI, conversation: dict, viewer: Viewer) -> service.TurnStart:
    """사람의 말을 저장하고 홀드까지 건 말 한 번. 모델은 아직 부르지 않았다."""
    start = await service.begin_turn(
        app.state.session_factory, viewer, uuid.UUID(conversation['id']), '안녕', 12000, utc_now()
    )
    await service.prepare_turn(app.state.session_factory, FakeRouter(), FreeBilling(), start, utc_now())
    return start


async def generation_of(session: AsyncSession) -> Generation:
    session.expire_all()
    return (await session.scalars(select(Generation))).one()


async def run(app: FastAPI, start: service.TurnStart, provider: ScriptedProvider, relay: Relay) -> None:
    route = await FakeRouter(provider).route(start.model_slug)
    await service.run_generation(app.state.session_factory, FreeBilling(), route, start, PARAMS, relay, utc_now)


async def test_nobody_reading_the_stream_still_saves_and_charges(
    app: FastAPI, session: AsyncSession, started: service.TurnStart
):
    relay = Relay()

    await run(app, started, ScriptedProvider(), relay)

    generation = await generation_of(session)
    assert (generation.billing_status, generation.outcome) == ('captured', 'complete')
    # 통로에는 조각 둘과 끝이 남아 있다. 아무도 꺼내지 않았다
    assert relay.queue.qsize() == 3


async def test_a_turn_stopped_by_shutdown_keeps_what_it_got(
    app: FastAPI, session: AsyncSession, started: service.TurnStart
):
    hold = asyncio.Event()
    provider = ScriptedProvider(pieces=['어서 ', '와'], hold=hold)
    task = asyncio.create_task(run(app, started, provider, Relay()))
    while not provider.calls:
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.01)

    await stop_turns({task})

    assert task.cancelled()
    generation = await generation_of(session)
    # 받은 만큼 저장했다. 확정은 정리 작업이 한다(꺼지는 서버는 결제 서버를 부르지 않는다)
    assert (generation.billing_status, generation.outcome, generation.error_code) == (
        'capture_due',
        'partial',
        'cancelled',
    )
    answer_id = generation.message_id
    session.expire_all()
    row = await session.get(Conversation, started.conversation_id)
    assert (row.active_leaf_id, row.generating_since) == (answer_id, None)


async def test_a_turn_stopped_before_any_text_is_released(
    app: FastAPI, session: AsyncSession, started: service.TurnStart
):
    hold = asyncio.Event()
    provider = ScriptedProvider(pieces=[], hold=hold)
    task = asyncio.create_task(run(app, started, provider, Relay()))
    while not provider.calls:
        await asyncio.sleep(0.01)

    await stop_turns({task})

    generation = await generation_of(session)
    assert (generation.billing_status, generation.message_id) == ('release_due', None)


async def test_an_answer_that_cannot_be_saved_ends_the_stream_with_a_failure(
    app: FastAPI, started: service.TurnStart, monkeypatch: pytest.MonkeyPatch
):
    async def broken(*args, **kwargs):
        raise ConnectionError('DB 가 없다')

    monkeypatch.setattr(service, 'save_result', broken)
    relay = Relay()

    await run(app, started, ScriptedProvider(), relay)

    frames = [item async for item in relay.frames()]
    assert (frames[-1].event, frames[-1].data) == ('failed', '{"code":"server_error"}')


async def test_an_unexpected_model_error_is_a_server_error(
    app: FastAPI, session: AsyncSession, started: service.TurnStart
):
    class Broken(ScriptedProvider):
        async def complete(self, messages, params, on_text=None):
            raise RuntimeError('버그')

    await run(app, started, Broken(), Relay())

    generation = await generation_of(session)
    assert (generation.billing_status, generation.error_code) == ('released', 'server_error')


async def test_stopping_with_nothing_running_is_quiet():
    await stop_turns(set())


async def test_a_quiet_relay_sends_a_heartbeat():
    relay = Relay(heartbeat=0.01)
    frames = relay.frames()

    item = await anext(frames)

    assert item == Comment('heartbeat')


async def test_a_charge_already_finished_is_not_sent_again(
    app: FastAPI, session: AsyncSession, started: service.TurnStart
):
    server = FakeBillingServer()
    await session.execute(update(Generation).values(billing_status='captured'))
    await session.commit()

    # 정리 작업이 먼저 끝냈다. 말 한 번의 끝은 결제 서버를 다시 부르지 않는다
    await service.settle_turn(
        app.state.session_factory, server.billing(server.make_client()), started.generation_id, utc_now()
    )

    assert server.calls == []


async def test_shutdown_stops_the_running_turns(app: FastAPI):
    async with app.router.lifespan_context(app):
        task = asyncio.create_task(asyncio.sleep(60))
        app.state.turns.add(task)

    assert task.cancelled()
