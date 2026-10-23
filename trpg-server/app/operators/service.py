# trpg-server/app/operators/service.py

"""
운영자가 남의 테이블과 시나리오를 본다(#391). 볼 때마다 감사 기록을 먼저 남긴다.

HTTP 를 모른다. 운영자인지는 부르는 쪽(app/operators/router.py 의 require_operator)이 이미 확인했다.
여기서는 앉아 있는지, 만든 사람인지를 보지 않는다.

감사 기록을 먼저 커밋하고 그다음에 읽는다. 없는 테이블을 본 시도도 남는다.
읽다가 실패해도 기록은 남는다. 무엇을 보려 했는지가 기록의 목적이라서다.
"""

import logging
import uuid
from datetime import datetime

from server_core.observability.context import current_ids
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Scenario, ScenarioVersion
from app.assets.scenarios import repository as versions
from app.assets.service import AssetNotFoundError
from app.chat import repository as messages
from app.chat.models import ChatMessage
from app.events import repository as events
from app.events.models import TableEvent
from app.operators import repository
from app.operators.models import OperatorRead, ReadKind
from app.tables import repository as tables
from app.tables.errors import TableNotFoundError
from app.tables.models import GameTable
from app.whispers.models import Whisper

logger = logging.getLogger(__name__)

# 운영자가 남의 것을 본 로그의 operation(docs/observability.md)
READ_OPERATION = 'operator.read'


def build_read(
    operator_id: uuid.UUID,
    kind: ReadKind,
    target_id: uuid.UUID,
    reason: str,
    now: datetime,
    number: int | None = None,
) -> OperatorRead:
    """감사 기록 한 줄을 만든다. 아직 저장하지 않는다. 지금 요청의 식별자를 함께 적는다."""
    return OperatorRead(
        operator_id=operator_id,
        read_at=now,
        target_kind=kind,
        target_id=target_id,
        target_number=number,
        reason=reason,
        request_id=current_ids().get('request_id'),
    )


def log_read(read: OperatorRead) -> None:
    """감사 기록과 같은 것을 로그에도 남긴다. 사유는 싣지 않는다(자유 글이라 개인정보가 섞일 수 있다)."""
    logger.info(
        '운영자가 남의 것을 보았다',
        extra={
            'operation': READ_OPERATION,
            'operator_id': str(read.operator_id),
            'target_kind': read.target_kind,
            'target_id': str(read.target_id),
            'target_number': read.target_number,
        },
    )


async def record_read(session: AsyncSession, read: OperatorRead) -> None:
    """감사 기록을 저장하고 로그를 남긴다. 읽기 전에 부른다."""
    repository.add_read(session, read)
    await session.commit()
    log_read(read)


async def find_table(session: AsyncSession, table_id: uuid.UUID) -> GameTable:
    """누구의 테이블이든 하나를 찾는다. 없으면 TableNotFoundError."""
    table = await tables.find_table(session, table_id)
    if table is None:
        raise TableNotFoundError
    return table


async def read_table(
    session: AsyncSession, operator_id: uuid.UUID, table_id: uuid.UUID, reason: str, now: datetime
) -> GameTable:
    """테이블 하나를 본다. 없으면 TableNotFoundError."""
    await record_read(session, build_read(operator_id, ReadKind.TABLE, table_id, reason, now))
    return await find_table(session, table_id)


async def read_events(
    session: AsyncSession,
    operator_id: uuid.UUID,
    table_id: uuid.UUID,
    reason: str,
    now: datetime,
    after: int,
    limit: int,
) -> tuple[GameTable, list[TableEvent]]:
    """테이블의 기록 중 after 번 뒤의 것을 본다. 앉은 사람이 읽는 것과 같은 순서다."""
    await record_read(session, build_read(operator_id, ReadKind.TABLE_EVENTS, table_id, reason, now))
    table = await find_table(session, table_id)
    return table, await events.list_after(session, table_id, after, limit)


async def read_messages(
    session: AsyncSession,
    operator_id: uuid.UUID,
    table_id: uuid.UUID,
    reason: str,
    now: datetime,
    after: int,
    limit: int,
) -> tuple[GameTable, list[ChatMessage]]:
    """테이블 대화 중 after 번 뒤의 것을 본다."""
    await record_read(session, build_read(operator_id, ReadKind.TABLE_MESSAGES, table_id, reason, now))
    table = await find_table(session, table_id)
    return table, await messages.list_after(session, table_id, after, limit)


async def read_whispers(
    session: AsyncSession,
    operator_id: uuid.UUID,
    table_id: uuid.UUID,
    reason: str,
    now: datetime,
    limit: int,
    offset: int,
) -> tuple[list[Whisper], int]:
    """테이블의 귓속말 전부(누가 누구에게)의 한 쪽과 전체 장 수를 본다."""
    await record_read(session, build_read(operator_id, ReadKind.TABLE_WHISPERS, table_id, reason, now))
    await find_table(session, table_id)
    found = await repository.list_whispers(session, table_id, limit, offset)
    return found, await repository.count_whispers(session, table_id)


async def read_scenario(
    session: AsyncSession, operator_id: uuid.UUID, scenario_id: uuid.UUID, reason: str, now: datetime
) -> Scenario:
    """시나리오의 초안을 본다. 없거나 지웠으면 AssetNotFoundError."""
    await record_read(session, build_read(operator_id, ReadKind.SCENARIO, scenario_id, reason, now))
    scenario = await repository.find_scenario(session, scenario_id)
    if scenario is None:
        raise AssetNotFoundError
    return scenario


async def read_version(
    session: AsyncSession, operator_id: uuid.UUID, scenario_id: uuid.UUID, number: int, reason: str, now: datetime
) -> ScenarioVersion:
    """시나리오의 판 하나를 굳힌 내용 전부와 함께 본다. 없으면 AssetNotFoundError."""
    await record_read(session, build_read(operator_id, ReadKind.SCENARIO_VERSION, scenario_id, reason, now, number))
    version = await versions.find_version(session, scenario_id, number)
    if version is None:
        raise AssetNotFoundError
    return version
