# game-server/tests/test_whisper_locking.py

"""
같은 쪽지함에 쪽지 둘이 동시에 올 때를 검증한다(#196).

쪽지함의 번호는 "지금까지의 가장 큰 번호 + 1"이다(app/whispers/service.py). 잠금이 없으면 이런 일이 생긴다.
  1. A: 친구의 쪽지함의 가장 큰 번호가 0 이다. 1 번으로 쓴다.
  2. B: 가장 큰 번호가 0 이다(A 가 아직 저장하지 않았다). 1 번으로 쓴다.
결과: 같은 번호가 둘이다. DB 의 유일 조건이 한쪽을 거부하고, 그 사람의 쪽지는 사라진다.

테이블을 잠그고 번호를 정하면 B 는 A 가 끝난 뒤의 번호(1)를 보고 2 번을 받는다.
두 연결(세션)을 따로 열어 이 순서를 직접 만든다.
"""

import asyncio
import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tables import repository as table_repository
from app.tables import service as tables
from app.tables import state as table_state
from app.tables.schemas import JoinRequest
from app.whispers import repository, service
from app.whispers.models import Whisper
from app.whispers.schemas import WhisperCreate
from tests.conftest import no_limits
from tests.signing import make_viewer
from tests.test_chat_locking import FRIEND, ME, is_waiting, open_duo

pytestmark = pytest.mark.usefixtures('clean_tables')

THIRD = uuid.UUID('33333333-2222-4333-8444-555555555555')


@pytest.fixture
async def other_session(app: FastAPI):
    """두 번째 연결. session 과 따로 트랜잭션을 연다."""
    async with app.state.session_factory() as db_session:
        yield db_session


async def test_two_whispers_to_one_mailbox_at_once_get_different_numbers(
    session: AsyncSession, other_session: AsyncSession
):
    table = await open_duo(session)
    # 정원이 둘이라 세 번째 사람은 앉을 수 없다. 자리를 늘려 앉힌다
    table.capacity = 3
    await session.commit()
    table = await tables.join_table(session, make_viewer(THIRD), JoinRequest(invite_code=table.invite_code))

    # A: 테이블을 잠그고 내가 친구에게 보낸 쪽지를 친구의 쪽지함에 올렸지만 아직 커밋하지 않았다
    locked = await table_repository.lock_table(session, table.id)
    sender, recipient = table_state.find_member(locked, ME), table_state.find_member(locked, FRIEND)
    data = WhisperCreate(recipient_id=FRIEND, content='먼저 보낸 쪽지')
    repository.add_whisper(session, service.build_copy(locked, FRIEND, 1, sender, recipient, data, 1))
    await session.flush()

    # B: 세 번째 사람이 친구에게 보낸다. A 가 끝날 때까지 기다려야 한다
    later = WhisperCreate(recipient_id=FRIEND, content='나중에 보낸 쪽지')
    sending = asyncio.create_task(service.post_whisper(other_session, THIRD, table.id, later, no_limits()))
    assert await is_waiting(sending)

    await session.commit()

    # 기다린 뒤에는 A 가 올린 번호가 보인다. B 는 친구의 쪽지함에서 그다음 번호를 받는다
    await sending
    query = select(Whisper.sequence, Whisper.content).where(Whisper.table_id == table.id, Whisper.owner_id == FRIEND)
    stored = (await other_session.execute(query.order_by(Whisper.sequence))).all()
    assert [tuple(row) for row in stored] == [(1, '먼저 보낸 쪽지'), (2, '나중에 보낸 쪽지')]
