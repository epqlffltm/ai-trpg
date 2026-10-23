# trpg-server/tests/test_credit_waits.py

"""
크레딧이 모자란 사람을 기다리는 기한(#181)을 검증한다. 결제 서버 자리에 가짜를 꽂는다(tests/billing.py).

보는 것.
  - 테이블의 설정: 기다리는 시간은 고르지 않으면 5 분, 30 초~1 시간. 자동으로 빼기는 기본 켬. 목록과 상세에 보인다.
    방장만 바꾼다. 이벤트로 남는다. 같은 값이면 아무것도 적지 않는다. DB 도 범위를 지킨다.
  - 시간: 서술이 크레딧 부족으로 실패한 때부터 센다. 지나기 전에는 아무것도 하지 않는다. 바꾼 시간은 바로 쓴다.
  - 켬: 모자란 사람을 빼고 나머지로 다시 서술한다. 방장이 모자라면 방장을 넘긴다. 모두 모자라면 아무도 빼지 않는다.
  - 끔: 낼 수 있는 사람의 값을 돌려주고 멈춘 채로 둔다. 다시 맡기면 새 이름표로 다시 걸어 서술한다. 한 번만 빠진다.
  - 한 번 한 뒤에는 다시 하지 않는다. 시계의 한 바퀴 줄에 한 수가 실린다.
서버의 시계가 보는 시각은 테스트가 정한다(RoundClock.clock).
"""

import logging
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing import repository as billing_repository
from app.rounds import credit_waits
from app.rounds.closing import closer_of
from app.tables.models import CREDIT_WAIT_MAX, CREDIT_WAIT_MIN, DEFAULT_CREDIT_WAIT
from tests.billing import FakeBillingServer
from tests.logs import rendered
from tests.test_narration_billing import PRICE, charges_of, close_round, tick
from tests.test_npc_actions import events_of
from tests.test_round_closing import FRIEND, ME, RESULT, GatedNarrator, bearer, current, table_url
from tests.test_round_time_limit import clock_at, open_with, start_with

pytestmark = pytest.mark.usefixtures('clean_tables')

# 각자의 처음 크레딧
CREDITS = 1000
# 시계의 시각을 기한에서 이만큼 비켜 둔다
PAST = timedelta(seconds=1)


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """함께 앉는 사람."""
    return bearer(signing_key, FRIEND)


@pytest.fixture
async def billing(app: FastAPI) -> FakeBillingServer:
    """앱에 꽂은 가짜 결제 서버. 둘 다 CREDITS 만큼 있다."""
    server = FakeBillingServer(balances={ME: CREDITS, FRIEND: CREDITS})
    client = server.make_client()
    app.state.billing = server.billing(client)
    yield server
    await client.aclose()


@pytest.fixture
def narrator(app: FastAPI) -> GatedNarrator:
    """앱에 꽂은 문 앞의 서술자. 문이 열려 있다."""
    gated = GatedNarrator()
    gated.release()
    app.state.narrator = gated
    yield gated
    gated.release()


async def stall(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, billing: FakeBillingServer, narrated, **options
) -> tuple[dict, datetime]:
    """
    함께 앉는 사람이 모자라 서술이 멈춘 테이블을 만든다. 테이블과 서술이 실패한 시각을 돌려준다.

    options 는 테이블을 만들 때 보내는 칸이다(credit_wait_seconds, remove_short_payers).
    라운드의 시간 제한은 없앤다. 시계를 몇 분 뒤로 돌릴 때 다음 라운드가 마감으로 닫히지 않게 한다.
    """
    billing.balances[FRIEND] = 0
    table = await start_with(client, me, friend, round_time_limit=None, **options)
    await tick(app)
    await close_round(client, me, friend, table, narrated)
    failed_at = (await current(client, me, table))['narration_failed_at']
    assert failed_at is not None
    return table, datetime.fromisoformat(failed_at)


async def statuses(session: AsyncSession, table: dict, payer: uuid.UUID) -> list[str]:
    """그 사람의 청구들의 상태. 라운드 순서다."""
    return [charge.status for charge in await charges_of(session, table, payer)]


