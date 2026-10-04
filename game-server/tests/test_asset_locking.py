# game-server/tests/test_asset_locking.py

"""
"확인하고 나서 쓰는" 일 둘이 동시에 일어날 때를 검증한다.

1) 자산을 가리키는 일과 지우는 일.

잠금이 없으면 이런 일이 생긴다.
  1. A: 룰북이 있는지 확인한다. 있다.
  2. B: 그 룰북을 쓰는 시나리오가 있는지 확인한다. 없다(A 가 아직 저장하지 않았다).
  3. A: 시나리오를 저장한다.   4. B: 룰북을 지운다.
결과: 지운 룰북을 가리키는 시나리오가 남는다.

2) 로어북에 항목을 더하는 일 둘. 둘 다 개수를 세고 "자리가 있다"고 보면 상한을 넘긴다.
3) 시나리오의 로어북 목록을 바꾸는 일 둘. 둘 다 같은 옛 목록과 비교하면 둘의 것이 합쳐진다.

두 연결(세션)을 따로 열어 이 순서를 직접 만든다. 한쪽이 잠근 채로 멈춰 있을 때 다른 쪽이 기다리는지 본다.
"""

import asyncio
import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import repository
from app.assets import service as assets
from app.assets.lorebooks import service as lorebooks
from app.assets.lorebooks.schemas import EntryCreate, LorebookCreate
from app.assets.lorebooks.service import LorebookFullError
from app.assets.models import Lorebook, Rulebook, Scenario, ScenarioLorebook
from app.assets.rulebooks import service as rulebooks
from app.assets.rulebooks.schemas import RulebookCreate
from app.assets.scenarios import service as scenarios
from app.assets.scenarios.schemas import ScenarioCreate, ScenarioUpdate
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
    rulebook = await repository.lock_owned(session, Rulebook, ME, rulebook_id)
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


async def test_adding_an_entry_waits_for_another_entry_being_added(
    session: AsyncSession, other_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(lorebooks, 'LOREBOOK_MAX_ENTRIES', 1)
    lorebook_id = (await lorebooks.create_lorebook(session, ME, LorebookCreate(title='로어북'))).asset_id

    # A: 로어북을 잠그고 마지막 자리에 항목을 올렸지만 아직 커밋하지 않았다
    await assets.lock_owned(session, Lorebook, ME, lorebook_id)
    session.add(lorebooks.build_entry(lorebook_id, EntryCreate(name='첫째')))
    await session.flush()

    # B: 같은 로어북에 항목을 더하려 한다. A 가 끝날 때까지 기다려야 한다
    adding = asyncio.create_task(lorebooks.add_entry(other_session, ME, lorebook_id, EntryCreate(name='둘째')))
    assert await is_waiting(adding)

    await session.commit()

    # 기다린 뒤에는 A 의 항목이 세어진다. 자리가 없다
    with pytest.raises(LorebookFullError):
        await adding


async def test_updating_a_scenario_waits_for_another_update(session: AsyncSession, other_session: AsyncSession):
    first = (await lorebooks.create_lorebook(session, ME, LorebookCreate(title='첫째'))).asset_id
    second = (await lorebooks.create_lorebook(session, ME, LorebookCreate(title='둘째'))).asset_id
    scenario_id = (await scenarios.create_scenario(session, ME, ScenarioCreate(title='시나리오'))).asset_id

    # A: 시나리오를 잠그고 첫째 로어북을 붙였지만 아직 커밋하지 않았다
    scenario = await assets.lock_owned(session, Scenario, ME, scenario_id)
    scenario.lorebook_ids = [first]
    await session.flush()

    # B: 같은 시나리오의 목록을 둘째 로어북으로 바꾸려 한다. A 가 끝날 때까지 기다려야 한다
    data = ScenarioUpdate(lorebook_ids=[second])
    updating = asyncio.create_task(scenarios.update_scenario(other_session, ME, scenario_id, data))
    assert await is_waiting(updating)

    await session.commit()

    await updating

    # 기다린 뒤에는 A 가 붙인 것이 보인다. 그것을 떼고 자기 목록으로 바꾼다.
    # 잠그지 않으면 B 는 "아무것도 붙지 않은" 옛 목록과 비교해서, 둘째를 더하기만 하고 첫째를 떼지 않는다
    stored = await session.scalars(
        select(ScenarioLorebook.lorebook_id).where(ScenarioLorebook.scenario_id == scenario_id)
    )
    assert list(stored) == [second]
