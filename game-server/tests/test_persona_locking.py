# game-server/tests/test_persona_locking.py

"""
같은 사람이 보관함에 캐릭터를 동시에 넣을 때를 검증한다.

넣기는 "몇 개인지 세고 나서 넣는다". 잠금이 없으면 이런 일이 생긴다.
  1. A: 센다. 49 개다. 자리가 있다.
  2. B: 센다. 49 개다(A 가 아직 저장하지 않았다). 자리가 있다.
  3. A: 넣는다.   4. B: 넣는다.
결과: 상한(50)을 넘어 51 개가 된다.

보관함에는 잠글 행이 없다. 비어 있을 수도 있고, 테이블 전체를 잠그면 남의 보관함까지 멈춘다.
그래서 "이 사람"이라는 이름에 거는 잠금(advisory lock)을 쓴다(app/personas/repository.py 의 lock_owner).
두 연결(세션)을 따로 열어 위의 순서를 직접 만든다(tests/test_table_locking.py 와 같은 방법).
"""

import asyncio
import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.personas import repository, service
from app.personas.models import PERSONA_MAX_PER_OWNER, Persona
from app.personas.schemas import PersonaWrite
from app.personas.service import Conflict, PersonaConflictError

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
STRANGER = uuid.UUID('99999999-2222-4333-8444-555555555555')

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


async def fill_vault(session: AsyncSession, owner_id: uuid.UUID, count: int) -> None:
    """보관함을 채우고 저장한다."""
    session.add_all(Persona(owner_id=owner_id, name=f'엑스트라 {number}') for number in range(count))
    await session.commit()


async def test_keeping_waits_for_another_keeping(session: AsyncSession, other_session: AsyncSession):
    await fill_vault(session, ME, PERSONA_MAX_PER_OWNER - 1)

    # A: 내 보관함을 잠그고 마지막 자리에 넣었지만 아직 커밋하지 않았다
    await repository.lock_owner(session, ME)
    repository.add_persona(session, Persona(owner_id=ME, name='드워프'))
    await session.flush()

    # B: 같은 사람이 또 넣으려 한다. A 가 끝날 때까지 기다려야 한다
    keeping = asyncio.create_task(service.create_persona(other_session, ME, PersonaWrite(name='오크')))
    assert await is_waiting(keeping)

    await session.commit()

    # 기다린 뒤에 세면 A 가 넣은 것까지 보인다. 자리가 없다
    with pytest.raises(PersonaConflictError) as refused:
        await keeping
    assert refused.value.reason == Conflict.VAULT_FULL
    await other_session.rollback()
    assert await other_session.scalar(text('SELECT count(*) FROM personas')) == PERSONA_MAX_PER_OWNER


async def test_someone_elses_vault_does_not_wait(session: AsyncSession, other_session: AsyncSession):
    # A: 내 보관함을 잠근 채로 있다
    await repository.lock_owner(session, ME)

    # B: 다른 사람의 보관함은 기다리지 않는다. 잠금은 사람마다 따로다
    keeping = asyncio.create_task(service.create_persona(other_session, STRANGER, PersonaWrite(name='오크')))

    assert not await is_waiting(keeping)
    assert (await keeping).owner_id == STRANGER
    await session.rollback()
