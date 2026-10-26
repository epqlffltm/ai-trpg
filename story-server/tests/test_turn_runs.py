# story-server/tests/test_turn_runs.py

"""
말 한 번의 따로 도는 작업(app/turns/service.py 의 run_generation)과,
서버가 꺼질 때 멈추는 것(app/main.py 의 stop_turns). chat 서버의 것과 같은 것을 본다.
실제 DB(story_test)에서 돈다. 모델은 가짜(tests/models.py), 결제 서버는 받지 않는 것(FreeBilling)이다.

보는 것.
  - 사람이 떠나도(아무도 통로를 읽지 않아도) 끝까지 돌아 답을 저장하고 확정한다
  - 서버가 꺼지며 멈추면 받은 만큼의 조각을 partial 로 저장하고 맡길 것(capture_due)으로 둔다.
    확정은 다음 서버의 정리 작업이 한다
  - 받은 조각이 없이 멈추면 답이 없고 돌려줄 것(release_due)이다
  - 답을 저장하지 못하면(DB 가 없다) 통로에 실패를 알리고 끝난다. 예상하지 못한 모델의 오류는 server_error 다
  - 사람이 멈추면(StopSwitch) 받은 만큼 partial 로 저장하고 바로 확정한다. 받은 조각이 없으면 돌려준다.
    부르기 전에 멈추면 부르지 않는다. 다 받은 뒤에는 멈출 것이 없다. 멈춘 뒤에 서버가 꺼지면 꺼지는 쪽을 따른다
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from ai_core.provider import GenerationParams
from conversation_core.relay import Relay
from fastapi import FastAPI
from server_core.auth.tokens import AccessClaims
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.free_billing import FreeBilling
from app.conversations.models import Conversation, Message
from app.core.dependencies import Viewer, utc_now
from app.main import stop_turns
from app.turns import service
from app.turns.models import Generation
from app.turns.stops import StopSwitch
from app.turns.values import PromptOptions
from tests.billing import FakeBillingServer
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import ME, bearer, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

OPTIONS = PromptOptions(context_chars=12000)
PARAMS = GenerationParams(max_tokens=100, temperature=0.5)


@pytest.fixture
async def conversation(clean_tables: None, session: AsyncSession, client, asset, signing_key) -> dict:
    """luna 로 시작한 내 세션."""
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
        app.state.session_factory, viewer, uuid.UUID(conversation['id']), '안녕', OPTIONS, utc_now()
    )
    await service.prepare_turn(app.state.session_factory, FakeRouter(), FreeBilling(), start, utc_now())
    return start


async def generation_of(session: AsyncSession) -> Generation:
    session.expire_all()
    return (await session.scalars(select(Generation))).one()


async def run(
    app: FastAPI, start: service.TurnStart, provider: ScriptedProvider, relay: Relay, stop: StopSwitch | None = None
) -> None:
    route = await FakeRouter(provider).route(start.model_slug)
    switch = stop if stop is not None else StopSwitch()
    await service.run_generation(app.state.session_factory, FreeBilling(), route, start, PARAMS, relay, utc_now, switch)


async def until_called(provider: ScriptedProvider) -> None:
    """모델을 부르고 조각을 다 흘릴 때까지 기다린다."""
    while not provider.calls:
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.01)


async def test_nobody_reading_the_stream_still_saves_and_charges(
    app: FastAPI, session: AsyncSession, started: service.TurnStart
):
    relay = Relay()

    await run(app, started, ScriptedProvider(), relay)

    generation = await generation_of(session)
    assert (generation.billing_status, generation.outcome) == ('captured', 'complete')
    # 통로에는 조각 둘(segment, delta 의 짝 둘)과 끝이 남아 있다. 아무도 꺼내지 않았다
    assert relay.queue.qsize() > 4


async def test_a_turn_stopped_by_shutdown_keeps_what_it_got(
    app: FastAPI, session: AsyncSession, started: service.TurnStart
):
    provider = ScriptedProvider(pieces=['@mina: 어서', ' 와'], hold=asyncio.Event())
    task = asyncio.create_task(run(app, started, provider, Relay()))
    while not provider.calls:
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.01)

    await stop_turns({task})

    assert task.cancelled()
    generation = await generation_of(session)
    # 받은 만큼 저장했다. 끝나지 않은 마지막 줄도 조각이다. 확정은 정리 작업이 한다
    assert (generation.billing_status, generation.outcome, generation.error_code) == (
        'capture_due',
        'partial',
        'cancelled',
    )
    answer = (
        await session.execute(select(Message.segments, Message.status).where(Message.id == generation.message_id))
    ).one()
    assert tuple(answer) == ([{'speaker': 'mina', 'text': '어서 와'}], 'partial')
    query = select(Conversation.active_leaf_id, Conversation.generating_since).where(
        Conversation.id == started.conversation_id
    )
    assert tuple((await session.execute(query)).one()) == (generation.message_id, None)


async def test_a_turn_stopped_before_any_text_is_released(
    app: FastAPI, session: AsyncSession, started: service.TurnStart
):
    provider = ScriptedProvider(pieces=[], hold=asyncio.Event())
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


# --- 사람이 멈춘다 ---


async def test_a_stopped_turn_keeps_what_it_got_and_charges_it(
    app: FastAPI, session: AsyncSession, started: service.TurnStart
):
    provider = ScriptedProvider(pieces=['@mina: 어서', ' 와'], hold=asyncio.Event())
    stop = StopSwitch()
    relay = Relay()
    task = asyncio.create_task(run(app, started, provider, relay, stop))
    await until_called(provider)

    assert stop.request() is True
    await task

    generation = await generation_of(session)
    assert (generation.billing_status, generation.outcome, generation.error_code) == (
        'captured',
        'partial',
        'stopped',
    )
    frames = [item async for item in relay.frames()]
    assert frames[-1].event == 'done'
    assert '"segments":[{"speaker":"mina","text":"어서 와"}]' in frames[-1].data
    assert '"status":"partial"' in frames[-1].data


async def test_a_turn_stopped_before_any_text_is_released_at_once(
    app: FastAPI, session: AsyncSession, started: service.TurnStart
):
    provider = ScriptedProvider(pieces=[], hold=asyncio.Event())
    stop = StopSwitch()
    relay = Relay()
    task = asyncio.create_task(run(app, started, provider, relay, stop))
    await until_called(provider)

    stop.request()
    await task

    generation = await generation_of(session)
    assert (generation.billing_status, generation.message_id, generation.error_code) == ('released', None, 'stopped')
    frames = [item async for item in relay.frames()]
    assert (frames[-1].event, frames[-1].data) == ('failed', '{"code":"stopped"}')
    session.expire_all()
    row = await session.get(Conversation, started.conversation_id)
    assert row.generating_since is None


async def test_a_turn_stopped_before_the_call_calls_nothing(
    app: FastAPI, session: AsyncSession, started: service.TurnStart
):
    provider = ScriptedProvider()
    stop = StopSwitch()

    assert stop.request() is True
    await run(app, started, provider, Relay(), stop)

    assert provider.calls == []
    assert (await generation_of(session)).billing_status == 'released'


async def test_a_finished_call_cannot_be_stopped(app: FastAPI, session: AsyncSession, started: service.TurnStart):
    stop = StopSwitch()

    await run(app, started, ScriptedProvider(), Relay(), stop)

    assert stop.request() is False
    assert (await generation_of(session)).outcome == 'complete'


async def test_shutdown_while_a_stop_is_settling_stops_the_whole_turn(
    app: FastAPI, session: AsyncSession, started: service.TurnStart
):
    class SlowToStop(ScriptedProvider):
        """멈추라는 말을 받고도 정리하느라 바로 끝나지 않는 공급자."""

        async def complete(self, messages, params, on_text=None):
            try:
                return await super().complete(messages, params, on_text)
            except asyncio.CancelledError:
                cleaning.set()
                await asyncio.Event().wait()
                raise

    cleaning = asyncio.Event()
    provider = SlowToStop(pieces=['@mina: 어'], hold=asyncio.Event())
    stop = StopSwitch()
    task = asyncio.create_task(run(app, started, provider, Relay(), stop))
    await until_called(provider)
    stop.request()
    await cleaning.wait()

    # 사람이 멈춘 뒤 공급자가 끊기기 전에 서버가 꺼진다. 서버가 꺼지는 쪽을 따른다
    await stop_turns({task})

    assert task.cancelled()
    assert (await generation_of(session)).error_code == 'cancelled'
