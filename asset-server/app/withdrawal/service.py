# asset-server/app/withdrawal/service.py

"""
탈퇴한 사람의 것을 지운다(docs/architecture/withdrawal.md 의 "마칠 때: 다른 서버").

  - 페르소나를 모두 지운다. 가져간 세션은 사본으로 돈다
  - 비공개 캐릭터를 판과 함께 지운다. 공개 캐릭터는 남긴다(남이 쓰는 것이다)
  - 그림(#566)이 생기면 그 사람의 그림도 여기서 지운다
한 트랜잭션이다. 일부만 지워진 채로 남지 않는다.
같은 알림이 다시 와도 결과가 같다. 지울 것이 없으면 아무것도 하지 않는다(멱등).
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.characters import repository as characters
from app.personas import repository as personas


async def erase_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    """그 사람의 페르소나와 비공개 캐릭터를 지우고 저장한다."""
    await personas.delete_all_owned(session, user_id)
    await characters.delete_private_owned(session, user_id)
    await session.commit()
