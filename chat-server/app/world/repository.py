# chat-server/app/world/repository.py

"""
말마다의 상태를 읽고 적는다. 상태의 값(WorldState)과 행(MessageState)을 오간다.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.world.models import MessageState
from app.world.state import Holding, WorldState


def to_state(row: MessageState) -> WorldState:
    """행을 상태의 값으로."""
    holdings = tuple(Holding(entry['item'], entry['count']) for entry in row.inventory)
    return WorldState(
        place=row.place,
        minutes=row.minutes,
        inventory=holdings,
        visited=tuple(row.visited),
        outfit=tuple(row.outfit),
        affection=row.affection,
        fired=tuple(row.fired),
        shown=tuple(row.shown),
        received=tuple(row.received),
    )


def to_row(message_id: uuid.UUID, state: WorldState) -> MessageState:
    """상태의 값을 그 말의 행으로. 아직 저장하지 않는다."""
    return MessageState(
        message_id=message_id,
        place=state.place,
        minutes=state.minutes,
        inventory=[{'item': holding.item, 'count': holding.count} for holding in state.inventory],
        visited=list(state.visited),
        outfit=list(state.outfit),
        affection=state.affection,
        fired=list(state.fired),
        shown=list(state.shown),
        received=list(state.received),
    )


async def states_for(session: AsyncSession, message_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, WorldState]:
    """그 말들 가운데 상태가 있는 것의 상태. 한 번의 쿼리다."""
    if not message_ids:
        return {}
    rows = await session.scalars(select(MessageState).where(MessageState.message_id.in_(message_ids)))
    return {row.message_id: to_state(row) for row in rows}


def add_state(session: AsyncSession, message_id: uuid.UUID, state: WorldState) -> None:
    """그 말 뒤의 상태를 세션에 올린다."""
    session.add(to_row(message_id, state))
