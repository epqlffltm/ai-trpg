# game-server/app/personas/service.py

"""
보관함에 캐릭터를 만들고, 읽고, 고치고, 지운다.

HTTP 를 모른다. SQL 을 모른다. 어디까지를 한 묶음으로 저장할지(커밋)는 여기서 정한다.

보관함은 주인만 본다. 남의 캐릭터는 "없는 캐릭터"다(PersonaNotFoundError).
한 사람이 보관할 수 있는 수에 상한이 있다. 세기 전에 그 사람의 보관함을 잠근다(repository.lock_owner).
"""

import enum
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.personas import repository
from app.personas.models import PERSONA_MAX_PER_OWNER, Persona
from app.personas.schemas import PersonaWrite


class PersonaNotFoundError(Exception):
    """그런 캐릭터가 보관함에 없다. 남의 것을 찾은 경우도 이 예외다."""


class Conflict(enum.StrEnum):
    """요청은 맞지만 지금 상태와 부딪히는 이유."""

    # 보관함이 가득 찼다
    VAULT_FULL = 'vault_full'
    # 테이블에 아직 캐릭터가 없다. 저장할 것이 없다
    NO_CHARACTER = 'no_character'
    # 프리젠은 보관함에 저장하지 못한다. 시나리오의 제작자가 쓴 인물이다
    PREGEN_NOT_KEPT = 'pregen_not_kept'


class PersonaConflictError(Exception):
    """지금 상태와 부딪힌다. reason 이 이유다."""

    def __init__(self, reason: Conflict) -> None:
        super().__init__(reason)
        self.reason = reason


# --- 판단하고 만드는 작은 함수들. DB 를 건드리지 않는다 ---


def build_persona(owner_id: uuid.UUID, data: PersonaWrite, rulebook_title: str | None = None) -> Persona:
    """입력에서 캐릭터 객체를 만든다. 아직 저장하지 않는다."""
    return Persona(
        owner_id=owner_id,
        name=data.name,
        description=data.description,
        abilities=dict(data.abilities) if data.abilities is not None else None,
        rulebook_title=rulebook_title,
    )


def overwrite(persona: Persona, data: PersonaWrite) -> None:
    """
    캐릭터를 입력으로 통째로 바꾼다.

    룰북의 제목은 지운다. 손으로 고친 숫자는 더는 그 룰북에서 만든 숫자가 아니다.
    """
    persona.name = data.name
    persona.description = data.description
    persona.abilities = dict(data.abilities) if data.abilities is not None else None
    persona.rulebook_title = None


# --- 읽기 ---


async def get_persona(session: AsyncSession, owner_id: uuid.UUID, persona_id: uuid.UUID) -> Persona:
    """보관한 캐릭터 하나를 돌려준다. 없거나 남의 것이면 PersonaNotFoundError."""
    persona = await repository.find_owned(session, owner_id, persona_id)
    if persona is None:
        raise PersonaNotFoundError
    return persona


async def list_personas(
    session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[Persona], int]:
    """보관한 캐릭터의 한 쪽과 전체 개수를 돌려준다."""
    personas = await repository.list_owned(session, owner_id, limit, offset)
    total = await repository.count_owned(session, owner_id)
    return personas, total


# --- 바꾸기 ---


async def keep(session: AsyncSession, persona: Persona) -> Persona:
    """
    만든 캐릭터를 보관함에 넣고 저장한다. 보관함이 가득 찼으면 PersonaConflictError.

    직접 만들 때와 테이블에서 저장할 때(app/personas/saving.py)가 함께 쓴다. 상한을 지키는 곳은 여기 하나다.
    개수를 세고 나서 넣는다. 두 요청이 동시에 세면 둘 다 "아직 자리가 있다"고 보고 상한을 넘긴다.
    그래서 세기 전에 이 사람의 보관함을 잠근다. 같은 사람의 다른 요청은 이 저장이 끝날 때까지 기다린다.
    """
    await repository.lock_owner(session, persona.owner_id)
    if await repository.count_owned(session, persona.owner_id) >= PERSONA_MAX_PER_OWNER:
        raise PersonaConflictError(Conflict.VAULT_FULL)

    repository.add_persona(session, persona)
    await session.commit()
    await session.refresh(persona)
    return persona


async def create_persona(session: AsyncSession, owner_id: uuid.UUID, data: PersonaWrite) -> Persona:
    """보관함에 캐릭터를 만든다. 보관함이 가득 찼으면 PersonaConflictError."""
    return await keep(session, build_persona(owner_id, data))


async def update_persona(
    session: AsyncSession, owner_id: uuid.UUID, persona_id: uuid.UUID, data: PersonaWrite
) -> Persona:
    """
    보관한 캐릭터를 고친다. 보낸 것으로 통째로 바뀐다. 없거나 남의 것이면 PersonaNotFoundError.

    이 캐릭터를 가져간 테이블은 바뀌지 않는다. 가져갈 때 사본을 떴다.
    """
    persona = await get_persona(session, owner_id, persona_id)
    overwrite(persona, data)
    await session.commit()
    await session.refresh(persona)
    return persona


async def delete_persona(session: AsyncSession, owner_id: uuid.UUID, persona_id: uuid.UUID) -> None:
    """
    보관한 캐릭터를 지운다. 없거나 남의 것이면 PersonaNotFoundError.

    이 캐릭터를 가져간 테이블은 바뀌지 않는다. 가져갈 때 사본을 떴다.
    """
    persona = await get_persona(session, owner_id, persona_id)
    await repository.delete_persona(session, persona)
    await session.commit()