async def member_ids(client: AsyncClient, headers: dict, table: dict) -> list[str]:
    """앉아 있는 사람들."""
    detail = (await client.get(table_url(table), headers=headers)).json()
    return [member['user_id'] for member in detail['members']]


async def set_wait(client: AsyncClient, headers: dict, table: dict, seconds: int, remove: bool):
    """기다리는 규칙을 바꾼다. 응답을 그대로 돌려준다."""
    body = {'credit_wait_seconds': seconds, 'remove_short_payers': remove}
    return await client.put(table_url(table, '/credit-wait'), json=body, headers=headers)


# --- 테이블의 설정 ---


async def test_the_defaults_are_five_minutes_and_removing(client: AsyncClient, me: dict):
    response = await open_with(client, me)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    body = response.json()
    assert (body['credit_wait_seconds'], body['remove_short_payers']) == (DEFAULT_CREDIT_WAIT, True)
    assert DEFAULT_CREDIT_WAIT == 300


async def test_the_rules_can_be_chosen_when_creating(client: AsyncClient, me: dict):
    response = await open_with(client, me, credit_wait_seconds=CREDIT_WAIT_MAX, remove_short_payers=False)
    listed = (await client.get('/api/v1/game/tables', headers=me)).json()

    assert (response.json()['credit_wait_seconds'], response.json()['remove_short_payers']) == (CREDIT_WAIT_MAX, False)
    assert [(item['credit_wait_seconds'], item['remove_short_payers']) for item in listed['items']] == [
        (CREDIT_WAIT_MAX, False)
    ]


@pytest.mark.parametrize('seconds', [CREDIT_WAIT_MIN - 1, CREDIT_WAIT_MAX + 1, None, '오 분'])
async def test_a_wait_out_of_range_is_rejected(client: AsyncClient, me: dict, seconds):
    response = await open_with(client, me, credit_wait_seconds=seconds)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_host_changes_the_rules_and_it_is_recorded(client: AsyncClient, me: dict):
    table = await start_with(client, me)

    response = await set_wait(client, me, table, 60, False)
    (changed,) = await events_of(client, me, table, 'credit_wait_changed')

    assert response.status_code == status.HTTP_200_OK, response.text
    assert (response.json()['credit_wait_seconds'], response.json()['remove_short_payers']) == (60, False)
    assert (changed['actor_id'], changed['payload']) == (
        str(ME),
        {'credit_wait_seconds': 60, 'remove_short_payers': False},
    )


async def test_the_same_rules_write_nothing(client: AsyncClient, me: dict):
    table = await start_with(client, me)

    response = await set_wait(client, me, table, DEFAULT_CREDIT_WAIT, True)

    assert response.status_code == status.HTTP_200_OK
    assert await events_of(client, me, table, 'credit_wait_changed') == []


