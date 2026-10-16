# game-server/app/drafts/drafting.py

"""
라운드의 서술이 끝난 뒤에 장부 초안을 쓰고 줄로 적는다. 서술을 맡은 작업의 끝에서 돈다(app/rounds/closing.py).

하는 일은 셋이다. 셋을 한 함수에 섞지 않는다.
  1. 테이블을 읽어 초안을 부탁할 것을 만든다. 장부 초안을 켠 진행 중인 테이블만이다(load_request).
  2. 초안을 쓰는 것(Drafter)을 부른다. 이때는 DB 연결도 잠금도 쥐고 있지 않다.
  3. 테이블을 잠그고, 아직 적을 초안인지 다시 보고, 기다리던 앞의 줄을 만료시키고, 새 줄을 적는다(save_drafts).

초안은 덤이다. 라운드는 이미 닫혔고 다음 라운드가 열렸다. 여기서 무엇이 실패해도 예외를 올리지 않는다.
로그(ledger_draft.write, ledger_draft.failed)만 남기고, 방장은 손으로 하던 대로 하면 된다.
시간의 상한이 따로 있다(DRAFT_BUDGET_SECONDS). 서술의 시간과 섞지 않는다.

초안을 쓰는 사이에 장부가 바뀌었을 수 있다(방장이 물건을 줬다, 퀘스트를 끝냈다).
그래서 받아들일 때 다시 본다. 여기서는 쓴 그대로 적는다.

초안을 쓰는 사이에 다음 라운드가 닫히고 그 초안이 먼저 적힐 수도 있다. 초안은 라운드가 넘어간 뒤에 쓰기 때문이다.
테이블을 잠그는 것은 쓰기를 하나씩 하게 할 뿐, 어느 것이 새것인지는 정하지 않는다.
그래서 잠근 뒤에 다시 본다(is_still_wanted). 뒤의 라운드가 이미 서술을 마쳤으면 이 장면은 낡았으니 버린다.
테이블이 끝났거나 방장이 장부 초안을 껐어도 버린다. 만료시키는 것도 이 라운드보다 앞의 줄만이다.
"""

import asyncio
import logging
import uuid
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.assets.scenarios.snapshot import read_snapshot
from app.drafts import records, repository
from app.drafts.context import build_context
from app.drafts.validation import NOTHING, Checked
from app.drafts.writer import DraftRequest
from app.tables import repository as table_repository
from app.tables.models import GameTable, TableStatus

logger = logging.getLogger(__name__)

# 로그의 이름과 실패의 코드(docs/observability.md)
OPERATION = 'ledger_draft.write'
FAILED_ERROR_CODE = 'ledger_draft.failed'

# 초안을 읽고, 부르고, 적는 데 쓰는 시간(초). 모델의 한 번의 시간 초과보다 조금 길다
DRAFT_BUDGET_SECONDS = 90.0


class Drafter(Protocol):
    """장부 초안을 쓰는 것. 구현은 app/drafts/writer.py 의 DraftWriter 다."""

    async def draft(self, request: DraftRequest) -> Checked:
        """장면에서 초안을 쓴다. 검증을 거쳐 받은 것과 버린 것이다."""
        ...


class NoDrafts:
    """아무것도 쓰지 않는 것. 언어 모델을 쓰지 않는 서버(가짜 서술자)와 테스트에서 꽂는다."""

    async def draft(self, request: DraftRequest) -> Checked:
        return NOTHING


NO_DRAFTS = NoDrafts()


async def load_request(session: AsyncSession, table_id: uuid.UUID, number: int, scene: str) -> DraftRequest | None:
    """
    초안을 부탁할 것. 테이블의 지금 상태로 목록을 만든다. 잠그지 않는다.

    테이블이 없거나, 장부 초안을 끄고 있거나, 진행 중이 아니면(끝났다) None 이다.
    """
    table = await table_repository.find_table(session, table_id)
    if table is None or not table.ledger_drafts or table.status != TableStatus.PLAYING:
        return None
    context = build_context(table, read_snapshot(table.content))
    return DraftRequest(scene=scene, context=context, table_id=table.id, round_number=number, host_id=table.host_id)


async def is_still_wanted(session: AsyncSession, table: GameTable | None, number: int) -> bool:
    """
    잠근 테이블에 number 라운드의 초안을 아직 적을 것인가.

    테이블이 있고, 진행 중이고, 장부 초안을 켜 두었고, 뒤의 라운드가 아직 서술을 마치지 않았어야 한다.
    """
    if table is None or not table.ledger_drafts or table.status != TableStatus.PLAYING:
        return False
    return not await repository.later_scene_told(session, table.id, number)


async def save_drafts(session: AsyncSession, table_id: uuid.UUID, number: int, checked: Checked) -> int:
    """
    테이블을 잠그고, 기다리던 앞의 줄을 만료시키고, 새 줄을 적고 저장한다. 새 줄의 수를 돌려준다.

    잠근 뒤에 아직 적을 초안인지 다시 본다(is_still_wanted). 아니면 아무것도 바꾸지 않고 0 이다.
    새 초안이 비어 있어도 앞의 줄은 만료시킨다. 장면이 한 라운드 넘어가 낡았다.
    잠그는 까닭: 방장이 앞의 줄을 받아들이는 일과 겹치지 않게 한다. 받아들인 줄이 만료로 덮이지 않는다.
    """
    table = await table_repository.lock_table(session, table_id)
    if not await is_still_wanted(session, table, number):
        return 0
    await repository.expire_pending(session, table_id, before_round=number)
    rows = records.to_rows(table_id, number, checked)
    repository.add_drafts(session, rows)
    await session.commit()
    return len(rows)


async def write_drafts(
    session_factory: async_sessionmaker[AsyncSession], drafter: Drafter, table_id: uuid.UUID, number: int, scene: str
) -> None:
    """읽고, 부르고, 적는다. 세션을 그때그때 따로 연다. 초안을 쓰는 동안에는 어느 세션도 열려 있지 않다."""
    async with session_factory() as session:
        request = await load_request(session, table_id, number, scene)
    if request is None:
        return
    checked = await drafter.draft(request)
    async with session_factory() as session:
        await save_drafts(session, table_id, number, checked)


async def draft_ledger(
    session_factory: async_sessionmaker[AsyncSession],
    drafter: Drafter,
    table_id: uuid.UUID,
    number: int,
    scene: str,
    budget: float = DRAFT_BUDGET_SECONDS,
) -> None:
    """방금 서술한 장면으로 장부 초안을 쓴다. budget 초까지만 해 본다. 예외를 올리지 않는다(로그만 남긴다)."""
    try:
        async with asyncio.timeout(budget):
            await write_drafts(session_factory, drafter, table_id, number, scene)
    except Exception:
        logger.warning(
            '장부 초안을 쓰지 못했다. 방장은 손으로 장부를 고치면 된다',
            exc_info=True,
            extra={
                'operation': OPERATION,
                'table_id': str(table_id),
                'round': number,
                'result': 'server_error',
                'error_code': FAILED_ERROR_CODE,
            },
        )
