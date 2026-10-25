# story-server/tests/test_charge_settler.py

"""
청구 정리(app/turns/settler.py)를 검증한다. 실제 DB(story_test)와 가짜 결제 서버(tests/billing.py)로 돈다.

보는 것.
  - 확정할 것과 돌려줄 것을 맡긴다. 맡기지 못하면 다음에 부를 때를 미룬다(5초, 10초 …). 그때가 되기 전에는 부르지 않는다
  - 결제 서버가 받아들이지 않으면 failed 다
  - 도중에 오래 남은 청구(서버가 꺼졌다)는 돌려준다. 오래되지 않은 것은 건드리지 않는다
  - 한 청구가 실패해도 다른 청구는 맡긴다. 바퀴가 통째로 실패해도 멈추지 않는다
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from server_core.auth.tokens import AccessClaims
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Viewer, utc_now
from app.turns import service
from app.turns.charging import retry_delay
from app.turns.models import Generation
from app.turns.settler import ChargeSettler
from app.turns.values import PromptOptions
from tests.billing import FakeBillingServer
from tests.models import FakeRouter
from tests.turns import ME, PRICE_CODE, bearer, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

OPTIONS = PromptOptions(context_chars=12000)


@pytest.fixture
def server() -> FakeBillingServer:
    """가짜 결제 서버. 나는 크레딧 100 이 있고 luna 의 말 한 번은 30 이다."""
    fake = FakeBillingServer(balances={ME: 100})
    fake.prices[PRICE_CODE] = 30
    return fake


@pytest.fixture
def billing(server: FakeBillingServer):
    return server.billing(server.make_client())


@pytest.fixture
async def held(app: FastAPI, session: AsyncSession, client, asset, signing_key, billing) -> service.TurnStart:
    """홀드까지 건 말 한 번(held). 모델은 부르지 않았다."""
    await turn_on_luna(session)
    conversation = await start_with_luna(client, asset, bearer(signing_key))
    claims = AccessClaims(user_id=ME, expires_at=datetime.now(UTC) + timedelta(minutes=15))
    start = await service.begin_turn(
        app.state.session_factory, Viewer(claims, 't'), uuid.UUID(conversation['id']), '안녕', OPTIONS, utc_now()
    )
    await service.prepare_turn(app.state.session_factory, FakeRouter(), billing, start, utc_now())
    return start


def settler_at(app: FastAPI, billing, now: datetime) -> ChargeSettler:
    return ChargeSettler(app.state.session_factory, billing=lambda: billing, interval=0.01, clock=lambda: now)


async def set_row(session: AsyncSession, **values) -> None:
    await session.execute(update(Generation).values(**values))
    await session.commit()


async def row(session: AsyncSession) -> Generation:
    session.expire_all()
    return (await session.scalars(select(Generation))).one()


@pytest.mark.parametrize(
    ('due', 'expected', 'balance'), [('capture_due', 'captured', 70), ('release_due', 'released', 100)]
)
async def test_due_charges_are_settled(
    app: FastAPI,
    session: AsyncSession,
    held: service.TurnStart,
    billing,
    server: FakeBillingServer,
    due: str,
    expected: str,
    balance: int,
):
    await set_row(session, billing_status=due)

    settled = await settler_at(app, billing, utc_now()).tick()

    assert settled == 1
    assert (await row(session)).billing_status == expected
    assert server.balance(ME) == balance


async def test_an_unreachable_billing_server_pushes_the_next_try_back(
    app: FastAPI, session: AsyncSession, held: service.TurnStart, billing, server: FakeBillingServer
):
    await set_row(session, billing_status='capture_due', settle_attempts=1)
    server.down = True
    now = utc_now()

    await settler_at(app, billing, now).tick()

    generation = await row(session)
    assert (generation.billing_status, generation.settle_attempts) == ('capture_due', 2)
    assert generation.next_settle_at == now + timedelta(seconds=10)


async def test_a_charge_waits_until_its_next_try(
    app: FastAPI, session: AsyncSession, held: service.TurnStart, billing, server: FakeBillingServer
):
    now = utc_now()
    await set_row(session, billing_status='capture_due', next_settle_at=now + timedelta(seconds=5))

    early = await settler_at(app, billing, now).tick()
    on_time = await settler_at(app, billing, now + timedelta(seconds=5)).tick()

    assert (early, on_time) == (0, 1)


async def test_a_refused_charge_is_failed(
    app: FastAPI, session: AsyncSession, held: service.TurnStart, billing, server: FakeBillingServer
):
    await set_row(session, billing_status='capture_due')
    server.expire(held.reference)

    await settler_at(app, billing, utc_now()).tick()

    generation = await row(session)
    assert (generation.billing_status, generation.error_code) == ('failed', 'rejected_409')


@pytest.mark.parametrize('status', ['held', 'pending'])
async def test_a_charge_left_open_by_a_dead_server_is_released(
    app: FastAPI, session: AsyncSession, held: service.TurnStart, billing, server: FakeBillingServer, status: str
):
    await set_row(session, billing_status=status, created_at=utc_now() - timedelta(minutes=16))

    await settler_at(app, billing, utc_now()).tick()

    generation = await row(session)
    assert (generation.billing_status, generation.outcome, generation.error_code) == ('released', 'failed', 'abandoned')
    assert server.balance(ME) == 100


async def test_a_charge_still_running_is_left_alone(
    app: FastAPI, session: AsyncSession, held: service.TurnStart, billing, server: FakeBillingServer
):
    settled = await settler_at(app, billing, utc_now()).tick()

    assert settled == 0
    assert (await row(session)).billing_status == 'held'


async def test_a_charge_finished_meanwhile_is_not_abandoned(
    app: FastAPI, session: AsyncSession, held: service.TurnStart, billing
):
    settler = settler_at(app, billing, utc_now())
    generation = await row(session)
    session.expunge(generation)
    await set_row(session, billing_status='captured')

    # 찾은 뒤 맡기기 전에 말 한 번이 먼저 끝냈다
    assert await settler.settle_one(generation, utc_now()) is False
    assert (await row(session)).billing_status == 'captured'


async def test_one_broken_charge_does_not_stop_the_others(
    app: FastAPI, session: AsyncSession, held: service.TurnStart, monkeypatch: pytest.MonkeyPatch
):
    async def broken(*args, **kwargs):
        raise RuntimeError('버그')

    await set_row(session, billing_status='capture_due')
    monkeypatch.setattr(service, 'settle_generation', broken)

    settled = await settler_at(app, object(), utc_now()).tick()

    assert settled == 0


async def test_the_loop_survives_a_failed_round_and_stops_when_told(app: FastAPI, monkeypatch: pytest.MonkeyPatch):
    settler = settler_at(app, object(), utc_now())
    rounds = []

    async def failing_sweep() -> int:
        rounds.append(1)
        raise RuntimeError('DB 가 없다')

    monkeypatch.setattr(ChargeSettler, 'sweep', lambda self: failing_sweep())
    stop = asyncio.Event()
    task = asyncio.create_task(settler.run(stop))
    while len(rounds) < 2:
        await asyncio.sleep(0.01)
    stop.set()
    await task

    assert len(rounds) >= 2


def test_the_retry_delay_doubles_up_to_five_minutes():
    assert [retry_delay(attempts).total_seconds() for attempts in (0, 1, 2, 6, 7, 20)] == [5, 10, 20, 300, 300, 300]


async def test_a_charge_that_is_not_due_is_not_sent(
    app: FastAPI, session: AsyncSession, held: service.TurnStart, billing, server: FakeBillingServer
):
    await set_row(session, billing_status='captured')
    generation = await row(session)

    # 찾은 것과 다른 상태의 청구가 넘어와도 결제 서버를 부르지 않는다
    assert await settler_at(app, billing, utc_now()).settle_one(generation, utc_now()) is False
    assert server.calls == [('holds', held.reference)]
