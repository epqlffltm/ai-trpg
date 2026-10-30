# story-server/app/withdrawal/repository.py

"""
탈퇴한 사람의 행을 지우는 쿼리. 저장(commit)은 부르는 쪽이 한다.

세션을 지우면 DB 의 외래 키가 딸린 것을 함께 지운다(CASCADE).
  - 말(messages), 말마다의 상태(message_states), 요약(summaries), 기억 메모(memory_notes), 페르소나의 사본
청구 기록(generations)은 지우지 않는다. 세션과 말을 가리키는 칸만 비워진다(SET NULL, chat 과 같다).
세계관의 판의 사본(worlds)은 세션이 가리키는 동안 지우지 못하므로(RESTRICT) 세션 다음에 지운다.
사본을 지우면 로어북의 벡터(lore_embeddings)도 함께 지워진다(CASCADE).
계정의 기록(본 엔딩, 연 일러스트)은 세션과 따로 남는 것이라 따로 지운다.
"""

import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, ImportedWorld
from app.records.models import EndingRecord, IllustrationUnlock


async def delete_conversations_owned(session: AsyncSession, owner_id: uuid.UUID) -> None:
    """그 사람의 세션을 모두 지운다."""
    await session.execute(delete(Conversation).where(Conversation.owner_id == owner_id))


async def delete_worlds_owned(session: AsyncSession, owner_id: uuid.UUID) -> None:
    """그 사람이 가져온 세계관의 판의 사본을 모두 지운다. 세션을 먼저 지워야 한다."""
    await session.execute(delete(ImportedWorld).where(ImportedWorld.owner_id == owner_id))


async def delete_records_owned(session: AsyncSession, owner_id: uuid.UUID) -> None:
    """그 사람의 계정의 기록(본 엔딩, 연 일러스트)을 모두 지운다. 세션을 가리키지 않거나 비울 뿐이라 따로 지운다."""
    await session.execute(delete(EndingRecord).where(EndingRecord.owner_id == owner_id))
    await session.execute(delete(IllustrationUnlock).where(IllustrationUnlock.owner_id == owner_id))
