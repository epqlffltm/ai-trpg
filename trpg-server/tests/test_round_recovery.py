# trpg-server/tests/test_round_recovery.py

"""
서술을 맡은 작업이 사라진 라운드를 서버의 시계가 다시 맡기는 것(app/rounds/recovery.py, #275)을 검증한다.

작업이 사라지는 것은 HeldJobs 로 흉내 낸다. 맡은 작업을 돌리지 않고 버린다. 서버가 서술 도중에 죽은 것과 같다.
시계의 "지금"은 테스트가 정한다. 닫기 시작한 시각에서 service.CLOSING_RETRY_SECONDS 를 더한 때가 사라졌다고 보는 때다.

다섯을 본다.
  - 다시 맡기기: 사라진 서술을 다시 맡겨 다음 라운드가 열린다.
    아직 기다릴 때, 실패를 적은 때, 끝난 테이블은 그대로 둔다.
  - 그만두기: 정해 둔 횟수를 넘으면 실패(stalled)로 적어 알린다. 방장이 다시 맡기면 횟수를 다시 센다.
  - 서버가 여럿: 같은 라운드를 동시에 보아도 한 번만 다시 맡긴다.
  - 자리가 다 찬 서술: 맡지 않은 서술도 같은 길로 다시 맡긴다.
  - 기록: 시계의 한 바퀴에 다시 맡긴 수가 남는다.
"""

import asyncio
import logging
import uuid
from collections import Counter
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import select, update

