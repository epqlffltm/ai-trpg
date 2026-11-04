# story-server/app/stats/repository.py

"""
세계관마다 세션을 시작한 수를 센다(#985). SQL 은 이 파일에만 있다.

세션은 세계관의 판의 사본을 가리키므로 사본의 원본 id(source_id, asset 서버의 id)로 묶는다.
지운 것으로 적어 둔 세션도 센다. 한 번 시작한 일이다. 탈퇴로 지운 것은 없으므로 세지 않는다.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, ImportedWorld


async def count_starts(session: AsyncSession, recent_since: datetime) -> list[tuple[uuid.UUID, int, int]]:
    """원본 id, 모든 세션의 수, recent_since 뒤에 시작한 수. 원본 id 의 차례다."""
    recent = func.count().filter(Conversation.created_at >= recent_since)
    query = (
        select(ImportedWorld.source_id, func.count(), recent)
        .join(Conversation, Conversation.world_id == ImportedWorld.id)
        .group_by(ImportedWorld.source_id)
        .order_by(ImportedWorld.source_id)
    )
    rows = await session.execute(query)
    return [(work_id, total, recent_count) for work_id, total, recent_count in rows.all()]
