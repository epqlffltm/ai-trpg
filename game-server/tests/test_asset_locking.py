# game-server/tests/test_asset_locking.py

"""
자산을 가리키는 일과 지우는 일이 동시에 일어날 때를 검증한다.

잠금이 없으면 이런 일이 생긴다.
  1. A: 룰북이 있는지 확인한다. 있다.
  2. B: 그 룰북을 쓰는 시나리오가 있는지 확인한다. 없다(A 가 아직 저장하지 않았다).
  3. A: 시나리오를 저장한다.   4. B: 룰북을 지운다.
결과: 지운 룰북을 가리키는 시나리오가 남는다.

두 연결(세션)을 따로 열어 이 순서를 직접 만든다. 한쪽이 잠근 채로 멈춰 있을 때 다른 쪽이 기다리는지 본다.
"""

import asyncio
import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import repository
from app.assets import service as assets
from app.assets.models import Rulebook
from app.assets.rulebooks import service as rulebooks
from app.assets.rulebooks.schemas import RulebookCreate
from app.assets.scenarios import service as scenarios
from app.assets.scenarios.schemas import ScenarioCreate
from app.assets.service import AssetInUseError, AssetReferenceError

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


async def test_deleting_waits_for_a_scenario_being_saved(session: AsyncSession, other_session: AsyncSession):
    rulebook_id = (await rulebooks.create_rulebook(session, ME, RulebookCreate(title='룰'))).asset_id

    # A: 룰북을 붙잡고 시나리오를 올렸지만 아직 커밋하지 않았다
    await assets.hold_reference(session, Rulebook, ME, rulebook_id, 'rulebook_id')
    session.add(scenarios.build_scenario(ME, ScenarioCreate(title='시나리오', rulebook_id=rulebook_id)))
    await session.flush()

    # B: 그 룰북을 지우려 한다. A 가 끝날 때까지 기다려야 한다
    deleting = asyncio.create_task(rulebooks.delete_rulebook(other_session, ME, rulebook_id))
    assert await is_waiting(deleting)

    await session.commit()

    # 기다린 뒤에는 A 의 시나리오가 보인다. 지울 수 없다
    with pytest.raises(AssetInUseError):
        await deleting


async def test_saving_a_scenario_waits_for_a_delete(session: AsyncSession, other_session: AsyncSession):
    rulebook_id = (await rulebooks.create_rulebook(session, ME, RulebookCreate(title='룰'))).asset_id

    # A: 룰북을 잠그고 지운 시각을 적었지만 아직 커밋하지 않았다
    rulebook = await repository.find_owned_for_delete(session, Rulebook, ME, rulebook_id)
    rulebook.asset.deleted_at = func.now()
    await session.flush()

    # B: 그 룰북을 가리키는 시나리오를 만들려 한다. A 가 끝날 때까지 기다려야 한다
    data = ScenarioCreate(title='시나리오', rulebook_id=rulebook_id)
    saving = asyncio.create_task(scenarios.create_scenario(other_session, ME, data))
    assert await is_waiting(saving)

    await session.commit()

    # 기다린 뒤에는 룰북이 지워져 있다. 가리킬 수 없다
    with pytest.raises(AssetReferenceError):
        await saving


async def test_two_scenarios_can_hold_the_same_rulebook_at_once(session: AsyncSession, other_session: AsyncSession):
    rulebook_id = (await rulebooks.create_rulebook(session, ME, RulebookCreate(title='룰'))).asset_id

    await assets.hold_reference(session, Rulebook, ME, rulebook_id, 'rulebook_id')

    # 붙잡는 쪽끼리는 서로 기다리지 않는다. 같은 룰북으로 시나리오를 동시에 만들 수 있다
    await asyncio.wait_for(assets.hold_reference(other_session, Rulebook, ME, rulebook_id, 'rulebook_id'), WAIT)