from app.core.jobs import BackgroundJobs, Limit
from app.rounds import closing, recovery, service
from app.rounds.clock import RoundClock
from app.rounds.closing import closer_of
from app.rounds.models import Round
from app.rounds.recovery import AUTO_RETRY_LIMIT, STALLED, Recovery
from tests.logs import rendered
from tests.test_round_closing import (
    FRIEND,
    FRIENDS_ACTION,
    ME,
    MY_ACTION,
    HeldJobs,
    bearer,
    current,
    declare,
    event_types,
    last_event,
    start_duo,
    started_at,
    table_url,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

CLOCK_LOGGER = 'app.rounds.clock'


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장의 머리말. 캐릭터는 '엘프'다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """함께 앉는 사람의 머리말. 캐릭터는 '영애'다."""
    return bearer(signing_key, FRIEND)


@pytest.fixture
def held(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> HeldJobs:
    """앱이 맡기는 작업을 버린다. 서술을 맡은 작업이 사라진 것과 같다."""
    jobs = HeldJobs()
    monkeypatch.setattr(app.state, 'jobs', jobs)
    return jobs


def clock_at(app: FastAPI, when: datetime) -> RoundClock:
    """지금이 when 인 서버의 시계. 앱에 꽂혀 있는 서술자와 작업 관리자로 다시 맡긴다."""
    return RoundClock(
        session_factory=app.state.session_factory,
        scheduler=lambda: closer_of(app.state),
        dice=lambda: app.state.dice,
        clock=lambda: when,
    )


def vanished_at(started: datetime) -> datetime:
    """started 에 닫기 시작한 라운드의 서술이 사라졌다고 보는 가장 이른 때."""
    return started + timedelta(seconds=service.CLOSING_RETRY_SECONDS)


async def close_round(client: AsyncClient, me: dict, friend: dict, table: dict) -> None:
    """둘 다 선언을 내서 라운드를 닫기 시작하게 한다."""
    await declare(client, me, table, MY_ACTION)
    await declare(client, friend, table, FRIENDS_ACTION)


async def round_row(app: FastAPI, table: dict, number: int = 1) -> Round:
    """라운드를 DB 에서 바로 읽는다."""
    async with app.state.session_factory() as session:
        query = select(Round).where(Round.table_id == uuid.UUID(table['id']), Round.number == number)
        return await session.scalar(query)


async def sweep_later(app: FastAPI, table: dict) -> Counter[Recovery]:
    """라운드의 서술이 사라졌다고 보는 때의 시계로 한 번 쓸어 담는다."""
    return await clock_at(app, vanished_at(await started_at(app, table))).sweep_vanished()


# --- 다시 맡기기 ---


async def test_a_round_whose_narration_vanished_is_narrated_again(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, held: HeldJobs, monkeypatch, narrated
):
    table = await start_duo(client, me, friend)
    await close_round(client, me, friend, table)
    # 서버가 다시 떴다. 이제 맡은 작업이 돈다
    monkeypatch.setattr(app.state, 'jobs', BackgroundJobs())

    done = await sweep_later(app, table)
    await narrated()

    assert done == Counter({Recovery.RETRIED: 1})
    # 서술이 끝나 다음 라운드가 열렸다. 실패를 적지 않았다. 다시 맡긴 것은 이벤트로 적지 않는다
    assert (await current(client, me, table))['number'] == 2
    assert await event_types(client, me, table) == [
        'player_action',
        'player_action',
        'round_closed',
        'gm_narration',
        'round_opened',
    ]
    assert (await round_row(app, table)).auto_retries == 1


async def test_a_round_still_within_its_time_is_left_alone(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, held: HeldJobs
):
    table = await start_duo(client, me, friend)
    await close_round(client, me, friend, table)
    started = await started_at(app, table)

    done = await clock_at(app, vanished_at(started) - timedelta(seconds=1)).sweep_vanished()

    # 아직 도는 서술일 수 있다. 위에 또 맡기지 않는다
    assert done == Counter()
    assert held.names == [f'narrate:{table["id"]}:1']
    assert (await round_row(app, table)).closing_at == started


async def test_a_failed_round_is_left_to_the_host(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, held: HeldJobs, session
):
    table = await start_duo(client, me, friend)
    await close_round(client, me, friend, table)
    started = await started_at(app, table)
    await session.execute(update(Round).where(Round.closing_at == started).values(narration_failed_at=started))
    await session.commit()

    done = await sweep_later(app, table)

    # 실패한 까닭(크레딧, 모델)이 그대로면 다시 해도 같다. 방장과 크레딧 기다리기의 몫이다
    assert done == Counter()
    assert len(held.names) == 1


async def test_an_ended_table_is_left_alone(client: AsyncClient, app: FastAPI, me: dict, friend: dict, held: HeldJobs):
    table = await start_duo(client, me, friend)
    await close_round(client, me, friend, table)
    ended = await client.post(table_url(table, '/end'), headers=me)

    done = await sweep_later(app, table)

    assert ended.status_code == status.HTTP_200_OK
    # 끝난 테이블의 닫는 중인 라운드는 고르지도 않는다. 고르면 바퀴마다 다시 고른다
    assert done == Counter()
    assert len(held.names) == 1


# --- 그만두기 ---


async def vanish_until_given_up(app: FastAPI, table: dict) -> list[Counter[Recovery]]:
    """다시 맡겨도 작업이 계속 사라진다. 그만둘 때까지 쓸어 담는다. 바퀴마다 한 일을 돌려준다."""
    return [await sweep_later(app, table) for _ in range(AUTO_RETRY_LIMIT + 1)]


async def test_the_server_gives_up_after_retrying_enough(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, held: HeldJobs
):
    table = await start_duo(client, me, friend)
    await close_round(client, me, friend, table)

    rounds = await vanish_until_given_up(app, table)

    # 정해 둔 횟수만큼 다시 맡기고, 그 뒤에는 그만둔다
    assert rounds == [Counter({Recovery.RETRIED: 1})] * AUTO_RETRY_LIMIT + [Counter({Recovery.GAVE_UP: 1})]
    assert len(held.names) == 1 + AUTO_RETRY_LIMIT
    # 실패로 적어 앉은 사람 모두에게 알린다. 라운드는 닫는 중에 머문다
    failed = await last_event(client, me, table)
    assert (failed['type'], failed['payload']['reason']) == ('narration_failed', STALLED)
    row = await round_row(app, table)
    assert row.narration_failed_at is not None
    assert row.closed_at is None
    # 그만둔 뒤에는 더 보지 않는다
    assert await sweep_later(app, table) == Counter()


async def test_the_host_hands_a_given_up_round_again_and_the_count_restarts(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, held: HeldJobs
):
    table = await start_duo(client, me, friend)
    await close_round(client, me, friend, table)
    await vanish_until_given_up(app, table)

    # 실패로 적혔으니 방장은 기다리지 않고 다시 맡긴다
    again = await client.post(table_url(table, '/rounds/current/close'), headers=me)

    assert again.status_code == status.HTTP_202_ACCEPTED
    assert (await round_row(app, table)).auto_retries == 0
    # 방장이 맡긴 것이 또 사라지면 서버가 다시 스스로 맡긴다
    assert await sweep_later(app, table) == Counter({Recovery.RETRIED: 1})


def test_the_limit_is_small_but_not_zero():
    assert 1 <= AUTO_RETRY_LIMIT <= 3


# --- 서버가 여럿 ---


async def test_two_servers_hand_it_again_only_once(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, held: HeldJobs
):
    table = await start_duo(client, me, friend)
    await close_round(client, me, friend, table)
    when = vanished_at(await started_at(app, table))
    table_id = uuid.UUID(table['id'])

    done = await asyncio.gather(
        clock_at(app, when).recover_one(table_id, when), clock_at(app, when).recover_one(table_id, when)
    )

    # 먼저 잠근 서버가 닫기 시작한 시각을 고친다. 뒤의 서버는 고친 시각을 보고 지나간다
    assert sorted(done) == sorted([Recovery.RETRIED, Recovery.NOTHING])
    assert len(held.names) == 2


# --- 자리가 다 찬 서술 ---


async def test_a_narration_refused_for_lack_of_room_is_handed_later(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, monkeypatch, narrated
):
    jobs = BackgroundJobs({closing.NARRATE_OPERATION: Limit(1, 1)})
    monkeypatch.setattr(app.state, 'jobs', jobs)
    busy = asyncio.Event()

    async def other_table() -> None:
        await busy.wait()

    jobs.spawn(other_table(), name='narrate:다른 테이블:1', operation=closing.NARRATE_OPERATION)
    table = await start_duo(client, me, friend)
    await close_round(client, me, friend, table)

    # 자리가 없어 맡지 않았다. 라운드는 닫는 중으로 남는다
    assert jobs.count(closing.NARRATE_OPERATION) == 1
    assert (await current(client, me, table))['status'] == 'closing'

    busy.set()
    await narrated()
    done = await sweep_later(app, table)
    await narrated()

    assert done == Counter({Recovery.RETRIED: 1})
    assert (await current(client, me, table))['number'] == 2


# --- 기록 ---


async def test_the_clock_counts_what_it_handed_again(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, held: HeldJobs, caplog: pytest.LogCaptureFixture
):
    table = await start_duo(client, me, friend)
    await close_round(client, me, friend, table)
    when = vanished_at(await started_at(app, table))

    with caplog.at_level(logging.DEBUG, logger=CLOCK_LOGGER):
        await clock_at(app, when).tick()

    (line,) = rendered(caplog.records, CLOCK_LOGGER)
    # 한 일이 있는 바퀴라 info 다
    assert line['level'] == 'info'
    assert (line['recovered'], line['gave_up']) == (1, 0)


async def test_giving_up_leaves_a_line_for_a_person(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, held: HeldJobs, caplog: pytest.LogCaptureFixture
):
    table = await start_duo(client, me, friend)
    await close_round(client, me, friend, table)

    with caplog.at_level(logging.INFO, logger=recovery.__name__):
        await vanish_until_given_up(app, table)

    lines = rendered(caplog.records, recovery.__name__)
    assert [line['level'] for line in lines] == ['info'] * AUTO_RETRY_LIMIT + ['warning']
    gave_up = lines[-1]
    assert (gave_up['error_code'], gave_up['table_id'], gave_up['round']) == (
        recovery.STALLED_ERROR_CODE,
        table['id'],
        1,
    )
