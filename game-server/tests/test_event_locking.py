# game-server/tests/test_event_locking.py

"""
같은 테이블에 이벤트 둘이 동시에 적힐 때를 검증한다.

이벤트의 번호는 테이블이 센다(game_tables.last_sequence). 잠금이 없으면 이런 일이 생긴다.
  1. A: 마지막 번호가 1 이다. 2 번으로 적는다.
  2. B: 마지막 번호가 1 이다(A 가 아직 저장하지 않았다). 2 번으로 적는다.
결과: 같은 번호가 둘이다. DB 의 유일 조건이 한쪽을 거부하고, 그 요청은 실패한다.

테이블을 잠그고 번호를 받으면 B 는 A 가 끝난 뒤의 번호(2)를 보고 3 번을 받는다.
두 연결(세션)을 따로 열어 이 순서를 직접 만든다.
"""

import asyncio
import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.rulebooks import service as rulebooks
from app.assets.rulebooks.schemas import RulebookCreate
from app.assets.scenarios import publishing
from app.assets.scenarios import service as scenarios
from app.assets.scenarios.schemas import ScenarioCreate, VersionCreate
from app.events import recorder
from app.events.models import EventType, TableEvent
from app.tables import repository as table_repository
from app.tables import service as tables
from app.tables.models import GameTable
from app.tables.schemas import JoinRequest, TableCreate
from tests.sheets import SHEET
from tests.signing import make_viewer

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
THIRD = uuid.UUID('33333333-2222-4333-8444-555555555555')

# 기다리는지 확인할 때 주는 시간(초). 잠금에 걸리지 않았다면 이 안에 끝난다
WAIT = 0.3


@pytest.fixture
async def other_session(app: FastAPI):
    """두 번째 연결. session 과 따로 트랜잭션을 연다."""
    async with app.state.session_factory() as db_session:
        yield db_session


async def is_waiting(task: asyncio.Task) -> bool:
    """작업이 끝나지 않고 기다리고 있는지 본다."""
    done, _ = await asyncio.wait({task}, timeout=WAIT)
    return not done


async def open_table(session: AsyncSession) -> GameTable:
    """내가 앉은 테이블을 연다. 이벤트가 하나(만들어짐) 적혀 있다."""
    rulebook = await rulebooks.create_rulebook(session, ME, RulebookCreate(title='룰북'))
    data = ScenarioCreate(title='시나리오', rulebook_id=rulebook.asset_id, openings=['도입부'], default_sheet=SHEET)
    scenario = await scenarios.create_scenario(session, ME, data)
    await publishing.publish(session, ME, scenario.asset_id, VersionCreate())
    create = TableCreate(scenario_id=scenario.asset_id, version=1, capacity=3)
    return await tables.create_table(session, make_viewer(ME), create)


async def test_two_events_at_once_get_different_sequences(session: AsyncSession, other_session: AsyncSession):
    table = await open_table(session)
    invite_code = table.invite_code

    # A: 테이블을 잠그고 친구를 앉히고 이벤트를 적었지만 아직 커밋하지 않았다
    locked = await table_repository.lock_table(session, table.id)
    tables.take_seat(locked, FRIEND)
    recorder.record(session, locked, EventType.MEMBER_JOINED, actor_id=FRIEND, payload={'via': 'invite'})
    await session.flush()

    # B: 세 번째 사람이 들어온다. A 가 끝날 때까지 기다려야 한다
    joining = asyncio.create_task(
        tables.join_table(other_session, make_viewer(THIRD), JoinRequest(invite_code=invite_code))
    )
    assert await is_waiting(joining)

    await session.commit()

    # 기다린 뒤에는 A 가 올린 번호가 보인다. B 는 그다음 번호를 받는다
    joined = await joining
    assert joined.last_sequence == 3
    # 응답이 아니라 저장된 것을 본다
    query = select(TableEvent.sequence, TableEvent.actor_id).where(TableEvent.table_id == table.id)
    stored = (await other_session.execute(query.order_by(TableEvent.sequence))).all()
    assert [tuple(row) for row in stored] == [(1, ME), (2, FRIEND), (3, THIRD)]