async def test_only_the_host_changes_the_rules(client: AsyncClient, me: dict, friend: dict):
    table = await start_with(client, me, friend, round_time_limit=None)

    response = await set_wait(client, friend, table, 60, True)

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_an_ended_table_keeps_its_rules(client: AsyncClient, me: dict):
    table = await start_with(client, me)
    await client.post(table_url(table, '/end'), headers=me)

    response = await set_wait(client, me, table, 60, True)

    assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.parametrize(
    'body',
    [
        {'credit_wait_seconds': 60},
        {'remove_short_payers': True},
        {'credit_wait_seconds': 10, 'remove_short_payers': True},
        {'credit_wait_seconds': 60, 'remove_short_payers': True, 'now': True},
    ],
)
async def test_a_bad_change_is_rejected(client: AsyncClient, me: dict, body: dict):
    table = await start_with(client, me)

    response = await client.put(table_url(table, '/credit-wait'), json=body, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_database_keeps_the_range(client: AsyncClient, me: dict, session: AsyncSession):
    table = (await open_with(client, me)).json()

    with pytest.raises(IntegrityError):
        await session.execute(
            text('UPDATE game_tables SET credit_wait_seconds = 10 WHERE id = :id'), {'id': uuid.UUID(table['id'])}
        )
    await session.rollback()


# --- 기다리는 시간 ---


async def test_nothing_happens_before_the_wait_is_over(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator,
    narrated,
):
    table, failed_at = await stall(client, app, me, friend, billing, narrated)

    await clock_at(app, failed_at + timedelta(seconds=DEFAULT_CREDIT_WAIT) - PAST).tick()

    # 아직 기다린다. 모자란 사람이 충전하거나 방장이 내보낼 수 있다
    assert await member_ids(client, me, table) == [str(ME), str(FRIEND)]
    assert await statuses(session, table, ME) == ['held']
    assert await events_of(client, me, table, 'member_dropped') == []


async def test_a_changed_wait_is_used_at_once(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, billing: FakeBillingServer, narrator, narrated
):
    table, failed_at = await stall(client, app, me, friend, billing, narrated)

    await set_wait(client, me, table, CREDIT_WAIT_MIN, True)
    await clock_at(app, failed_at + timedelta(seconds=CREDIT_WAIT_MIN) + PAST).tick()
    await narrated()

    # 기다리는 동안 줄인 시간이 지금 기다리는 라운드에 바로 쓰였다
    assert await member_ids(client, me, table) == [str(ME)]


# --- 켬: 모자란 사람을 뺀다 ---


async def test_the_short_one_is_dropped_and_the_rest_go_on(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator,
    narrated,
):
    table, failed_at = await stall(client, app, me, friend, billing, narrated)

    await clock_at(app, failed_at + timedelta(seconds=DEFAULT_CREDIT_WAIT) + PAST).tick()
    await narrated()
    (dropped,) = await events_of(client, me, table, 'member_dropped')

    # 모자란 사람을 자리에서 빼고 바로 다시 서술했다. 뺀 사람은 내지 않았다
    assert dropped['payload'] == {'round': 1, 'user_id': str(FRIEND), 'character_name': '캐릭터1'}
    assert await member_ids(client, me, table) == [str(ME)]
    assert (await current(client, me, table))['scene'] == RESULT
    assert (await statuses(session, table, ME))[0] == 'captured'
    assert await statuses(session, table, FRIEND) == ['released']
    assert (billing.balance(ME), billing.balance(FRIEND)) == (CREDITS - PRICE, 0)


async def test_a_short_host_is_dropped_and_the_seat_is_handed_over(
    client: AsyncClient,
    app: FastAPI,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator,
    narrated,
):
    billing.balances[ME] = 0
    table = await start_with(client, me, friend, round_time_limit=None)
    await tick(app)
    await close_round(client, me, friend, table, narrated)
    failed_at = datetime.fromisoformat((await current(client, me, table))['narration_failed_at'])

    await clock_at(app, failed_at + timedelta(seconds=DEFAULT_CREDIT_WAIT) + PAST).tick()
    await narrated()
    (handed,) = await events_of(client, friend, table, 'host_changed')

    # 방장도 같다. 빠지면 남은 사람이 방장이 된다(나가기와 같다)
    assert handed['payload'] == {'user_id': str(FRIEND)}
    assert await member_ids(client, friend, table) == [str(FRIEND)]
    assert (await current(client, friend, table))['scene'] == RESULT
    assert billing.balance(FRIEND) == CREDITS - PRICE


async def test_when_everyone_is_short_no_one_is_dropped(
    client: AsyncClient,
    app: FastAPI,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator,
    narrated,
):
    billing.balances[ME] = 0
    billing.balances[FRIEND] = 0
    table = await start_with(client, me, friend, round_time_limit=None)
    await close_round(client, me, friend, table, narrated)
    failed_at = datetime.fromisoformat((await current(client, me, table))['narration_failed_at'])

    await clock_at(app, failed_at + timedelta(seconds=DEFAULT_CREDIT_WAIT) + PAST).tick()

    # 빼면 앉은 사람이 없어진다. 묶인 값도 없다. 그대로 기다린다
    assert await member_ids(client, me, table) == [str(ME), str(FRIEND)]
    assert await events_of(client, me, table, 'member_dropped') == []
    assert await events_of(client, me, table, 'narration_credits_released') == []


async def test_it_happens_only_once(
    client: AsyncClient,
    app: FastAPI,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator,
    narrated,
    caplog: pytest.LogCaptureFixture,
):
    table, failed_at = await stall(client, app, me, friend, billing, narrated)
    moment = failed_at + timedelta(seconds=DEFAULT_CREDIT_WAIT) + PAST

    with caplog.at_level(logging.DEBUG, logger='app.rounds.clock'):
        await clock_at(app, moment).tick()
        await narrated()
        await clock_at(app, moment).tick()

    # 뺀 뒤에는 모자란 청구가 없다. 두 번째 바퀴는 할 일이 없다. 한 바퀴의 줄에 한 수가 실린다
    first, second = rendered(caplog.records, 'app.rounds.clock')
    assert (first['level'], first['credit_waits'], first['closed']) == ('info', 1, 0)
    assert (second['level'], second['credit_waits']) == ('debug', 0)
    assert len(await events_of(client, me, table, 'member_dropped')) == 1


async def test_a_round_retried_after_topping_up_is_left_alone(
    client: AsyncClient,
    app: FastAPI,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator,
    narrated,
):
    table, failed_at = await stall(client, app, me, friend, billing, narrated)
    billing.balances[FRIEND] = CREDITS
    await client.post(table_url(table, '/rounds/current/close'), headers=me)
    await narrated()

    await clock_at(app, failed_at + timedelta(seconds=DEFAULT_CREDIT_WAIT) + PAST).tick()

    # 기다리는 동안 충전해서 서술됐다. 아무도 빼지 않는다
    assert await member_ids(client, me, table) == [str(ME), str(FRIEND)]
    assert (await current(client, me, table))['number'] == 2


# --- 끔: 낼 수 있는 사람의 값을 돌려준다 ---


async def test_without_removing_the_others_get_their_credits_back(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator,
    narrated,
):
    table, failed_at = await stall(client, app, me, friend, billing, narrated, remove_short_payers=False)

    await clock_at(app, failed_at + timedelta(seconds=DEFAULT_CREDIT_WAIT) + PAST).tick()
    await tick(app)
    (released,) = await events_of(client, me, table, 'narration_credits_released')

    # 아무도 빼지 않는다. 방장의 값은 돌아왔다. 라운드는 멈춘 채로 있다
    assert released['payload'] == {'round': 1}
    assert await member_ids(client, me, table) == [str(ME), str(FRIEND)]
    assert await statuses(session, table, ME) == ['released']
    assert billing.balance(ME) == CREDITS
    assert (await current(client, me, table))['status'] == 'closing'


async def test_handing_it_again_holds_everyone_anew_and_charges_once(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator,
    narrated,
):
    table, failed_at = await stall(client, app, me, friend, billing, narrated, remove_short_payers=False)
    await clock_at(app, failed_at + timedelta(seconds=DEFAULT_CREDIT_WAIT) + PAST).tick()

    billing.balances[FRIEND] = CREDITS
    retried = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    await narrated()
    [mine] = (await charges_of(session, table))[:1]

    # 돌려줬던 방장의 값은 새 이름표로 다시 걸었다. 둘 다 한 번씩만 빠졌다
    assert retried.status_code == status.HTTP_202_ACCEPTED, retried.text
    assert (await current(client, me, table))['scene'] == RESULT
    assert (mine.status, mine.reference) == ('captured', f'narration:{table["id"]}:1:{ME}:r1')
    assert (await statuses(session, table, FRIEND))[0] == 'captured'
    assert (billing.balance(ME), billing.balance(FRIEND)) == (CREDITS - PRICE, CREDITS - PRICE)


async def test_handing_it_again_while_still_short_waits_again(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator,
    narrated,
):
    table, failed_at = await stall(client, app, me, friend, billing, narrated, remove_short_payers=False)
    await clock_at(app, failed_at + timedelta(seconds=DEFAULT_CREDIT_WAIT) + PAST).tick()

    await client.post(table_url(table, '/rounds/current/close'), headers=me)
    await narrated()

    # 아직 모자라 다시 실패했다. 방장의 값은 다시 걸렸고, 다시 기다린다
    assert len(await events_of(client, me, table, 'narration_failed')) == 2
    assert await statuses(session, table, ME) == ['held']
    assert billing.balance(ME) == CREDITS - PRICE


async def test_a_retry_that_fails_again_is_told_again(
    client: AsyncClient,
    app: FastAPI,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator: GatedNarrator,
    narrated,
):
    table, failed_at = await stall(client, app, me, friend, billing, narrated)
    narrator.fail_next = True

    await clock_at(app, failed_at + timedelta(seconds=DEFAULT_CREDIT_WAIT) + PAST).tick()
    await narrated()

    # 다시 맡긴 서술은 새 서술이다(실패의 표시를 지웠다). 또 실패하면 다시 알리고 방장이 다시 맡길 수 있다
    reasons = [event['payload']['reason'] for event in await events_of(client, me, table, 'narration_failed')]
    assert reasons == ['insufficient_credits', 'error']


# --- 찾기와 다시 보기 ---


async def test_the_finder_picks_only_rounds_whose_wait_is_over(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator,
    narrated,
):
    table, failed_at = await stall(client, app, me, friend, billing, narrated)
    wait = timedelta(seconds=DEFAULT_CREDIT_WAIT)

    async def found(moment: datetime) -> list[uuid.UUID]:
        return await billing_repository.find_waiting_table_ids(
            session, moment, credit_waits.WAITED_FOR, credit_waits.PAYABLE, 50
        )

    # 기다리는 시간을 DB 에서 센다. 서버가 여럿이어도 같은 기준이다
    assert await found(failed_at + wait - PAST) == []
    assert await found(failed_at + wait + PAST) == [uuid.UUID(table['id'])]


async def test_the_finder_skips_rounds_with_nothing_held(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator,
    narrated,
):
    billing.balances[ME] = 0
    billing.balances[FRIEND] = 0
    table = await start_with(client, me, friend, round_time_limit=None)
    await close_round(client, me, friend, table, narrated)
    failed_at = datetime.fromisoformat((await current(client, me, table))['narration_failed_at'])

    later = failed_at + timedelta(seconds=DEFAULT_CREDIT_WAIT) + PAST
    found = await billing_repository.find_waiting_table_ids(
        session, later, credit_waits.WAITED_FOR, credit_waits.PAYABLE, 50
    )

    # 모두 모자라 묶인 값이 없다. 바퀴마다 고르지 않는다
    assert found == []


async def test_settling_looks_again_after_locking(
    client: AsyncClient,
    app: FastAPI,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator,
    narrated,
):
    table, failed_at = await stall(client, app, me, friend, billing, narrated)
    table_id = uuid.UUID(table['id'])
    early = failed_at + timedelta(seconds=DEFAULT_CREDIT_WAIT) - PAST

    # 고른 뒤 잠그기 전에 방장이 시간을 늘렸을 수 있다. 잠근 뒤의 테이블로 다시 본다
    async with app.state.session_factory() as session:
        done = await credit_waits.settle_credit_wait(session, table_id, early, closer_of(app.state))

    assert done is False
    assert await member_ids(client, me, table) == [str(ME), str(FRIEND)]


async def test_settling_does_nothing_when_nothing_is_held(
    client: AsyncClient,
    app: FastAPI,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator,
    narrated,
):
    billing.balances[ME] = 0
    billing.balances[FRIEND] = 0
    table = await start_with(client, me, friend, round_time_limit=None)
    await close_round(client, me, friend, table, narrated)
    failed_at = datetime.fromisoformat((await current(client, me, table))['narration_failed_at'])
    later = failed_at + timedelta(seconds=DEFAULT_CREDIT_WAIT) + PAST

    async with app.state.session_factory() as session:
        done = await credit_waits.settle_credit_wait(session, uuid.UUID(table['id']), later, closer_of(app.state))

    # 모두 모자라면 아무도 빼지 않는다(빼면 앉은 사람이 없어진다)
    assert done is False
    assert await member_ids(client, me, table) == [str(ME), str(FRIEND)]
