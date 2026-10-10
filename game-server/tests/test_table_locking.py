# game-server/tests/test_table_locking.py

"""
같은 테이블을 바꾸는 요청 둘이 동시에 올 때를 검증한다.

테이블을 바꾸는 일은 모두 "확인하고 나서 쓴다". 자리가 남았는지 보고 앉고, 프리젠이 비었는지 보고 가져간다.
잠금이 없으면 이런 일이 생긴다.
  1. A: 앉은 사람을 센다. 한 자리가 남았다.
  2. B: 앉은 사람을 센다. 한 자리가 남았다(A 가 아직 저장하지 않았다).
  3. A: 앉는다.   4. B: 앉는다.
결과: 정원보다 많은 사람이 앉는다.

두 연결(세션)을 따로 열어 이 순서를 직접 만든다. 한쪽이 테이블을 잠근 채로 멈춰 있을 때 다른 쪽이 기다리는지 본다.
API 로 두 요청을 동시에 보내는 방법은 쓰지 않는다. 요청이 어디서 엇갈릴지 정할 수 없어서, 잠금이 없어도 통과할 수 있다.
"""

import asyncio
import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.rulebooks import service as rulebooks
from app.assets.rulebooks.schemas import RulebookCreate
from app.assets.scenarios import publishing
from app.assets.scenarios import service as scenarios
from app.assets.scenarios.schemas import ScenarioCreate, VersionCreate
from app.tables import repository, service
from app.tables.models import GameTable, TableMember
from app.tables.schemas import CharacterUpdate, JoinRequest, LobbyJoinRequest, TableCreate
from app.tables.service import Conflict, TableConflictError
from tests.indexers import NO_INDEXER
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


async def open_table(session: AsyncSession, capacity: int, is_public: bool = False) -> GameTable:
    """내가 방장인 테이블을 연다. 프리젠이 하나 있는 시나리오로 만든다."""
    rulebook = await rulebooks.create_rulebook(session, ME, RulebookCreate(title='룰북'))
    data = ScenarioCreate(
        title='시나리오',
        rulebook_id=rulebook.asset_id,
        openings=['도입부'],
        pregens=[{'name': '폭주족 엘프', 'sheet': SHEET}],
        default_sheet=SHEET,
    )
    scenario = await scenarios.create_scenario(session, ME, data)
    await publishing.publish(session, ME, scenario.asset_id, VersionCreate(), NO_INDEXER)
    table = TableCreate(scenario_id=scenario.asset_id, version=1, capacity=capacity, is_public=is_public)
    return await service.create_table(session, make_viewer(ME), table)


async def count_members(session: AsyncSession, table_id: uuid.UUID) -> int:
    """테이블에 앉은 사람을 DB 에서 직접 센다."""
    query = select(func.count()).select_from(TableMember).where(TableMember.table_id == table_id)
    return await session.scalar(query)


async def test_joining_waits_for_another_join(session: AsyncSession, other_session: AsyncSession):
    table = await open_table(session, capacity=2)

    # A: 테이블을 잠그고 한 자리 남은 곳에 앉았지만 아직 커밋하지 않았다
    locked = await repository.lock_table(session, table.id)
    locked.members.append(TableMember(user_id=FRIEND))
    await session.flush()

    # B: 같은 테이블에 들어오려 한다. A 가 끝날 때까지 기다려야 한다
    data = JoinRequest(invite_code=table.invite_code)
    joining = asyncio.create_task(service.join_table(other_session, make_viewer(THIRD), data))
    assert await is_waiting(joining)

    await session.commit()

    # 기다린 뒤에는 A 가 앉은 것이 보인다. 자리가 없다
    with pytest.raises(TableConflictError) as refused:
        await joining
    assert refused.value.reason == Conflict.TABLE_FULL
    await other_session.rollback()
    # 응답이 아니라 저장된 것을 본다. 정원을 넘겨 앉은 사람이 없어야 한다
    assert await count_members(other_session, table.id) == 2


async def test_joining_from_the_lobby_waits_for_another_join(session: AsyncSession, other_session: AsyncSession):
    table = await open_table(session, capacity=2, is_public=True)

    # A: 테이블을 잠그고 한 자리 남은 곳에 앉았지만 아직 커밋하지 않았다
    locked = await repository.lock_table(session, table.id)
    locked.members.append(TableMember(user_id=FRIEND))
    await session.flush()

    # B: 로비에서 같은 테이블에 들어오려 한다. 초대 코드로 들어올 때와 같은 잠금을 기다려야 한다
    viewer = make_viewer(THIRD)
    joining = asyncio.create_task(service.join_public_table(other_session, viewer, table.id, LobbyJoinRequest()))
    assert await is_waiting(joining)

    await session.commit()

    with pytest.raises(TableConflictError) as refused:
        await joining
    assert refused.value.reason == Conflict.TABLE_FULL
    await other_session.rollback()
    assert await count_members(other_session, table.id) == 2


async def test_taking_a_pregen_waits_for_another_take(session: AsyncSession, other_session: AsyncSession):
    table = await open_table(session, capacity=2)
    await service.join_table(session, make_viewer(FRIEND), JoinRequest(invite_code=table.invite_code))

    # A: 테이블을 잠그고 프리젠을 가져갔지만 아직 커밋하지 않았다
    locked = await repository.lock_table(session, table.id)
    mine = service.find_member(locked, ME)
    mine.character_name = '폭주족 엘프'
    mine.character_mode = 'pregen'
    mine.pregen_index = 0
    await session.flush()

    # B: 같은 프리젠을 가져가려 한다. A 가 끝날 때까지 기다려야 한다
    taking = asyncio.create_task(
        service.set_character(other_session, FRIEND, table.id, CharacterUpdate(pregen_index=0))
    )
    assert await is_waiting(taking)

    await session.commit()

    # 기다린 뒤에는 A 가 가져간 것이 보인다. 같은 인물이 둘이 되지 않는다
    with pytest.raises(TableConflictError) as refused:
        await taking
    assert refused.value.reason == Conflict.PREGEN_TAKEN


async def test_starting_waits_for_a_join(session: AsyncSession, other_session: AsyncSession):
    table = await open_table(session, capacity=2)
    await service.set_character(session, ME, table.id, CharacterUpdate(name='엘프'))

    # A: 테이블을 잠그고 새 사람이 앉았지만 아직 커밋하지 않았다. 이 사람은 캐릭터가 없다
    locked = await repository.lock_table(session, table.id)
    locked.members.append(TableMember(user_id=FRIEND))
    await session.flush()

    # B: 방장이 시작하려 한다. 잠금이 없으면 "모두 캐릭터가 있다"고 보고 시작해 버린다
    starting = asyncio.create_task(service.start_table(other_session, ME, table.id))
    assert await is_waiting(starting)

    await session.commit()

    # 기다린 뒤에는 새로 앉은 사람이 보인다. 캐릭터가 없는 사람이 있어 시작할 수 없다
    with pytest.raises(TableConflictError) as refused:
        await starting
    assert refused.value.reason == Conflict.CHARACTERS_MISSING
