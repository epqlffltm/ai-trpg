# chat-server/app/world/service.py

"""
대화의 지금 상태를 읽는다. 판의 사본(시작 상태)과 가지의 말마다의 상태(message_states)를 합친다.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.schemas import CharacterDocument
from app.conversations.models import ImportedCharacter
from app.world import repository
from app.world.state import WorldState, filled, initial_state, state_at


def document_of(character: ImportedCharacter) -> CharacterDocument:
    """대화가 가져온 판의 문서."""
    return CharacterDocument.model_validate(character.document)


async def state_on(session: AsyncSession, document: CharacterDocument, path_ids: Sequence[uuid.UUID]) -> WorldState:
    """가지(첫 말부터 끝까지의 id)의 끝의 상태. 가지에 상태가 하나도 없으면 판의 시작 상태다."""
    states = await repository.states_for(session, path_ids)
    return filled(document, state_at(path_ids, states, initial_state(document)))
