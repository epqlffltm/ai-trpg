# trpg-server/tests/test_round_time_limit.py

"""
라운드의 시간 제한(#57)을 검증한다.

보는 것은 다섯이다.
  - 테이블의 설정: 고르지 않으면 5 분, null 이면 없음, 30 초~1 시간. 목록과 상세에 보인다. DB 도 범위를 지킨다.
  - 마감: 라운드를 열 때 시간 제한만큼 뒤로 정한다. 라운드와 열림의 이벤트에 실린다. 시간 제한이 없으면 마감도 없다.
  - 설정 바꾸기: 방장만, 끝나기 전까지. 다음 라운드부터 쓰고 지금 라운드의 마감은 그대로다. 이벤트로 남는다.
  - 서버의 시계: 마감이 지난 라운드만 닫는다. 안 낸 사람은 아무것도 하지 않은 것으로 넘어가고, 닫힌 까닭이 남는다.
    시계가 둘이어도 한 번만 닫는다. 한 테이블이 실패해도 다른 테이블은 닫는다. 멈추라면 멈춘다.
  - 떠난 뒤: 기다리던 사람이 떠나거나 내보내져서 남은 사람이 모두 냈으면 닫는다. 아무도 안 냈으면 닫지 않는다.
시계의 시각은 테스트가 정한다(RoundClock.clock). 정말로 기다리지 않는다.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import create_app
from app.rounds import clock as round_clock
from app.rounds import service
from app.rounds.clock import RoundClock
from app.rounds.closing import closer_of
from app.rounds.models import Declaration, Round
from app.rounds.state import is_ready
from app.tables.models import (
    DEFAULT_ROUND_TIME_LIMIT,
    ROUND_TIME_LIMIT_MAX,
    ROUND_TIME_LIMIT_MIN,
    GameTable,
    TableMember,
    TableSheet,
)
from tests.logs import rendered
from tests.signing import SigningKey
from tests.test_npc_actions import bearer, declare, events_of, table_url
from tests.test_tables_api import TABLES_URL, publish_scenario

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
STRANGER = uuid.UUID('99999999-2222-4333-8444-555555555555')

LAUGH = '크게 웃는다.'
# 시계의 시각을 정할 때 마감에서 이만큼 지나게 둔다
PAST = timedelta(seconds=1)


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """두 번째로 앉는 사람."""
    return bearer(signing_key, FRIEND)


async def open_with(client: AsyncClient, me: dict[str, str], capacity: int = 2, **options) -> dict:
    """테이블을 연다. options 는 만들 때 보내는 칸이다(round_time_limit 같은 것). 보내지 않은 칸은 기본값이다."""
    scenario = await publish_scenario(client, me)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': capacity, **options}
    return await client.post(TABLES_URL, json=body, headers=me)


async def start_with(client: AsyncClient, me: dict[str, str], *others: dict[str, str], **options) -> dict:
    """테이블을 열고, others 를 앉히고, 모두 캐릭터를 정하고, 시작한다. 시작한 테이블을 돌려준다."""
    response = await open_with(client, me, capacity=1 + len(others), **options)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    table = response.json()
    for headers in others:
        joined = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=headers)
        assert joined.status_code == status.HTTP_200_OK, joined.text
    for index, headers in enumerate([me, *others]):
        named = await client.put(table_url(table, '/character'), json={'name': f'캐릭터{index}'}, headers=headers)
        assert named.status_code == status.HTTP_200_OK, named.text
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


async def current(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    """지금 라운드."""
    response = await client.get(table_url(table, '/rounds/current'), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def read_time(value: str) -> datetime:
    """응답의 시각."""
    return datetime.fromisoformat(value)


def clock_at(app: FastAPI, moment: datetime) -> RoundClock:
    """그 시각에 멈춘 시계. 앱의 서술자와 주사위를 쓴다."""
    return RoundClock(
        session_factory=app.state.session_factory,
        scheduler=lambda: closer_of(app.state),
        dice=lambda: app.state.dice,
        clock=lambda: moment,
    )


def after(round_: dict) -> datetime:
    """라운드의 마감을 조금 지난 시각."""
    return read_time(round_['deadline_at']) + PAST


async def set_limit(client: AsyncClient, headers: dict[str, str], table: dict, limit: int | None):
    """시간 제한을 바꾼다. 응답을 그대로 돌려준다."""
    return await client.put(table_url(table, '/round-time-limit'), json={'round_time_limit': limit}, headers=headers)


# --- 테이블의 설정 ---


async def test_the_default_limit_is_five_minutes(client: AsyncClient, me: dict[str, str]):
    response = await open_with(client, me)

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()['round_time_limit'] == DEFAULT_ROUND_TIME_LIMIT == 300


async def test_null_means_no_limit(client: AsyncClient, me: dict[str, str]):
    response = await open_with(client, me, round_time_limit=None)

    assert response.json()['round_time_limit'] is None


@pytest.mark.parametrize('limit', [ROUND_TIME_LIMIT_MIN, ROUND_TIME_LIMIT_MAX])
async def test_the_edges_of_the_range_are_accepted(client: AsyncClient, me: dict[str, str], limit: int):
    response = await open_with(client, me, round_time_limit=limit)

    assert response.json()['round_time_limit'] == limit


@pytest.mark.parametrize('limit', [ROUND_TIME_LIMIT_MIN - 1, ROUND_TIME_LIMIT_MAX + 1, 0, -30, '오 분'])
async def test_a_limit_out_of_range_is_rejected(client: AsyncClient, me: dict[str, str], limit):
    response = await open_with(client, me, round_time_limit=limit)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_list_shows_the_limit(client: AsyncClient, me: dict[str, str]):
    await open_with(client, me, round_time_limit=60)

    listed = (await client.get(TABLES_URL, headers=me)).json()

    assert [table['round_time_limit'] for table in listed['items']] == [60]


async def test_the_database_keeps_the_range(client: AsyncClient, me: dict[str, str], session: AsyncSession):
    table = (await open_with(client, me)).json()

    with pytest.raises(IntegrityError):
        await session.execute(
            text('UPDATE game_tables SET round_time_limit = 10 WHERE id = :id'), {'id': uuid.UUID(table['id'])}
        )
    await session.rollback()


# --- 마감 ---


async def test_the_first_round_gets_a_deadline(client: AsyncClient, me: dict[str, str]):
    before = datetime.now(UTC)
    table = await start_with(client, me, round_time_limit=60)

    round_ = await current(client, me, table)
    (opened,) = await events_of(client, me, table, 'round_opened')

    deadline = read_time(round_['deadline_at'])
    assert before + timedelta(seconds=60) <= deadline <= datetime.now(UTC) + timedelta(seconds=60)
    assert read_time(opened['payload']['deadline_at']) == deadline


async def test_no_limit_means_no_deadline(client: AsyncClient, me: dict[str, str]):
    table = await start_with(client, me, round_time_limit=None)

    round_ = await current(client, me, table)
    (opened,) = await events_of(client, me, table, 'round_opened')

    assert round_['deadline_at'] is None
    assert opened['payload']['deadline_at'] is None


async def test_the_next_round_counts_from_its_own_opening(client: AsyncClient, me: dict[str, str], narrated):
    table = await start_with(client, me, round_time_limit=60)
    first = await current(client, me, table)

    await declare(client, me, table, LAUGH)
    await narrated()
    second = await current(client, me, table)

    assert second['number'] == 2
    # 서술을 기다린 시간은 세지 않는다. 열린 때부터 다시 센다
    assert read_time(second['deadline_at']) - read_time(second['created_at']) < timedelta(seconds=61)
    assert read_time(second['deadline_at']) >= read_time(first['deadline_at'])


# --- 설정 바꾸기 ---


async def test_the_host_changes_the_limit_and_it_is_recorded(client: AsyncClient, me: dict[str, str]):
    table = await start_with(client, me)

    response = await set_limit(client, me, table, 120)
    (changed,) = await events_of(client, me, table, 'round_time_limit_changed')

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['round_time_limit'] == 120
    assert (changed['actor_id'], changed['payload']) == (str(ME), {'round_time_limit': 120})


async def test_the_change_waits_for_the_next_round(client: AsyncClient, me: dict[str, str], narrated):
    table = await start_with(client, me, round_time_limit=60)
    first = await current(client, me, table)

    await set_limit(client, me, table, None)
    unchanged = await current(client, me, table)
    await declare(client, me, table, LAUGH)
    await narrated()
    second = await current(client, me, table)

    # 지금 라운드의 마감은 그대로, 다음 라운드부터 시간 제한이 없다
    assert unchanged['deadline_at'] == first['deadline_at']
    assert second['deadline_at'] is None


async def test_the_same_limit_writes_nothing(client: AsyncClient, me: dict[str, str]):
    table = await start_with(client, me)

    response = await set_limit(client, me, table, DEFAULT_ROUND_TIME_LIMIT)

    assert response.status_code == status.HTTP_200_OK
    assert await events_of(client, me, table, 'round_time_limit_changed') == []


async def test_only_the_host_changes_the_limit(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await start_with(client, me, friend)

    response = await set_limit(client, friend, table, 60)

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_an_ended_table_keeps_its_limit(client: AsyncClient, me: dict[str, str]):
    table = await start_with(client, me)
    await client.post(table_url(table, '/end'), headers=me)

    response = await set_limit(client, me, table, 60)

    assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.parametrize('body', [{}, {'round_time_limit': 5}, {'round_time_limit': 60, 'paused': True}])
async def test_a_bad_change_is_rejected(client: AsyncClient, me: dict[str, str], body: dict):
    table = await start_with(client, me)

    response = await client.put(table_url(table, '/round-time-limit'), json=body, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 서버의 시계 ---


async def test_an_overdue_round_is_closed_by_the_clock(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_with(client, me, friend, round_time_limit=60)
    await declare(client, me, table, LAUGH)
    round_ = await current(client, me, table)

    closed = await clock_at(app, after(round_)).tick()
    await narrated()

    (event,) = await events_of(client, me, table, 'round_closed')
    assert closed == 1
    # 저절로 닫혔다. 닫은 사람이 없고, 안 낸 사람이 적히고, 까닭은 마감이다
    assert (event['actor_id'], event['payload']) == (None, {'number': 1, 'idle': [str(FRIEND)], 'reason': 'timeout'})
    assert (await current(client, me, table))['number'] == 2


async def test_a_round_before_its_deadline_stays_open(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table = await start_with(client, me, round_time_limit=60)
    round_ = await current(client, me, table)

    closed = await clock_at(app, read_time(round_['deadline_at']) - PAST).tick()

    assert closed == 0
    assert (await current(client, me, table))['status'] == 'open'


async def test_a_table_without_a_limit_is_never_closed_by_the_clock(
    client: AsyncClient, app: FastAPI, me: dict[str, str]
):
    table = await start_with(client, me, round_time_limit=None)

    closed = await clock_at(app, datetime.now(UTC) + timedelta(days=365)).tick()

    assert closed == 0
    assert (await current(client, me, table))['status'] == 'open'


async def test_a_closing_round_is_left_alone(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table = await start_with(client, me, round_time_limit=60)
    round_ = await current(client, me, table)
    await declare(client, me, table, LAUGH)

    # 마감 바로 그 시각. 서술이 먼저 끝나 다음 라운드가 열렸어도, 그 마감은 이보다 뒤다
    closed = await clock_at(app, read_time(round_['deadline_at'])).tick()

    # 모두 내서 이미 닫는 중이다. 시계는 찾지도 않는다
    assert closed == 0
    assert len(await events_of(client, me, table, 'round_closed')) == 1


async def test_two_clocks_close_a_round_once(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_with(client, me, friend, round_time_limit=60)
    round_ = await current(client, me, table)
    moment = after(round_)

    # 서버가 둘이라 둘 다 같은 라운드를 찾았다. 테이블의 잠금이 하나만 닫게 한다
    results = await asyncio.gather(clock_at(app, moment).tick(), clock_at(app, moment).tick())
    await narrated()

    assert sorted(results) == [0, 1]
    assert len(await events_of(client, me, table, 'round_closed')) == 1


async def test_one_failing_table_does_not_stop_the_others(
    client: AsyncClient,
    app: FastAPI,
    me: dict[str, str],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    narrated,
):
    broken = await start_with(client, me, round_time_limit=60)
    working = await start_with(client, me, round_time_limit=60)
    moment = max(after(await current(client, me, broken)), after(await current(client, me, working)))
    real = service.close_on_time

    async def fail_for_broken(session, table_id, *args):
        if str(table_id) == broken['id']:
            raise RuntimeError('이 테이블에서 실패했다')
        return await real(session, table_id, *args)

    monkeypatch.setattr(service, 'close_on_time', fail_for_broken)

    with caplog.at_level(logging.ERROR, logger='app.rounds.clock'):
        closed = await clock_at(app, moment).tick()
    await narrated()

    assert closed == 1
    assert (await current(client, me, working))['number'] == 2
    assert (await current(client, me, broken))['status'] == 'open'
    # 실패는 공통 규격의 error 줄이다. 어느 테이블인지 칸으로 남고, 바퀴의 job_id 로 묶인다
    (failure,) = [line for line in rendered(caplog.records, 'app.rounds.clock') if line['level'] == 'error']
    assert failure['table_id'] == broken['id']
    assert (failure['operation'], failure['error_code'], failure['result']) == (
        'round.close_overdue',
        'job.failed',
        'server_error',
    )
    assert 'job_id' in failure
    assert 'request_id' not in failure


async def test_each_tick_is_a_job_with_one_line(
    client: AsyncClient, app: FastAPI, me: dict[str, str], caplog: pytest.LogCaptureFixture, narrated
):
    table = await start_with(client, me, round_time_limit=60)
    round_ = await current(client, me, table)

    with caplog.at_level(logging.DEBUG, logger='app.rounds.clock'):
        await clock_at(app, read_time(round_['deadline_at']) - PAST).tick()
        await clock_at(app, after(round_)).tick()
    await narrated()

    idle, busy = rendered(caplog.records, 'app.rounds.clock')
    # 할 일이 없던 바퀴는 debug, 닫은 바퀴는 info. 바퀴마다 다른 작업이다
    assert (idle['level'], idle['closed'], busy['level'], busy['closed']) == ('debug', 0, 'info', 1)
    assert {idle['operation'], busy['operation']} == {'round.close_overdue'}
    assert idle['job_id'] != busy['job_id']
    assert busy['result'] == 'success'
    assert isinstance(busy['duration_ms'], int)


async def test_the_clock_runs_until_told_to_stop(app: FastAPI, monkeypatch: pytest.MonkeyPatch):
    ticks = []

    async def count(self) -> int:
        ticks.append(1)
        return 0

    monkeypatch.setattr(RoundClock, 'tick', count)
    running = round_clock.start(replace_interval(clock_at(app, datetime.now(UTC)), 0.01))
    await asyncio.sleep(0.05)
    await asyncio.wait_for(running.halt(), timeout=1)

    assert len(ticks) >= 2
    assert running.task.done()


async def test_a_failing_tick_does_not_stop_the_clock(app: FastAPI, monkeypatch: pytest.MonkeyPatch):
    ticks = []

    async def fail(self) -> int:
        ticks.append(1)
        raise RuntimeError('DB 가 없다')

    monkeypatch.setattr(RoundClock, 'tick', fail)
    running = round_clock.start(replace_interval(clock_at(app, datetime.now(UTC)), 0.01))
    await asyncio.sleep(0.05)
    await asyncio.wait_for(running.halt(), timeout=1)

    assert len(ticks) >= 2


def replace_interval(clock: RoundClock, interval: float) -> RoundClock:
    """간격만 바꾼 시계."""
    return RoundClock(clock.session_factory, clock.scheduler, clock.dice, interval, clock.clock)


async def test_the_overdue_query_skips_rounds_that_are_not_open(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    table = await start_with(client, me, round_time_limit=60)
    round_ = await current(client, me, table)
    await declare(client, me, table, LAUGH)

    moment = read_time(round_['deadline_at'])
    stored = await session.scalar(select(Round).where(Round.table_id == uuid.UUID(table['id']), Round.number == 1))
    found = await clock_at(app, moment).overdue(moment)

    assert stored.closing_at is not None
    assert found == []


# --- 떠난 뒤 ---


async def test_leaving_closes_a_round_that_only_waited_for_the_leaver(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_with(client, me, friend, round_time_limit=None)
    await declare(client, me, table, LAUGH)

    left = await client.delete(table_url(table, '/members/me'), headers=friend)
    await narrated()

    (event,) = await events_of(client, me, table, 'round_closed')
    assert left.status_code == status.HTTP_204_NO_CONTENT
    assert (event['actor_id'], event['payload']['reason']) == (None, 'all_declared')
    assert (await current(client, me, table))['number'] == 2


async def test_kicking_closes_a_round_that_only_waited_for_the_kicked(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_with(client, me, friend, round_time_limit=None)
    await declare(client, me, table, LAUGH)

    kicked = await client.delete(table_url(table, f'/members/{FRIEND}'), headers=me)
    await narrated()

    assert kicked.status_code == status.HTTP_200_OK
    assert (await current(client, me, table))['number'] == 2


async def test_leaving_when_nobody_declared_keeps_the_round_open(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    table = await start_with(client, me, friend, round_time_limit=None)

    await client.delete(table_url(table, '/members/me'), headers=friend)

    # 남은 사람이 아직 내지 않았다. 기다린다
    assert (await current(client, me, table))['status'] == 'open'
    assert await events_of(client, me, table, 'round_closed') == []


async def test_leaving_while_others_still_wait_keeps_the_round_open(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], signing_key: SigningKey
):
    third = bearer(signing_key, STRANGER)
    table = await start_with(client, me, friend, third, round_time_limit=None)
    await declare(client, me, table, LAUGH)

    await client.delete(table_url(table, '/members/me'), headers=third)

    # 친구가 아직 내지 않았다
    assert (await current(client, me, table))['waiting_for'] == [str(FRIEND)]


async def test_the_overdue_query_finds_only_rounds_past_their_deadline(
    client: AsyncClient, app: FastAPI, me: dict[str, str]
):
    table = await start_with(client, me, round_time_limit=60)
    deadline = read_time((await current(client, me, table))['deadline_at'])
    clock = clock_at(app, deadline)

    assert await clock.overdue(deadline - PAST) == []
    assert await clock.overdue(deadline) == [uuid.UUID(table['id'])]


async def test_closing_on_time_checks_the_deadline_again_under_the_lock(
    client: AsyncClient, app: FastAPI, me: dict[str, str]
):
    table = await start_with(client, me, round_time_limit=60)
    deadline = read_time((await current(client, me, table))['deadline_at'])

    # 고른 뒤 잠그기 전에 라운드가 바뀔 수 있다(닫히고 새 라운드가 열림). 잠근 뒤에 마감을 다시 본다
    async with app.state.session_factory() as session:
        closed = await service.close_on_time(
            session, uuid.UUID(table['id']), deadline - PAST, closer_of(app.state), app.state.dice
        )

    assert closed is False
    assert (await current(client, me, table))['status'] == 'open'


# --- 닫을 준비가 됐는가. DB 를 쓰지 않는다 ---


def member_with(hp: int) -> TableMember:
    """시트가 있는 자리 하나. hp 가 0 이면 쓰러져 있다."""
    sheet = TableSheet(abilities={}, max_hp=10, hp=hp, number=1)
    return TableMember(user_id=uuid.uuid4(), character_name='엘프', sheets=[sheet])


def round_with(*declared: TableMember) -> Round:
    """선언을 낸 사람들이 있는 열린 라운드."""
    round_ = Round(number=1, scene='장면', arrivals=[])
    round_.declarations = [
        Declaration(user_id=member.user_id, character_name='엘프', content=LAUGH) for member in declared
    ]
    return round_


def test_a_round_is_ready_when_nobody_is_waited_for_and_someone_declared():
    standing, downed = member_with(5), member_with(0)
    table = GameTable(members=[standing, downed])

    assert is_ready(table, round_with(standing))
    assert not is_ready(GameTable(members=[standing]), round_with())


def test_a_table_of_downed_characters_is_not_ready():
    # 기다릴 사람이 없지만 아무도 내지 않았다. 저절로 넘어가지 않는다. 방장이나 마감이 닫는다
    table = GameTable(members=[member_with(0), member_with(0)])

    assert not is_ready(table, round_with())


# --- 서버가 뜨고 꺼질 때 ---


async def test_the_server_runs_the_clock_while_it_is_up(settings, auth_server, monkeypatch: pytest.MonkeyPatch):
    ticks = []

    async def count(self) -> int:
        ticks.append(1)
        return 0

    monkeypatch.setattr(RoundClock, 'tick', count)
    server = create_app(settings, http_client=auth_server.make_client())

    async with server.router.lifespan_context(server):
        await asyncio.sleep(0.05)
        started = len(ticks)
    # 꺼질 때 멈춘다. 더 돌지 않는다
    await asyncio.sleep(0.05)

    assert started >= 1
    assert len(ticks) == started
    # 닫을 때마다 앱에 꽂힌 서술자와 주사위를 꺼낸다
    assert server.state.round_clock.dice() is server.state.dice
    assert server.state.round_clock.scheduler().narrator is server.state.narrator
