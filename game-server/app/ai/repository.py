# game-server/app/ai/repository.py

"""
AI 호출의 기록(ai_invocations)을 고치는 SQL. 커밋하지 않는다.

기록을 쓰는 것은 app/ai/call_log.py 다. 여기는 보관 기간이 지난 원문을 비우는 것(app/ai/retention.py)만 있다.
"""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.models import AiInvocation


async def clear_old_texts(session: AsyncSession, before: datetime, limit: int) -> int:
    """
    before 보다 먼저 남긴 기록의 원문(text)을 오래된 것부터 limit 개 비운다. 비운 수를 돌려준다.

    원문만 비우고 줄은 남긴다. 모델, 토큰 수, 걸린 시간, 결과는 사용량과 비용의 근거다.
    고를 때 다른 서버가 잠근 줄은 건너뛴다(SKIP LOCKED). 서버가 여럿이어도 같은 줄을 두고 기다리지 않는다.
    색인(ix_ai_invocations_text_kept)이 원문이 남은 줄만 담는다. 비운 줄은 색인에서 빠져 다시 훑지 않는다.
    """
    chosen = (
        select(AiInvocation.id)
        .where(AiInvocation.text.is_not(None), AiInvocation.created_at < before)
        .order_by(AiInvocation.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    result = await session.execute(update(AiInvocation).where(AiInvocation.id.in_(chosen)).values(text=None))
    return result.rowcount
