# asset-server/app/withdrawal/service.py

"""
탈퇴한 사람의 것을 지운다(docs/architecture/withdrawal.md 의 "마칠 때: 다른 서버").

  - 페르소나를 모두 지운다. 가져간 세션은 사본으로 돈다
  - 비공개 캐릭터를 판과 함께 지운다. 공개 캐릭터는 남긴다(남이 쓰는 것이다)
  - 로어북을 판과 함께 모두 지운다(#672, 지금은 만든 사람만 쓴다). 남긴 공개 캐릭터의 판에 복사된 것은 남는다
  - 그 사람의 그림 가운데 어느 판에도 쓰이지 않은 것을 저장소와 표에서 지운다(#566). 남긴 공개 캐릭터의 그림은 남는다
페르소나와 캐릭터와 로어북은 한 트랜잭션이다. 그림은 그다음이다(app/images/service.py 의 erase_images).
저장소에서 지우다 실패하면 ImageStoreUnavailableError(503)다. 인증 서버가 다시 보내면 남은 그림을 다시 지운다.
같은 알림이 다시 와도 결과가 같다. 지울 것이 없으면 아무것도 하지 않는다(멱등).
"""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.characters import repository as characters
from app.images import service as images
from app.images.store import ImageStore
from app.lorebooks import repository as lorebooks
from app.personas import repository as personas


async def erase_belongings(session: AsyncSession, user_id: uuid.UUID) -> None:
    """그 사람의 페르소나와 비공개 캐릭터와 로어북을 지우고 저장한다."""
    await personas.delete_all_owned(session, user_id)
    await characters.delete_private_owned(session, user_id)
    await lorebooks.delete_owned(session, user_id)
    await session.commit()


async def erase_user(session: AsyncSession, store: ImageStore, user_id: uuid.UUID, now: datetime) -> None:
    """그 사람의 페르소나와 비공개 캐릭터를 지우고, 남은 판에 쓰이지 않은 그림을 지운다."""
    await erase_belongings(session, user_id)
    await images.erase_images(session, store, user_id, now)
