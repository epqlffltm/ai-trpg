# game-server/tests/test_round_locking.py

"""
같은 라운드에 선언 둘이 동시에 올 때를 검증한다.

마지막 두 사람이 동시에 선언을 내면, 잠금이 없을 때 이런 일이 생긴다.
  1. A: 선언을 적는다. 아직 안 낸 사람이 하나 남았다(B 가 아직 저장하지 않았다). 닫지 않는다.
  2. B: 선언을 적는다. 아직 안 낸 사람이 하나 남았다(A 가 아직 저장하지 않았다). 닫지 않는다.
결과: 모두 냈는데 라운드가 닫히지 않는다. 테이블이 멈춘다.

두 연결(세션)을 따로 열어 이 순서를 직접 만든다. 한쪽이 테이블을 잠근 채로 멈춰 있을 때 다른 쪽이 기다리는지 본다.
"""

import asyncio
import uuid
from datetime import datetime

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.rulebooks import service as rulebooks
from app.assets.rulebooks.schemas import RulebookCreate
from app.assets.scenarios import publishing
from app.assets.scenarios import service as scenarios
from app.assets.scenarios.schemas import ScenarioCreate, VersionCreate
from app.engine.dice import ScriptedDice
from app.rounds import closing, repository, service
from app.rounds.models import Round
from app.rounds.narrator import FakeNarrator
from app.rounds.schemas import DeclarationUpdate
from app.tables import repository as table_repository
from app.tables import service as tables
from app.tables.models import GameTable
from app.tables.schemas import CharacterUpdate, JoinRequest, TableCreate
from tests.indexers import NO_INDEXER
from tests.sheets import SHEET
from tests.signing import make_viewer

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')

# 눈이 하나도 없는 주사위. 여기의 선언에는 행동이 없어 굴릴 일이 없다. 굴리면 오류가 난다
NO_DICE = ScriptedDice([])

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


async def start_duo(session: AsyncSession) -> GameTable:
    """나와 친구가 앉은 테이블을 시작한다. 첫 라운드가 열려 있다."""
    rulebook = await rulebooks.create_rulebook(session, ME, RulebookCreate(title='룰북'))
    data = ScenarioCreate(title='시나리오', rulebook_id=rulebook.asset_id, openings=['도입부'], default_sheet=SHEET)
    scenario = await scenarios.create_scenario(session, ME, data)
    await publishing.publish(session, ME, scenario.asset_id, VersionCreate(), NO_INDEXER)
    create = TableCreate(scenario_id=scenario.asset_id, version=1, capacity=2)
    table = await tables.create_table(session, make_viewer(ME), create)
    await tables.join_table(session, make_viewer(FRIEND), JoinRequest(invite_code=table.invite_code))
    await tables.set_character(session, ME, table.id, CharacterUpdate(name='엘프'))
    await tables.set_character(session, FRIEND, table.id, CharacterUpdate(name='영애'))
    return await tables.start_table(session, ME, table.id)


class RecordingScheduler:
    """맡긴 것을 적어 두기만 하는 것. 서술을 돌리지 않는다. 몇 번 맡겼는지 본다."""

    def __init__(self) -> None:
        self.scheduled: list[tuple[uuid.UUID, int]] = []
        # 맡길 때마다 함께 받은 닫기 시작한 시각
        self.started: list[datetime] = []

    def schedule(self, table_id: uuid.UUID, number: int, started: datetime) -> None:
        self.scheduled.append((table_id, number))
        self.started.append(started)


async def narrate(app: FastAPI, table: GameTable, number: int) -> Round:
    """맡겨진 서술을 직접 돌리고, 그 뒤의 가장 최근 라운드를 돌려준다."""
    async with app.state.session_factory() as fresh:
        started = (await repository.find_round(fresh, table.id, number)).closing_at
    await closing.narrate_round(app.state.session_factory, FakeNarrator(), table.id, number, started)
    async with app.state.session_factory() as fresh:
        return await repository.find_latest_round(fresh, table.id)


async def test_the_last_two_declarations_close_the_round_once(
    app: FastAPI, session: AsyncSession, other_session: AsyncSession
):
    table = await start_duo(session)
    scheduler = RecordingScheduler()

    # A: 테이블을 잠그고 내 선언을 적었지만 아직 커밋하지 않았다
    locked = await table_repository.lock_table(session, table.id)
    round_ = await repository.find_latest_round(session, table.id)
    service.put_declaration(round_, tables.find_member(locked, ME), '달린다.', None)
    await session.flush()

    # B: 친구가 선언을 낸다. A 가 끝날 때까지 기다려야 한다
    data = DeclarationUpdate(content='웃는다.')
    declaring = asyncio.create_task(service.declare(other_session, FRIEND, table.id, data, scheduler, NO_DICE))
    assert await is_waiting(declaring)

    await session.commit()

    # 기다린 뒤에는 A 의 선언이 보인다. 모두 냈으므로 B 가 라운드를 닫기 시작하고 서술을 한 번 맡긴다
    _, closing_round = await declaring
    assert (closing_round.number, closing_round.status) == (1, 'closing')
    assert scheduler.scheduled == [(table.id, 1)]
    # 저장한 닫기 시작한 시각을 함께 넘긴다. 작업이 이것으로 자기 차례인지 안다
    async with app.state.session_factory() as fresh:
        assert scheduler.started == [(await repository.find_round(fresh, table.id, 1)).closing_at]

    latest = await narrate(app, table, 1)
    assert latest.number == 2
    assert latest.scene == '[1 라운드의 결과]\n엘프: 달린다.\n영애: 웃는다.'
    # 응답이 아니라 저장된 것을 본다. 라운드는 둘이고, 닫히지 않은 것은 하나다
    total = await other_session.scalar(select(func.count()).select_from(Round).where(Round.table_id == table.id))
    opened = await other_session.scalar(
        select(func.count()).select_from(Round).where(Round.table_id == table.id, Round.closed_at.is_(None))
    )
    assert (total, opened) == (2, 1)


async def test_closing_waits_for_a_declaration_being_saved(
    app: FastAPI, session: AsyncSession, other_session: AsyncSession
):
    table = await start_duo(session)

    # A: 테이블을 잠그고 친구의 선언을 적었지만 아직 커밋하지 않았다
    locked = await table_repository.lock_table(session, table.id)
    round_ = await repository.find_latest_round(session, table.id)
    service.put_declaration(round_, tables.find_member(locked, FRIEND), '웃는다.', None)
    await session.flush()

    # B: 방장이 라운드를 닫으려 한다. 잠금이 없으면 친구의 선언을 못 보고 "아무것도 하지 않았다"로 닫는다
    closing_task = asyncio.create_task(service.force_close(other_session, ME, table.id, RecordingScheduler(), NO_DICE))
    assert await is_waiting(closing_task)

    await session.commit()
    await closing_task

    latest = await narrate(app, table, 1)
    assert latest.scene == '[1 라운드의 결과]\n엘프: 아무것도 하지 않았다.\n영애: 웃는다.'
