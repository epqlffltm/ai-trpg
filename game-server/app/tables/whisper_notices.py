# game-server/app/tables/whisper_notices.py

"""
쪽지를 보낸 사실을 모두에게 알릴지 바꾼다. 방장만 한다(#196).

켜면 쪽지를 보낼 때마다 "누가 누구에게 보냈다"를 이벤트로 남긴다(app/whispers/service.py). 글은 싣지 않는다.
바꾼 뒤에 보내는 쪽지부터 따른다. 이미 보낸 쪽지를 거슬러 알리지 않는다.

바꾼 것은 이벤트로 남긴다. 앉은 사람 모두가 스트림으로 본다. 알림이 꺼진 것도 모두가 안다.

HTTP 를 모른다. 테이블을 잠그고 한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.events import recorder
from app.events.models import EventType
from app.tables.models import GameTable
from app.tables.schemas import WhisperNoticeUpdate
from app.tables.service import lock_seated, save
from app.tables.state import require_host, require_not_ended


async def change_whisper_notice(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, data: WhisperNoticeUpdate
) -> GameTable:
    """
    방장이 쪽지를 보낸 사실을 알릴지 바꾼다.

    방장이 아니면 NotHostError, 끝난 테이블이면 TableConflictError.
    지금과 같으면 아무것도 적지 않는다. 바뀐 것이 없는데 이벤트가 쌓이지 않게 한다.
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_not_ended(table)

    if table.whisper_notice == data.whisper_notice:
        return table

    table.whisper_notice = data.whisper_notice
    recorder.record(session, table, EventType.WHISPER_NOTICE_CHANGED, actor_id=host_id, payload=data.model_dump())
    return await save(session, table)
