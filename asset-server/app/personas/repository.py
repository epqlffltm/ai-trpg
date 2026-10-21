# asset-server/app/personas/repository.py

"""
계정 페르소나를 DB 에서 읽고 쓴다. 커밋하지 않는다. 언제 커밋할지는 서비스가 안다.

모든 함수가 주인의 ID 를 받는다. 페르소나의 ID 만으로 남의 페르소나를 건드리는 길이 없다.
"""

import uuid

from sqlalchemy import delete as delete_rows
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.personas.models import Persona


async def lock_owner(session: AsyncSession, owner_id: uuid.UUID) -> None:
    """
    이 사람의 페르소나들을 이 트랜잭션이 끝날 때까지 혼자 쓰게 잠근다. 세거나 기본을 바꾸기 전에 부른다.

    잠글 행이 없을 수 있다(처음 만들 때). 테이블 전체를 잠그면 남의 것까지 멈춘다.
    그래서 행이 아니라 "이 사람"이라는 이름에 거는 잠금(advisory lock)을 쓴다. 트랜잭션이 끝나면 저절로 풀린다.
    이름은 숫자여야 해서 주인의 ID 를 숫자로 바꾼다(hashtext). 다른 사람과 숫자가 겹치면 잠깐 서로 기다릴 뿐이다.
    TRPG 의 보관함(trpg-server 의 app/personas/repository.py)과 같은 방법이다.
    """
    await session.execute(text('SELECT pg_advisory_xact_lock(hashtext(:owner))'), {'owner': str(owner_id)})


async def count_owned(session: AsyncSession, owner_id: uuid.UUID) -> int:
    """이 사람의 페르소나가 몇 개인지 센다."""
    query = select(func.count()).select_from(Persona).where(Persona.owner_id == owner_id)
    return await session.scalar(query) or 0


async def list_owned(session: AsyncSession, owner_id: uuid.UUID) -> list[Persona]:
    """이 사람의 페르소나 전부. 기본이 먼저, 그다음 만든 차례다. 상한(50)이 있어 쪽을 나누지 않는다."""
    query = (
        select(Persona)
        .where(Persona.owner_id == owner_id)
        .order_by(Persona.is_default.desc(), Persona.created_at, Persona.id)
    )
    return list(await session.scalars(query))


async def find_owned(
    session: AsyncSession, owner_id: uuid.UUID, persona_id: uuid.UUID, for_update: bool = False
) -> Persona | None:
    """
    이 사람의 페르소나 하나. 없거나 남의 것이면 None.

    for_update 면 행을 잠근다. 고치는 두 요청이 같은 revision 을 읽고 둘 다 하나만 올리는 일을 막는다.
    """
    query = select(Persona).where(Persona.id == persona_id, Persona.owner_id == owner_id)
    if for_update:
        query = query.with_for_update()
    return await session.scalar(query)


async def oldest_owned(session: AsyncSession, owner_id: uuid.UUID) -> Persona | None:
    """이 사람의 가장 먼저 만든 페르소나. 없으면 None."""
    query = select(Persona).where(Persona.owner_id == owner_id).order_by(Persona.created_at, Persona.id).limit(1)
    return await session.scalar(query)


def add(session: AsyncSession, persona: Persona) -> None:
    """새 페르소나를 세션에 올린다."""
    session.add(persona)


async def clear_default(session: AsyncSession, owner_id: uuid.UUID) -> None:
    """이 사람의 기본을 모두 내린다. 새 기본을 올리기 전에 부른다(한 사람에 기본은 하나다)."""
    statement = update(Persona).where(Persona.owner_id == owner_id, Persona.is_default).values(is_default=False)
    await session.execute(statement)


async def delete(session: AsyncSession, persona: Persona) -> None:
    """페르소나의 행을 지운다."""
    await session.delete(persona)


async def delete_all_owned(session: AsyncSession, owner_id: uuid.UUID) -> int:
    """이 사람의 페르소나를 모두 지운다(탈퇴). 지운 수를 돌려준다."""
    result = await session.execute(delete_rows(Persona).where(Persona.owner_id == owner_id))
    return result.rowcount
