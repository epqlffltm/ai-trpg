# game-server/tests/test_replacement_locking.py

"""
같은 사람의 "새 캐릭터 들이기" 요청 둘이 동시에 올 때를 검증한다.

새 캐릭터를 들이는 것은 "캐릭터가 죽었는지 보고 나서 들인다". 잠금이 없으면 이런 일이 생긴다.
  1. A: 캐릭터가 죽었는지 본다. 죽었다.
  2. B: 캐릭터가 죽었는지 본다. 죽었다(A 가 아직 저장하지 않았다).
  3. A: 새 캐릭터에게 시트를 준다.   4. B: 새 캐릭터에게 시트를 준다.
결과: 한 사람에게 살아 있는 캐릭터가 둘 생긴다.

두 연결(세션)을 따로 열어 이 순서를 직접 만든다(tests/test_table_locking.py 와 같은 방법).
잠금이 빠져도 DB 가 마지막에 막는다(유일 색인 uq_table_sheets_living). 그것은 tests/test_table_sheets.py 가 본다.
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
from app.engine.sheet import Sheet
from app.tables import replacements, repository, service, sheets
from app.tables.models import GameTable
from app.tables.schemas import CharacterUpdate, TableCreate
from app.tables.service import Conflict, TableConflictError
from tests.indexers import NO_INDEXER
from tests.sheets import SHEET
from tests.signing import make_viewer

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')

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


async def start_with_a_dead_character(session: AsyncSession) -> GameTable:
    """혼자 앉아 시작한 테이블. 내 캐릭터 '엘프'는 죽어 있다. 첫 라운드가 열려 있다."""
    rulebook = await rulebooks.create_rulebook(session, ME, RulebookCreate(title='룰북'))
    data = ScenarioCreate(title='시나리오', rulebook_id=rulebook.asset_id, openings=['도입부'], default_sheet=SHEET)
    scenario = await scenarios.create_scenario(session, ME, data)
    await publishing.publish(session, ME, scenario.asset_id, VersionCreate(), NO_INDEXER)
    created = TableCreate(scenario_id=scenario.asset_id, version=1, capacity=1)
    table = await service.create_table(session, make_viewer(ME), created)
    await service.set_character(session, ME, table.id, CharacterUpdate(name='엘프'))
    await service.start_table(session, ME, table.id)
    # 죽이는 길(쓰러뜨리고 보내기)은 다른 테스트가 본다. 여기서는 죽어 있는 상태만 필요하다
    await session.execute(text('UPDATE table_sheets SET hp = 0, died_at = now()'))
    await session.commit()
    return table


async def test_bringing_in_a_character_waits_for_another(session: AsyncSession, other_session: AsyncSession):
    table = await start_with_a_dead_character(session)

    # A: 테이블을 잠그고 새 캐릭터에게 시트를 줬지만 아직 커밋하지 않았다
    locked = await repository.lock_table(session, table.id)
    seat = locked.members[0]
    seat.character_name = '드워프'
    sheets.give_sheet(seat, Sheet.model_validate(SHEET))
    await session.flush()

    # B: 같은 사람이 또 들이려 한다. A 가 끝날 때까지 기다려야 한다
    arriving = asyncio.create_task(
        replacements.bring_in_character(other_session, ME, table.id, CharacterUpdate(name='오크'))
    )
    assert await is_waiting(arriving)

    await session.commit()

    # 기다린 뒤에는 A 가 들인 캐릭터가 보인다. 살아 있는 캐릭터가 있으니 또 들이지 않는다
    with pytest.raises(TableConflictError) as refused:
        await arriving
    assert refused.value.reason == Conflict.CHARACTER_ALIVE
    await other_session.rollback()
    names = await other_session.scalars(text('SELECT character_name FROM table_sheets ORDER BY number'))
    assert names.all() == ['엘프', '드워프']
