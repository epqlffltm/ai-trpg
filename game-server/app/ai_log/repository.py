# game-server/app/ai_log/repository.py

"""
AI 호출의 기록(ai_invocations)을 고치는 SQL. 커밋하지 않는다.

기록을 쓰는 것은 app/ai_log/call_log.py 다. 여기는 보관 기간이 지난 원문을 비우는 것(app/ai_log/retention.py)만 있다.
"""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_log.models import AiInvocation


async def choose_old_texts(session: AsyncSession, before: datetime, limit: int) -> list[uuid.UUID]:
    """
    before 보다 먼저 남긴 기록 중 원문이 남은 것을 오래된 것부터 limit 개 골라 잠근다. 고른 줄의 id 를 돌려준다.

    다른 서버가 잠근 줄은 건너뛴다(SKIP LOCKED). 서버가 여럿이어도 같은 줄을 두고 기다리지 않는다.
    색인(ix_ai_invocations_text_kept)이 원문이 남은 줄만 담는다. 비운 줄은 색인에서 빠져 다시 훑지 않는다.
    """
    chosen = (
        select(AiInvocation.id)
        .where(AiInvocation.text.is_not(None), AiInvocation.created_at < before)
        .order_by(AiInvocation.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(await session.scalars(chosen))


async def clear_texts(session: AsyncSession, ids: list[uuid.UUID]) -> int:
    """그 기록들의 원문(text)을 비운다. 비운 수를 돌려준다. 줄과 그 밖의 칸은 남긴다."""
    if not ids:
        return 0
    result = await session.execute(update(AiInvocation).where(AiInvocation.id.in_(ids)).values(text=None))
    return result.rowcount


async def clear_old_texts(session: AsyncSession, before: datetime, limit: int) -> int:
    """
    before 보다 먼저 남긴 기록의 원문을 오래된 것부터 limit 개까지 비운다. 비운 수를 돌려준다.

    원문만 비우고 줄은 남긴다. 모델, 토큰 수, 걸린 시간, 결과는 사용량과 비용의 근거다.
    고르기와 비우기를 두 문장으로 나눈다. 한 문장(UPDATE … WHERE id IN (SELECT … LIMIT … FOR UPDATE SKIP LOCKED))으로
    쓰면 계획기가 Nested Loop Semi Join 을 고를 때 안쪽 SELECT 를 바깥 줄마다 다시 돌려 LIMIT 을 넘겨 비울 수 있다.
    고른 줄은 같은 트랜잭션 안에서 잠겨 있으므로 둘 사이에 다른 서버가 끼어들지 못한다.
    """
    return await clear_texts(session, await choose_old_texts(session, before, limit))
