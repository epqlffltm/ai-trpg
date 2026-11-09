# chat-server/app/achievements/service.py

"""
답을 저장한 뒤 업적을 주고 대화한 사람으로 적는다(docs/architecture/achievements.md 의 "chat").

말 한 번(app/turns/service.py 의 run_generation)이 답을 저장한 다음에 부른다. 답의 저장과 따로인 트랜잭션이다.
여기서 실패해도 답은 남는다(업적은 다음 답에서 다시 본다. 이미 받은 것은 계정에 남아 있다).
  - 답이 끝인 가지로 본다: 그 가지의 상태(행동과 받아들인 상태의 변화가 든다)와 그 가지에서 보낸 말의 수
  - 다시 생성과 이어서 출력도 같이 본다(가지가 같으면 새로 맞는 것이 없다)
  - 처음 받은 것만 돌려준다. done 메시지에 싣는다
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.achievements import repository
from app.achievements.schemas import EarnedAchievementOut
from app.assets.schemas import AchievementDocument, CharacterDocument
from app.conversations import repository as conversations
from app.conversations.models import Conversation, ImportedCharacter, Message, Role
from app.world import service as world
from app.world.achievements import newly_earned


async def character_of(session: AsyncSession, conversation_id: uuid.UUID) -> ImportedCharacter | None:
    """대화가 가져온 캐릭터의 판의 사본. 대화가 없으면(그사이 지웠다) None."""
    query = (
        select(ImportedCharacter)
        .join(Conversation, Conversation.character_id == ImportedCharacter.id)
        .where(Conversation.id == conversation_id)
    )
    return await session.scalar(query)


def sent_count(path: Sequence[Message]) -> int:
    """가지에서 보낸 말(사람의 말)의 수. 행동 말과 상대의 말은 세지 않는다."""
    return sum(1 for message in path if message.role == Role.USER)


def earned_out(achievement: AchievementDocument) -> EarnedAchievementOut:
    """받은 업적 하나를 done 메시지의 모양으로."""
    return EarnedAchievementOut(
        id=achievement.id, name=achievement.name, description=achievement.description, image_id=achievement.image_id
    )


async def candidates_on(
    session: AsyncSession, document: CharacterDocument, owner_id: uuid.UUID, source: uuid.UUID, answer_id: uuid.UUID
) -> tuple[AchievementDocument, ...]:
    """답이 끝인 가지에서 조건이 맞고 아직 받지 않은 업적들(판의 차례)."""
    path = await conversations.active_path(session, answer_id)
    state = await world.state_on(session, document, [message.id for message in path])
    owned = await repository.achievement_ids_of(session, owner_id, source)
    return newly_earned(document, state, sent_count(path), owned)


async def award(
    session_factory: async_sessionmaker[AsyncSession],
    owner_id: uuid.UUID,
    conversation_id: uuid.UUID,
    answer_id: uuid.UUID,
    now: datetime,
) -> tuple[EarnedAchievementOut, ...]:
    """대화한 사람으로 적고, 처음 받은 업적을 계정에 적어 돌려준다. 업적이 없는 판에서도 대화한 사람으로 적는다."""
    async with session_factory() as session:
        character = await character_of(session, conversation_id)
        if character is None:
            return ()
        await repository.mark_played(session, owner_id, character.source_id, now)
        document = world.document_of(character)
        earned: tuple[EarnedAchievementOut, ...] = ()
        if document.achievements:
            candidates = await candidates_on(session, document, owner_id, character.source_id, answer_id)
            added = await repository.add_achievements(
                session, owner_id, character.source_id, candidates, conversation_id, now
            )
            earned = tuple(earned_out(achievement) for achievement in candidates if achievement.id in added)
        await session.commit()
    return earned
