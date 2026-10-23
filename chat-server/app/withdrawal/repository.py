# chat-server/app/withdrawal/repository.py

"""
탈퇴한 사람의 행을 지우는 쿼리. 저장(commit)은 부르는 쪽이 한다.

대화를 지우면 DB 의 외래 키가 딸린 것을 함께 지운다(CASCADE).
  - 말(messages), 말마다의 상태(message_states), 요약(summaries), 기억 메모(memory_notes), 페르소나의 사본
청구 기록(generations)은 지우지 않는다. 대화와 말을 가리키는 칸만 비워진다(SET NULL, #670).
캐릭터의 판의 사본(characters)은 대화가 가리키는 동안 지우지 못하므로(RESTRICT) 대화 다음에 지운다.
연 이벤트 씬의 기록(scene_unlocks)은 대화와 따로 남는 것이라 따로 지운다.
"""

import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, ImportedCharacter
from app.gallery.models import SceneUnlock


async def delete_conversations_owned(session: AsyncSession, owner_id: uuid.UUID) -> None:
    """그 사람의 대화를 모두 지운다. 지운 것으로 적어 둔 것(deleted_at)도 지운다."""
    await session.execute(delete(Conversation).where(Conversation.owner_id == owner_id))


async def delete_unlocks_owned(session: AsyncSession, owner_id: uuid.UUID) -> None:
    """그 사람이 연 이벤트 씬의 기록을 모두 지운다(#669). 대화를 가리키지 않아 따로 지운다."""
    await session.execute(delete(SceneUnlock).where(SceneUnlock.owner_id == owner_id))


async def delete_characters_owned(session: AsyncSession, owner_id: uuid.UUID) -> None:
    """그 사람이 가져온 캐릭터의 판의 사본을 모두 지운다. 대화를 먼저 지워야 한다."""
    await session.execute(delete(ImportedCharacter).where(ImportedCharacter.owner_id == owner_id))
