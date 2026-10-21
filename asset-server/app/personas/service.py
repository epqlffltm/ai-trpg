# asset-server/app/personas/service.py

"""
계정 페르소나를 만들고, 읽고, 고치고, 지우고, 기본으로 둔다(#565).

지키는 것.
  - 주인만 보고 고친다. 남의 페르소나는 없는 것과 같다(PersonaNotFoundError, 404).
  - 한 사람의 수에 상한이 있다(설정 PERSONA_MAX_PER_OWNER, 기본 50). 세기 전에 그 사람을 잠근다.
  - 페르소나가 있으면 늘 하나가 기본이다. 처음 만든 것이 기본이 되고, 기본을 지우면 가장 먼저 만든 것이 기본이 된다.
  - 내용이 바뀔 때만 revision 이 오른다. 같은 값을 보내거나 기본으로 두는 것은 내용이 아니다.
  - 나이와 성별로 거르거나 막지 않는다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.personas import repository
from app.personas.models import Persona
from app.personas.schemas import PersonaCreate, PersonaUpdate


class PersonaNotFoundError(Exception):
    """그런 페르소나가 없다. 남의 것도 이것이다."""


class PersonaLimitError(Exception):
    """페르소나가 상한에 닿아 더 만들 수 없다. limit 은 그 상한이다."""

    def __init__(self, limit: int) -> None:
        super().__init__(limit)
        self.limit = limit


def build_persona(owner_id: uuid.UUID, data: PersonaCreate, is_default: bool) -> Persona:
    """입력에서 페르소나 객체를 만든다. 아직 저장하지 않는다."""
    return Persona(owner_id=owner_id, is_default=is_default, revision=1, **data.model_dump())


def changed_fields(persona: Persona, changes: dict) -> dict:
    """보낸 칸 중 지금 값과 다른 것만."""
    return {name: value for name, value in changes.items() if getattr(persona, name) != value}


def apply_changes(persona: Persona, changes: dict) -> bool:
    """바뀐 칸을 반영하고 revision 을 올린다. 바뀐 것이 없으면 아무것도 하지 않고 False 다."""
    changed = changed_fields(persona, changes)
    for name, value in changed.items():
        setattr(persona, name, value)
    if changed:
        persona.revision += 1
    return bool(changed)


async def get_persona(session: AsyncSession, owner_id: uuid.UUID, persona_id: uuid.UUID) -> Persona:
    """자기 페르소나 하나. 없으면 PersonaNotFoundError."""
    persona = await repository.find_owned(session, owner_id, persona_id)
    if persona is None:
        raise PersonaNotFoundError
    return persona


async def list_personas(session: AsyncSession, owner_id: uuid.UUID) -> list[Persona]:
    """자기 페르소나 전부. 기본이 먼저다."""
    return await repository.list_owned(session, owner_id)


async def create_persona(session: AsyncSession, owner_id: uuid.UUID, data: PersonaCreate, limit: int) -> Persona:
    """
    페르소나를 만든다. 상한에 닿았으면 PersonaLimitError. 처음 만든 것이면 기본이다.

    세고 나서 더한다. 두 요청이 동시에 세면 둘 다 자리가 있다고 보고 상한을 넘긴다. 그래서 세기 전에 그 사람을 잠근다.
    """
    await repository.lock_owner(session, owner_id)
    count = await repository.count_owned(session, owner_id)
    if count >= limit:
        raise PersonaLimitError(limit)

    persona = build_persona(owner_id, data, is_default=count == 0)
    repository.add(session, persona)
    await session.commit()
    # 만든 시각과 고친 시각은 DB 가 정했다
    await session.refresh(persona)
    return persona


async def update_persona(
    session: AsyncSession, owner_id: uuid.UUID, persona_id: uuid.UUID, data: PersonaUpdate
) -> Persona:
    """자기 페르소나를 고친다. 바뀐 것이 있으면 revision 이 오른다. 없으면 PersonaNotFoundError."""
    persona = await repository.find_owned(session, owner_id, persona_id, for_update=True)
    if persona is None:
        raise PersonaNotFoundError
    apply_changes(persona, data.changes())
    await session.commit()
    await session.refresh(persona)
    return persona


async def make_default(session: AsyncSession, owner_id: uuid.UUID, persona_id: uuid.UUID) -> Persona:
    """
    자기 페르소나 하나를 기본으로 둔다. 다른 것은 기본에서 내린다. revision 은 그대로다. 없으면 PersonaNotFoundError.

    두 요청이 서로 다른 것을 기본으로 두려 해도 그 사람을 잠가 차례로 한다(DB 의 색인도 둘을 막는다).
    """
    await repository.lock_owner(session, owner_id)
    persona = await get_persona(session, owner_id, persona_id)
    if not persona.is_default:
        await repository.clear_default(session, owner_id)
        persona.is_default = True
    await session.commit()
    await session.refresh(persona)
    return persona


async def delete_persona(session: AsyncSession, owner_id: uuid.UUID, persona_id: uuid.UUID) -> None:
    """
    자기 페르소나를 지운다(행을 지운다). 없으면 PersonaNotFoundError.

    기본을 지웠으면 남은 것 중 가장 먼저 만든 것이 기본이 된다. 가져간 세션은 사본으로 돈다.
    """
    await repository.lock_owner(session, owner_id)
    persona = await get_persona(session, owner_id, persona_id)
    was_default = persona.is_default
    await repository.delete(session, persona)
    await session.flush()
    if was_default:
        await promote_oldest(session, owner_id)
    await session.commit()


async def promote_oldest(session: AsyncSession, owner_id: uuid.UUID) -> None:
    """남은 것 중 가장 먼저 만든 것을 기본으로 둔다. 남은 것이 없으면 아무것도 하지 않는다."""
    oldest = await repository.oldest_owned(session, owner_id)
    if oldest is not None:
        oldest.is_default = True
