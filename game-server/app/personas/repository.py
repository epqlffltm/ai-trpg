# game-server/app/personas/repository.py

"""
보관함을 DB 에서 읽고 쓴다. SQL 은 이 파일에만 있다. 커밋하지 않는다.

읽는 함수는 모두 주인을 조건으로 받는다. 남의 보관함을 읽는 길이 아예 없다.
"""

import uuid

from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.personas.models import Persona


def owned(owner_id: uuid.UUID) -> Select[tuple[Persona]]:
    """한 사람이 보관한 캐릭터를 고르는 조건. 읽는 함수들이 함께 쓴다."""
    return select(Persona).where(Persona.owner_id == owner_id)


async def lock_owner(session: AsyncSession, owner_id: uuid.UUID) -> None:
    """
    이 사람의 보관함을 이 트랜잭션이 끝날 때까지 혼자 쓰게 잠근다. 개수를 세고 더하기 전에 부른다.

    잠글 행이 없다. 보관함이 비어 있으면 잠글 것이 없고, 테이블 전체를 잠그면 남의 보관함까지 멈춘다.
    그래서 행이 아니라 "이 사람"이라는 이름에 거는 잠금(advisory lock)을 쓴다.
    xact: 트랜잭션이 끝나면(커밋이든 되돌리기든) 저절로 풀린다. 푸는 것을 잊을 일이 없다.

    이름은 숫자여야 해서 주인의 ID 를 숫자로 바꾼다(hashtext). 다른 사람과 숫자가 겹칠 수 있지만,
    그러면 두 사람이 잠깐 서로를 기다릴 뿐 틀린 결과가 나오지는 않는다.
    값은 묶어서 보낸다(:owner). 문장에 끼워 넣지 않는다.
    """
    await session.execute(text('SELECT pg_advisory_xact_lock(hashtext(:owner))'), {'owner': str(owner_id)})


def add_persona(session: AsyncSession, persona: Persona) -> None:
    """새 캐릭터를 세션에 올린다."""
    session.add(persona)


async def delete_persona(session: AsyncSession, persona: Persona) -> None:
    """캐릭터를 지운다. 행을 지운다."""
    await session.delete(persona)


async def find_owned(session: AsyncSession, owner_id: uuid.UUID, persona_id: uuid.UUID) -> Persona | None:
    """보관한 캐릭터 하나를 찾는다. 없거나 남의 것이면 None."""
    return await session.scalar(owned(owner_id).where(Persona.id == persona_id))


async def count_owned(session: AsyncSession, owner_id: uuid.UUID) -> int:
    """이 사람이 보관한 캐릭터의 수."""
    return await session.scalar(select(func.count()).select_from(owned(owner_id).subquery())) or 0


async def list_owned(session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int) -> list[Persona]:
    """
    이 사람이 보관한 캐릭터를 최근에 만든 것부터 돌려준다.

    만든 시각이 같은 것끼리의 순서도 정해 둔다. 정하지 않으면 쪽을 넘길 때 같은 것이 두 번 나오거나 빠진다.
    """
    query = owned(owner_id).order_by(Persona.created_at.desc(), Persona.id).limit(limit).offset(offset)
    return list(await session.scalars(query))
