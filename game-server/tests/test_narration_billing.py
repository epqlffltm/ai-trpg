# game-server/tests/test_narration_billing.py

"""
라운드의 서술 값을 결제 서버에서 받는 흐름(#148)을 검증한다. 결제 서버 자리에 가짜를 꽂는다(tests/billing.py).

보는 것.
  - 라운드를 열면 방장에게 청구를 적는다. 정리 작업이 곧 건다. 서술이 다음 장면이 되면 확정한다.
  - 크레딧이 모자라면 선언하기 전에 알리고, 닫을 때 서술하지 않는다. 충전하고 다시 맡기면 서술한다.
  - 결제 서버가 죽어도 열 때 잡아 둔 라운드는 서술한다. 확정은 살아난 뒤에 정리 작업이 한다.
    열 때도 닫을 때도 죽어 있으면 서술하지 않는다.
  - 테이블이 끝나면 돌려준다. 서술하는 도중에 끝나도 돌려준다.
  - 서술이 실패해 다시 맡겨도 같은 홀드를 쓴다. 두 번 빠지지 않는다.
  - 결제 서버가 받아들이지 않으면 실패로 적고 오류로 남긴다. 답을 받지 못하면 갈수록 늦게 다시 부른다.
  - 걸고 왔더니 그사이 돌려준 청구면 한 번 더 돌려준다.
"""

