# game-server/tests/test_roll_locking.py

"""
같은 사람의 "굴리기" 요청 둘이 동시에 올 때를 검증한다.

굴리기는 "이미 굴렸는지 보고 나서 굴린다". 잠금이 없으면 이런 일이 생긴다.
  1. A: 굴린 것이 있는지 본다. 없다.
  2. B: 굴린 것이 있는지 본다. 없다(A 가 아직 저장하지 않았다).
  3. A: 굴려서 적는다.   4. B: 굴려서 적는다.
결과: 한 번만 굴려야 하는 주사위를 두 번 굴린다. 버튼을 빠르게 두 번 눌러 더 좋은 쪽을 노릴 수 있다.

두 연결(세션)을 따로 열어 이 순서를 직접 만든다(tests/test_table_locking.py 와 같은 방법).
"""

import asyncio
import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.rulebooks import service as rulebooks
from app.assets.rulebooks.schemas import RulebookCreate
from app.assets.scenarios import publishing
from app.assets.scenarios import service as scenarios
from app.assets.scenarios.schemas import ScenarioCreate, VersionCreate
from app.engine.dice import ScriptedDice
from app.tables import repository, rolls, service
from app.tables.models import GameTable, TableRoll
from app.tables.schemas import TableCreate
from app.tables.service import Conflict, TableConflictError
from tests.sheets import SHEET
from tests.signing import make_viewer

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')

# 기다리는지 확인할 때 주는 시간(초). 잠금에 걸리지 않았다면 이 안에 끝난다
WAIT = 0.3

# 먼저 굴린 쪽이 적은 점수
FIRST = [15, 14, 13, 12, 10, 8]


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
    """내가 방장인 테이블을 연다. 주사위로 정하기를 허용하는 시나리오로 만든다."""
    rulebook = await rulebooks.create_rulebook(session, ME, RulebookCreate(title='룰북'))
    data = ScenarioCreate(
        title='시나리오',
        rulebook_id=rulebook.asset_id,
        openings=['도입부'],
        default_sheet=SHEET,
        character_modes=['custom', 'rolled'],
        player_made_hp={'base': 10, 'cap': 12},
    )
    scenario = await scenarios.create_scenario(session, ME, data)
    await publishing.publish(session, ME, scenario.asset_id, VersionCreate())
    table = TableCreate(scenario_id=scenario.asset_id, version=1, capacity=1)
    return await service.create_table(session, make_viewer(ME), table)


async def test_rolling_waits_for_another_roll(session: AsyncSession, other_session: AsyncSession):
    table = await open_table(session)
    # B 가 굴리게 되면 모두 6 이 나온다. 굴렸는지를 남은 눈으로 본다
    dice = ScriptedDice([6] * 24)

    # A: 테이블을 잠그고 굴린 것을 적었지만 아직 커밋하지 않았다
    locked = await repository.lock_table(session, table.id)
    locked.rolls.append(TableRoll(user_id=ME, dice=[[1, 5, 5, 5]] * 6, scores=FIRST, times_rolled=1))
    await session.flush()

    # B: 같은 사람이 또 굴리려 한다. A 가 끝날 때까지 기다려야 한다
    rolling = asyncio.create_task(rolls.roll_abilities(other_session, ME, table.id, dice))
    assert await is_waiting(rolling)

    await session.commit()

    # 기다린 뒤에는 A 가 굴린 것이 보인다. 한 번 더 굴리지 않는다
    with pytest.raises(TableConflictError) as refused:
        await rolling
    assert refused.value.reason == Conflict.ALREADY_ROLLED
    assert dice.remaining == 24
    # 저장된 것을 다시 읽어 확인한다. 먼저 굴린 점수가 그대로다
    await other_session.rollback()
    assert await other_session.scalar(text('SELECT scores FROM table_rolls')) == FIRST
