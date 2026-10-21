# notification-server/app/withdrawals/service.py

"""
탈퇴한 사람의 것을 지우는 규칙(#603, docs/architecture/withdrawal.md). HTTP 를 모른다.
인증 서버의 서명은 router.py 가 확인했다.

  - 지우는 것: 그 사람의 알림(읽은 것, 읽지 않은 것 모두)과 끈 알림의 종류. 둘을 한 트랜잭션에서 지운다
  - 남기는 것이 없다. 알림의 원문은 그 일을 맡은 서버에 있고, 그 서버가 탈퇴를 따로 받는다
  - 몇 번을 불러도 같다. 두 번째에는 지울 것이 없다. 이 서버가 모르는 사람도 지울 것이 없을 뿐이다
  - 탈퇴한 뒤에 다른 서버가 그 사람의 알림을 늦게 넣으면 다시 생긴다. 보관 기간(30일)이 지나면 지워진다
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.withdrawals import repository
from app.withdrawals.schemas import Erased


async def erase_user(session: AsyncSession, user_id: uuid.UUID) -> Erased:
    """그 사람의 알림과 끈 종류를 지우고 커밋한다. 지운 수를 돌려준다."""
    notifications = await repository.delete_notifications(session, user_id)
    mutes = await repository.delete_mutes(session, user_id)
    await session.commit()
    return Erased(notifications=notifications, mutes=mutes)