import asyncio
import logging
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing import settler as charge_settler
from app.billing import settling
from app.billing.charges import EXTEND_AFTER, EXTEND_REJECTED_RETRY, retry_delay
from app.billing.client import HoldOutcome, HoldResult
from app.billing.models import NarrationCharge
from app.billing.settler import ChargeSettler
from app.main import create_app
from app.rounds import closing
from app.rounds.closing import ChargeNotSecured, failure_reason
from app.rounds.models import Round
from tests.billing import FakeBillingServer
from tests.logs import rendered
from tests.signing import SigningKey
from tests.test_round_closing import (
    FRIEND,
    FRIENDS_ACTION,
    ME,
    MY_ACTION,
    RESULT,
    CountingNarrator,
    GatedNarrator,
    HeldJobs,
    bearer,
    current,
    declare,
    event_types,
    hold_closing,
    last_event,
    start_duo,
    table_url,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

# 서술 한 번의 값. 가짜 결제 서버의 가격표다
PRICE = 50
# 가짜 결제 서버의 standard 가격표 이름. 등급을 고르지 않은 테이블의 라운드가 건다
PRICE_CODE = 'narration.standard'


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장. 서술 값을 낸다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """함께 앉는 사람."""
    return bearer(signing_key, FRIEND)


@pytest.fixture
async def billing(app: FastAPI) -> FakeBillingServer:
    """앱에 꽂은 가짜 결제 서버. 방장(ME)에게 1000 크레딧이 있다."""
    server = FakeBillingServer(balances={ME: 1000})
    client = server.make_client()
    app.state.billing = server.billing(client)
    yield server
    await client.aclose()


@pytest.fixture
def narrator(app: FastAPI) -> GatedNarrator:
    """앱에 꽂은 문 앞의 서술자. 문이 열려 있다. 테스트가 닫을 수 있다."""
    gated = GatedNarrator()
    gated.release()
    app.state.narrator = gated
    yield gated
    gated.release()


def settler_at(app: FastAPI, moment: datetime) -> ChargeSettler:
    """그 시각에 멈춘 청구 정리. 앱의 결제 서버를 쓴다."""
    return replace(app.state.charge_settler, clock=lambda: moment)


async def tick(app: FastAPI, moment: datetime | None = None) -> None:
    """청구 정리를 한 바퀴 돌린다. 시각을 주지 않으면 지금이다."""
    await settler_at(app, moment or datetime.now(UTC)).tick()


async def charges_of(session: AsyncSession, table: dict) -> list[NarrationCharge]:
    """테이블의 청구들. 라운드 순서다."""
    query = (
        select(NarrationCharge)
        .join(Round, Round.id == NarrationCharge.round_id)
        .where(Round.table_id == uuid.UUID(table['id']))
        .order_by(Round.number)
        .execution_options(populate_existing=True)
    )
    return list(await session.scalars(query))


async def statuses_of(session: AsyncSession, table: dict) -> list[str]:
    """테이블의 청구들의 상태. 라운드 순서다."""
    return [charge.status for charge in await charges_of(session, table)]


async def close_round(client: AsyncClient, me: dict, friend: dict, table: dict, narrated) -> None:
    """둘 다 선언해서 라운드를 닫고, 서술이 끝날 때까지 기다린다."""
    await declare(client, me, table, MY_ACTION)
    await declare(client, friend, table, FRIENDS_ACTION)
    await narrated()


# --- 열고, 걸고, 확정한다 ---


async def test_opening_a_round_charges_the_host(
    client: AsyncClient, session: AsyncSession, me: dict, friend: dict, billing: FakeBillingServer
):
    table = await start_duo(client, me, friend)

    [charge] = await charges_of(session, table)

    # 라운드를 연 것과 함께 적었다. 결제 서버는 아직 부르지 않았다
    assert (charge.status, charge.payer_id, charge.price_code) == ('pending', ME, PRICE_CODE)
    assert charge.reference == f'narration:{table["id"]}:1:{ME}'
    assert billing.calls == []


async def test_the_settler_holds_the_charge_of_an_open_round(
    client: AsyncClient, app: FastAPI, session: AsyncSession, me: dict, friend: dict, billing: FakeBillingServer
):
    table = await start_duo(client, me, friend)

    await tick(app)

    assert await statuses_of(session, table) == ['held']
    assert billing.balance(ME) == 1000 - PRICE


async def test_a_narrated_round_is_captured_and_the_next_one_charged(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator: GatedNarrator,
    narrated,
):
    table = await start_duo(client, me, friend)
    await tick(app)

    await close_round(client, me, friend, table, narrated)

    # 서술이 다음 장면이 됐다. 그 값을 확정했다. 새 라운드의 청구가 생겼다
    assert (await current(client, me, table))['scene'] == RESULT
    assert await statuses_of(session, table) == ['captured', 'pending']
    assert billing.statuses() == {f'narration:{table["id"]}:1:{ME}': 'captured'}
    assert billing.balance(ME) == 1000 - PRICE


async def test_closing_holds_the_charge_if_the_settler_has_not_yet(
    client: AsyncClient,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator: GatedNarrator,
    narrated,
):
    table = await start_duo(client, me, friend)

    await close_round(client, me, friend, table, narrated)

    # 정리 작업이 돌기 전에 닫았다. 서술 작업이 걸고, 서술하고, 확정했다
    assert [action for action, _ in billing.calls] == ['holds', 'capture']
    assert await statuses_of(session, table) == ['captured', 'pending']


async def test_the_host_who_opened_the_round_pays_for_it(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator: GatedNarrator,
    narrated,
):
    billing.balances[FRIEND] = 1000
    table = await start_duo(client, me, friend)
    await tick(app)
    handed = await client.put(table_url(table, '/host'), json={'user_id': str(FRIEND)}, headers=me)
    assert handed.status_code == status.HTTP_200_OK, handed.text

    await close_round(client, me, friend, table, narrated)
    await tick(app)

    # 라운드를 열 때의 방장이 그 라운드를 낸다. 다음 라운드는 새 방장이 낸다
    assert [charge.payer_id for charge in await charges_of(session, table)] == [ME, FRIEND]
    assert (billing.balance(ME), billing.balance(FRIEND)) == (1000 - PRICE, 1000 - PRICE)


# --- 크레딧이 모자랄 때 ---


async def test_short_credits_are_told_before_anyone_declares(
    client: AsyncClient, app: FastAPI, session: AsyncSession, me: dict, friend: dict, billing: FakeBillingServer
):
    billing.balances[ME] = PRICE - 1
    table = await start_duo(client, me, friend)

    await tick(app)
    await tick(app)

    # 앉은 사람 모두에게 한 번 알린다. 모자란 청구는 정리 작업이 다시 걸지 않는다(충전했는지는 닫을 때 본다)
    assert await event_types(client, friend, table) == ['narration_credits_short']
    assert (await last_event(client, friend, table))['payload'] == {'round': 1}
    assert await statuses_of(session, table) == ['short']
    assert len(billing.calls) == 1


async def test_a_round_without_credits_is_not_narrated(
    client: AsyncClient,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator: GatedNarrator,
    narrated,
):
    billing.balances[ME] = 0
    table = await start_duo(client, me, friend)

    await close_round(client, me, friend, table, narrated)

    # 서술자를 부르지 않았다. 라운드는 닫는 중에 머물고 까닭이 보인다
    assert narrator.requests == []
    assert (await current(client, me, table))['status'] == 'closing'
    assert (await last_event(client, friend, table))['payload'] == {'round': 1, 'reason': 'insufficient_credits'}
    assert await statuses_of(session, table) == ['short']


async def test_shortness_is_told_once_even_when_found_again_at_closing(
    client: AsyncClient,
    app: FastAPI,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator: GatedNarrator,
    narrated,
):
    billing.balances[ME] = 0
    table = await start_duo(client, me, friend)
    await tick(app)

    await close_round(client, me, friend, table, narrated)

    # 닫을 때 다시 걸어 봐도 모자랐다. 모자라다는 알림은 처음 한 번뿐이고, 서술의 실패로 다시 알린다
    assert await event_types(client, friend, table) == [
        'narration_credits_short',
        'player_action',
        'player_action',
        'round_closed',
        'narration_failed',
    ]


async def test_after_topping_up_the_host_can_hand_the_round_again(
    client: AsyncClient,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator: GatedNarrator,
    narrated,
):
    billing.balances[ME] = 0
    table = await start_duo(client, me, friend)
    await close_round(client, me, friend, table, narrated)

    billing.balances[ME] = 100
    retried = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    await narrated()

    assert retried.status_code == status.HTTP_202_ACCEPTED
    assert (await current(client, me, table))['number'] == 2
    assert (await statuses_of(session, table))[0] == 'captured'
    assert billing.balance(ME) == 100 - PRICE


# --- 결제 서버가 죽었을 때 ---


async def test_a_round_held_at_opening_is_narrated_while_billing_is_down(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator: GatedNarrator,
    narrated,
):
    table = await start_duo(client, me, friend)
    await tick(app)
    billing.down = True

    await close_round(client, me, friend, table, narrated)

    # 열 때 잡아 둔 값으로 서술했다. 확정은 못 했지만 할 일로 남았다
    assert (await current(client, me, table))['scene'] == RESULT
    first, second = await charges_of(session, table)
    assert (first.status, first.attempts, first.last_error) == ('capture_due', 1, 'unreachable')
    assert second.status == 'pending'

    billing.down = False
    await tick(app, datetime.now(UTC) + timedelta(minutes=10))

    # 살아난 뒤에 정리 작업이 확정했다. 다음 라운드의 값도 잡았다
    assert await statuses_of(session, table) == ['captured', 'held']
    assert billing.balance(ME) == 1000 - 2 * PRICE


async def test_billing_down_at_opening_and_closing_stops_the_narration(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator: GatedNarrator,
    narrated,
):
    billing.down = True
    table = await start_duo(client, me, friend)
    await tick(app)

    await close_round(client, me, friend, table, narrated)

    # 값을 잡지 못했으니 서술하지 않는다. 결제 서버가 살아나면 방장이 다시 맡긴다
    assert narrator.requests == []
    assert (await last_event(client, friend, table))['payload'] == {'round': 1, 'reason': 'billing_unavailable'}
    assert await statuses_of(session, table) == ['pending']


async def test_the_settler_waits_longer_each_time_billing_does_not_answer(
    client: AsyncClient, app: FastAPI, session: AsyncSession, me: dict, friend: dict, billing: FakeBillingServer
):
    billing.down = True
    table = await start_duo(client, me, friend)
    start = datetime.now(UTC) + timedelta(seconds=1)

    await tick(app, start)
    [charge] = await charges_of(session, table)
    first_retry = charge.next_attempt_at
    await tick(app, start + timedelta(seconds=1))
    [charge] = await charges_of(session, table)
    tried_early = charge.attempts
    await tick(app, first_retry + timedelta(seconds=1))
    [charge] = await charges_of(session, table)

    assert first_retry == start + retry_delay(1)
    # 차례가 오기 전에는 부르지 않는다
    assert tried_early == 1
    # 두 번째에는 두 배를 기다린다
    assert charge.attempts == 2
    assert charge.next_attempt_at == first_retry + timedelta(seconds=1) + retry_delay(2)


def test_the_wait_doubles_up_to_a_limit():
    assert [retry_delay(n).total_seconds() for n in (1, 2, 3, 7, 30)] == [5, 10, 20, 300, 300]


@pytest.fixture
def held(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> HeldJobs:
    """앱이 맡기는 작업을 돌리지 않게 한다. 테스트가 서술 작업을 직접 돌린다."""
    jobs = HeldJobs()
    monkeypatch.setattr(app.state, 'jobs', jobs)
    return jobs


class SilentBilling:
    """답하지 않는 결제 서버."""

    async def hold(self, reference, user_id, price_code):
        await asyncio.Event().wait()


async def test_a_billing_server_that_never_answers_is_given_up(
    client: AsyncClient, app: FastAPI, session: AsyncSession, me: dict, friend: dict, held
):
    table, started = await hold_closing(client, app, me, friend)
    narrator = CountingNarrator()
    budgets = closing.Budgets(billing=0.05)

    with pytest.raises(ChargeNotSecured):
        async with asyncio.timeout(2):
            await closing.narrate_round(
                app.state.session_factory,
                narrator,
                uuid.UUID(table['id']),
                1,
                started,
                budgets=budgets,
                billing=SilentBilling(),
            )

    # 서술 값을 잡는 데 쓰는 시간이 다 되면 기다리지 않고 실패로 적는다. 서술자는 부르지 않았다
    assert narrator.calls == 0
    assert (await last_event(client, friend, table))['payload'] == {'round': 1, 'reason': 'billing_unavailable'}
    assert await statuses_of(session, table) == ['pending']


class StuckCaptureBilling:
    """홀드는 바로 잡고, 확정에는 답하지 않는 결제 서버."""

    async def hold(self, reference, user_id, price_code):
        return HoldOutcome(HoldResult.HELD)

    async def capture(self, reference):
        await asyncio.Event().wait()


async def test_a_capture_that_never_answers_is_left_to_the_settler(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    held,
    caplog: pytest.LogCaptureFixture,
):
    table, started = await hold_closing(client, app, me, friend)

    with caplog.at_level(logging.WARNING, logger='app.rounds.closing'):
        async with asyncio.timeout(2):
            await closing.narrate_round(
                app.state.session_factory,
                CountingNarrator(),
                uuid.UUID(table['id']),
                1,
                started,
                budgets=closing.Budgets(billing=0.05),
                billing=StuckCaptureBilling(),
            )

    # 라운드는 닫혔고 확정할 것은 DB 에 남았다. 기다리지 않고 정리 작업에 넘긴다
    assert (await current(client, me, table))['number'] == 2
    assert (await statuses_of(session, table))[0] == 'capture_due'
    [line] = rendered(caplog.records, 'app.rounds.closing')
    assert (line['level'], line['operation'], line['error_code']) == (
        'warning',
        'billing.capture',
        'billing.unavailable',
    )
    assert (line['table_id'], line['round']) == (table['id'], 1)


# --- 돌려주기 ---


async def test_ending_the_table_releases_its_charge(
    client: AsyncClient, app: FastAPI, session: AsyncSession, me: dict, friend: dict, billing: FakeBillingServer
):
    table = await start_duo(client, me, friend)
    await tick(app)

    ended = await client.post(table_url(table, '/end'), headers=me)
    await tick(app)

    assert ended.status_code == status.HTTP_200_OK
    assert await statuses_of(session, table) == ['released']
    assert billing.balance(ME) == 1000


async def test_a_short_charge_of_an_ended_table_is_closed_too(
    client: AsyncClient, app: FastAPI, session: AsyncSession, me: dict, friend: dict, billing: FakeBillingServer
):
    billing.balances[ME] = 0
    table = await start_duo(client, me, friend)
    await tick(app)

    await client.post(table_url(table, '/end'), headers=me)
    await tick(app)

    # 결제 서버에 홀드가 없다. 돌려주기는 없는 홀드(404)에도 된 것이다
    assert await statuses_of(session, table) == ['released']


async def test_a_table_ended_while_the_gm_narrates_gets_its_credits_back(
    client: AsyncClient,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator: GatedNarrator,
    narrated,
):
    table = await start_duo(client, me, friend)
    narrator.hold()
    await declare(client, me, table, MY_ACTION)
    await declare(client, friend, table, FRIENDS_ACTION)
    await narrator.wait_until_called()

    await client.post(table_url(table, '/end'), headers=me)
    narrator.release()
    await narrated()

    # 서술은 다음 장면이 되지 못했다. 받지 않는다
    assert await statuses_of(session, table) == ['released']
    assert billing.balance(ME) == 1000


async def test_a_failed_narration_keeps_the_hold_for_the_next_try(
    client: AsyncClient,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator: GatedNarrator,
    narrated,
):
    table = await start_duo(client, me, friend)
    narrator.fail_next = True
    await close_round(client, me, friend, table, narrated)
    failed = await statuses_of(session, table)

    await client.post(table_url(table, '/rounds/current/close'), headers=me)
    await narrated()

    # 실패해도 돌려주지 않았다. 다시 맡긴 서술이 같은 홀드를 썼다. 한 번만 빠졌다
    assert failed == ['held']
    assert await statuses_of(session, table) == ['captured', 'pending']
    assert billing.balance(ME) == 1000 - PRICE
    assert len(billing.holds) == 1


async def test_a_hold_that_lands_after_the_release_is_released_again(
    client: AsyncClient, app: FastAPI, session: AsyncSession, me: dict, friend: dict, billing: FakeBillingServer
):
    table = await start_duo(client, me, friend)
    [stale] = await charges_of(session, table)
    # 서술 작업이 걸어야 함을 읽은 뒤, 그사이 테이블이 끝나 정리 작업이 돌려줬다(결제 서버에는 아무것도 없었다)
    await client.post(table_url(table, '/end'), headers=me)
    await tick(app)
    session.expunge_all()

    readiness = await settling.secure(app.state.session_factory, app.state.billing, stale, datetime.now(UTC))
    released = await statuses_of(session, table)
    await tick(app)

    # 늦게 닿은 홀드가 크레딧을 붙잡고 있지 않게 한 번 더 돌려준다
    assert readiness == settling.Readiness.UNAVAILABLE
    assert released == ['release_due']
    assert await statuses_of(session, table) == ['released']
    assert billing.balance(ME) == 1000


async def test_a_hold_already_written_by_the_other_side_is_ready(
    client: AsyncClient, app: FastAPI, session: AsyncSession, me: dict, friend: dict, billing: FakeBillingServer
):
    table = await start_duo(client, me, friend)
    [stale] = await charges_of(session, table)
    await tick(app)

    readiness = await settling.secure(app.state.session_factory, app.state.billing, stale, datetime.now(UTC))

    # 정리 작업이 먼저 걸었다. 같은 이름표라 한 번만 빠졌고, 서술해도 된다
    assert readiness == settling.Readiness.READY
    assert billing.balance(ME) == 1000 - PRICE


# --- 연장 ---


async def overdue_extension(session: AsyncSession, table: dict) -> None:
    """걸린 청구의 연장할 때를 하루 전으로 돌린다. 정리 작업이 오래 멈춰 연장하지 못한 것이다."""
    for charge in await charges_of(session, table):
        charge.next_attempt_at = datetime.now(UTC) - timedelta(hours=12)
    await session.commit()


async def test_a_held_charge_is_extended_when_half_of_its_time_is_left(
    client: AsyncClient, app: FastAPI, session: AsyncSession, me: dict, friend: dict, billing: FakeBillingServer
):
    table = await start_duo(client, me, friend)
    start = datetime.now(UTC)
    billing.clock = lambda: start
    await tick(app, start)
    [charge] = await charges_of(session, table)
    first = charge.next_attempt_at

    await tick(app, start + timedelta(hours=1))
    early = list(billing.extended)
    later = start + timedelta(hours=12, seconds=1)
    billing.clock = lambda: later
    await tick(app, later)
    [charge] = await charges_of(session, table)

    # 결제 서버가 준 만료 시각(24시간 뒤)까지 남은 시간의 절반이 지나면 연장한다. 그 전에는 부르지 않는다.
    # 연장한 뒤에는 새 만료 시각까지 남은 시간의 절반 뒤다
    assert first == start + timedelta(hours=12)
    assert early == []
    assert billing.extended == [charge.reference]
    assert charge.next_attempt_at == later + timedelta(hours=12)
    assert billing.balance(ME) == 1000 - PRICE


async def test_a_short_hold_ttl_is_extended_sooner(
    client: AsyncClient, app: FastAPI, session: AsyncSession, me: dict, friend: dict, billing: FakeBillingServer
):
    # 결제 서버의 HOLD_TTL 은 설정이다. 1시간으로 둔 환경이면 30분 뒤에 연장한다
    billing.ttl = timedelta(hours=1)
    table = await start_duo(client, me, friend)
    start = datetime.now(UTC)
    billing.clock = lambda: start

    await tick(app, start)

    [charge] = await charges_of(session, table)
    assert charge.next_attempt_at == start + timedelta(minutes=30)


async def test_without_an_expiry_the_hold_is_extended_after_twelve_hours(
    client: AsyncClient, app: FastAPI, session: AsyncSession, me: dict, friend: dict
):
    # 결제 서버를 두지 않았다(받지 않는 것). 만료 시각을 모르므로 정해 둔 간격이다
    table = await start_duo(client, me, friend)
    start = datetime.now(UTC)

    await tick(app, start)

    [charge] = await charges_of(session, table)
    assert (charge.status, charge.next_attempt_at) == ('held', start + EXTEND_AFTER)


async def test_an_expired_hold_of_an_open_round_is_held_again_under_a_new_name(
    client: AsyncClient, app: FastAPI, session: AsyncSession, me: dict, friend: dict, billing: FakeBillingServer
):
    table = await start_duo(client, me, friend)
    start = datetime.now(UTC)
    await tick(app, start)
    [first] = await charges_of(session, table)
    billing.expire(first.reference)
    later = start + EXTEND_AFTER + timedelta(hours=1)

    first_reference = first.reference
    await tick(app, later)
    [renewed] = await charges_of(session, table)
    renewed_state = (renewed.status, renewed.renewals, renewed.last_error, renewed.reference)
    await tick(app, later)
    [charge] = await charges_of(session, table)

    # 만료되어 돌려준 홀드는 같은 이름표로 다시 걸 수 없다. 아직 서술 전이라 새 이름표로 다시 건다
    assert renewed_state == ('pending', 1, 'expired', f'{first_reference}:r1')
    assert charge.status == 'held'
    assert billing.statuses() == {first_reference: 'released', f'{first_reference}:r1': 'held'}
    assert billing.balance(ME) == 1000 - PRICE


async def test_a_missing_hold_is_held_again_under_the_same_name(
    client: AsyncClient, app: FastAPI, session: AsyncSession, me: dict, friend: dict, billing: FakeBillingServer
):
    table = await start_duo(client, me, friend)
    start = datetime.now(UTC)
    await tick(app, start)
    [first] = await charges_of(session, table)
    first_reference = first.reference
    # 결제 서버에 그 홀드가 없다(결제 서버의 DB 를 비웠다)
    billing.holds.clear()
    billing.balances[ME] = 1000
    later = start + EXTEND_AFTER + timedelta(hours=1)

    await tick(app, later)
    [missing] = await charges_of(session, table)
    missing_state = (missing.status, missing.renewals, missing.last_error)
    await tick(app, later)
    [charge] = await charges_of(session, table)

    assert missing_state == ('pending', 0, 'missing')
    assert (charge.status, charge.reference) == ('held', first_reference)
    assert billing.balance(ME) == 1000 - PRICE


async def test_a_renewed_hold_short_of_credits_is_told(
    client: AsyncClient, app: FastAPI, session: AsyncSession, me: dict, friend: dict, billing: FakeBillingServer
):
    table = await start_duo(client, me, friend)
    start = datetime.now(UTC)
    await tick(app, start)
    [first] = await charges_of(session, table)
    billing.expire(first.reference)
    # 돌려받은 크레딧을 그사이 다른 데 썼다
    billing.balances[ME] = 0
    later = start + EXTEND_AFTER + timedelta(hours=1)

    await tick(app, later)
    await tick(app, later)

    assert await statuses_of(session, table) == ['short']
    assert await event_types(client, friend, table) == ['narration_credits_short']


async def test_closing_after_a_missed_extension_holds_again_before_narrating(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator: GatedNarrator,
    narrated,
):
    table = await start_duo(client, me, friend)
    # 하루 전에 걸었고, 그 뒤로 정리 작업이 멈춰 연장하지 못했다. 그사이 결제 서버가 만료된 홀드를 돌려줬다
    await tick(app)
    await overdue_extension(session, table)
    [first] = await charges_of(session, table)
    first_reference = first.reference
    billing.expire(first_reference)

    await close_round(client, me, friend, table, narrated)

    # 서술하기 전에 연장해 보고, 만료된 것을 알고 새 이름표로 다시 걸었다. 그 값으로 서술하고 확정했다
    assert (await current(client, me, table))['scene'] == RESULT
    assert await statuses_of(session, table) == ['captured', 'pending']
    assert billing.statuses() == {first_reference: 'released', f'{first_reference}:r1': 'captured'}
    assert billing.balance(ME) == 1000 - PRICE


async def test_closing_with_an_extension_due_while_billing_is_down_still_narrates(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator: GatedNarrator,
    narrated,
):
    table = await start_duo(client, me, friend)
    await tick(app)
    await overdue_extension(session, table)
    billing.down = True

    await close_round(client, me, friend, table, narrated)

    # 연장할 때가 지났지만 만료까지는 여유가 있다. 걸린 것으로 보고 서술한다. 확정은 정리 작업이 마저 한다
    assert (await current(client, me, table))['scene'] == RESULT
    assert (await statuses_of(session, table))[0] == 'capture_due'


async def test_a_capture_of_an_expired_hold_is_not_paid(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator: GatedNarrator,
    narrated,
    caplog: pytest.LogCaptureFixture,
):
    table = await start_duo(client, me, friend)
    await tick(app)
    billing.down = True
    await close_round(client, me, friend, table, narrated)
    [first, _] = await charges_of(session, table)
    billing.down = False
    # 확정하지 못한 사이 결제 서버가 만료된 홀드를 돌려줬다
    billing.expire(first.reference)

    with caplog.at_level(logging.ERROR, logger='app.billing.settling'):
        await tick(app, datetime.now(UTC) + timedelta(minutes=10))

    # 서술은 이미 나갔다. 다시 걸지 않고 받지 못한 것으로 남긴다. 사람이 봐야 한다
    [charge, _] = await charges_of(session, table)
    assert (charge.status, charge.last_error) == ('failed', 'rejected_409')
    # 앞서 확정하지 못한 것(warning)도 같은 로거에 남아 있다. 오류는 이 한 줄이다
    [line] = [line for line in rendered(caplog.records, 'app.billing.settling') if line['level'] == 'error']
    assert (line['operation'], line['error_code']) == ('billing.capture', 'billing.rejected')
    # 1 라운드의 값은 돌아왔고(만료), 남은 것은 2 라운드의 홀드다
    assert billing.balance(ME) == 1000 - PRICE


async def test_an_extension_the_billing_server_refuses_keeps_the_hold(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    table = await start_duo(client, me, friend)
    start = datetime.now(UTC)
    await tick(app, start)
    monkeypatch.setattr(billing, 'extend', lambda reference: billing.answer(400))
    later = start + EXTEND_AFTER + timedelta(seconds=1)

    with caplog.at_level(logging.ERROR, logger='app.billing.settling'):
        await tick(app, later)

    # 실패로 적지 않는다. 홀드는 살아 있을 수 있고, 실패로 적으면 그 라운드를 서술할 수 없다. 한 시간 뒤에 다시 부른다
    [charge] = await charges_of(session, table)
    assert (charge.status, charge.last_error) == ('held', 'rejected_400')
    assert charge.next_attempt_at == later + EXTEND_REJECTED_RETRY
    [line] = rendered(caplog.records, 'app.billing.settling')
    assert (line['operation'], line['error_code']) == ('billing.extend', 'billing.rejected')


# --- 받아들여지지 않을 때 ---


async def test_a_rejected_hold_is_marked_failed_and_logged(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    caplog: pytest.LogCaptureFixture,
):
    table = await start_duo(client, me, friend)
    [charge] = await charges_of(session, table)
    # 같은 이름표를 다른 사용자로 이미 썼다. 결제 서버는 409 로 답한다
    billing.balances[FRIEND] = 1000
    billing.place({'reference': charge.reference, 'user_id': str(FRIEND), 'price_code': PRICE_CODE})

    with caplog.at_level(logging.ERROR, logger='app.billing.settling'):
        await tick(app)

    [charge] = await charges_of(session, table)
    assert (charge.status, charge.last_error) == ('failed', 'rejected_409')
    [line] = rendered(caplog.records, 'app.billing.settling')
    assert (line['error_code'], line['operation'], line['status_code']) == ('billing.rejected', 'billing.hold', 409)


async def test_a_refused_signature_is_logged_as_an_error(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    caplog: pytest.LogCaptureFixture,
):
    billing.secret = 'another-secret-0123456789abcdef0123'
    table = await start_duo(client, me, friend)

    with caplog.at_level(logging.WARNING, logger='app.billing.settling'):
        await tick(app)

    # 다시 부를 일이지만 설정이 틀린 것이라 사람이 봐야 한다
    [charge] = await charges_of(session, table)
    assert (charge.status, charge.last_error) == ('pending', 'unauthorized')
    [line] = rendered(caplog.records, 'app.billing.settling')
    assert (line['level'], line['error_code'], line['reason']) == ('error', 'billing.unavailable', 'unauthorized')
    assert billing.secret not in caplog.text


@pytest.mark.parametrize(
    ('reason', 'expected'),
    [('insufficient_credits', 'insufficient_credits'), ('billing_unavailable', 'billing_unavailable')],
)
def test_the_reason_of_an_unsecured_charge_is_told(reason: str, expected: str):
    assert failure_reason(ChargeNotSecured(reason)) == expected


# --- 결제 서버 없이 ---


async def test_without_a_billing_server_the_charges_still_move(
    client: AsyncClient, session: AsyncSession, me: dict, friend: dict, narrator: GatedNarrator, narrated
):
    table = await start_duo(client, me, friend)

    await close_round(client, me, friend, table, narrated)

    # 받지 않는 것(FreeBilling)이 꽂혀 있다. 길은 같고 받는 일만 하지 않는다
    assert await statuses_of(session, table) == ['captured', 'pending']


# --- 정리 작업 ---


async def test_each_round_of_the_settler_is_a_job_with_one_line(
    client: AsyncClient,
    app: FastAPI,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    caplog: pytest.LogCaptureFixture,
):
    with caplog.at_level(logging.DEBUG, logger='app.billing.settler'):
        await tick(app)
        await start_duo(client, me, friend)
        await tick(app)

    idle, busy = rendered(caplog.records, 'app.billing.settler')
    # 할 일이 없던 바퀴는 debug, 한 일이 있던 바퀴는 info. 바퀴마다 다른 작업이다
    assert (idle['level'], idle['settled'], busy['level'], busy['settled']) == ('debug', 0, 'info', 1)
    assert {idle['operation'], busy['operation']} == {'charge.settle'}
    assert idle['job_id'] != busy['job_id']


async def test_one_failing_charge_does_not_stop_the_others(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    broken = await start_duo(client, me, friend)
    working = await start_duo(client, me, friend)
    [broken_charge] = await charges_of(session, broken)
    real_settle = settling.settle

    async def settle(session_factory, billing, charge, now):
        if charge.id == broken_charge.id:
            raise RuntimeError('버그')
        await real_settle(session_factory, billing, charge, now)

    monkeypatch.setattr(settling, 'settle', settle)
    with caplog.at_level(logging.ERROR, logger='app.billing.settler'):
        await tick(app)

    assert await statuses_of(session, working) == ['held']
    assert await statuses_of(session, broken) == ['pending']
    [failure] = rendered(caplog.records, 'app.billing.settler')
    assert (failure['charge_id'], failure['error_code']) == (str(broken_charge.id), 'job.failed')


async def test_the_settler_runs_until_told_to_stop(app: FastAPI, monkeypatch: pytest.MonkeyPatch):
    ticks = []

    async def count(self):
        ticks.append(1)
        raise RuntimeError('DB 가 없다')

    monkeypatch.setattr(ChargeSettler, 'tick', count)
    running = charge_settler.start(replace(app.state.charge_settler, interval=0.01))
    await asyncio.sleep(0.05)
    await asyncio.wait_for(running.halt(), timeout=1)

    # 한 바퀴가 통째로 실패해도 멈추지 않고, 멈추라면 멈춘다
    assert len(ticks) >= 2
    assert running.task.done()


async def test_the_server_runs_the_settler_while_it_is_up(settings, auth_server, monkeypatch: pytest.MonkeyPatch):
    ticks = []

    async def count(self):
        ticks.append(1)

    monkeypatch.setattr(ChargeSettler, 'tick', count)
    server = create_app(settings, http_client=auth_server.make_client())

    async with server.router.lifespan_context(server):
        await asyncio.sleep(0.05)
        started = len(ticks)
    await asyncio.sleep(0.05)

    assert started >= 1
    assert len(ticks) == started
    # 부를 때마다 앱에 꽂힌 결제 서버를 꺼낸다
    assert server.state.charge_settler.billing() is server.state.billing
