# trpg-server/app/memory/repository.py

"""지난 라운드와 그 벡터를 읽고 쓰는 쿼리. 커밋은 부르는 쪽이 한다. 모든 함수가 테이블의 id 를 받는다."""

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.models import RoundMemory
from app.rounds.models import Round


async def list_rounds_until(session: AsyncSession, table_id: uuid.UUID, last: int | None = None) -> list[Round]:
    """
    테이블의 라운드들. 번호 순이다. last 를 주면 그 번호까지만이다(선언도 함께 읽힌다).

    되돌린 라운드(#288)는 빼고 읽는다. 없었던 일이다.
    """
    query = select(Round).where(Round.table_id == table_id, Round.reverted_at.is_(None)).order_by(Round.number)
    if last is not None:
        query = query.where(Round.number <= last)
    return list(await session.scalars(query))


async def indexed_numbers(session: AsyncSession, table_id: uuid.UUID, model: str) -> set[int]:
    """이 테이블의 라운드 중 이 모델의 벡터가 이미 있는 것들의 번호."""
    query = select(RoundMemory.round_number).where(RoundMemory.table_id == table_id, RoundMemory.model == model)
    return set(await session.scalars(query))


async def add_vectors(session: AsyncSession, table_id: uuid.UUID, model: str, vectors: dict[int, list[float]]) -> None:
    """
    라운드들의 벡터를 넣는다. vectors 는 라운드의 번호에서 벡터로.

    이미 있는 것(같은 테이블, 모델, 라운드)은 건너뛴다. 두 작업이 같은 테이블을 함께 만들어도 실패하지 않는다.
    """
    if not vectors:
        return
    rows = [
        {'table_id': table_id, 'model': model, 'round_number': number, 'embedding': vector}
        for number, vector in vectors.items()
    ]
    await session.execute(insert(RoundMemory).values(rows).on_conflict_do_nothing())


async def delete_vectors_from(session: AsyncSession, table_id: uuid.UUID, number: int) -> None:
    """
    이 테이블의 number 번 라운드부터의 벡터를 모두 지운다(#288). 모든 모델의 것이다.

    라운드 N 의 기억은 N 의 선언과 N+1 의 장면이다. 되돌린 라운드 N 의 기억은 없었던 일이라 지우고,
    다시 닫은 뒤에 다음 색인이 새로 만든다. 그 앞(N-1)의 기억은 N 의 장면이 그대로라 남는다.
    """
    query = delete(RoundMemory).where(RoundMemory.table_id == table_id, RoundMemory.round_number >= number)
    await session.execute(query)


async def count_vectors(session: AsyncSession, table_id: uuid.UUID, model: str) -> int:
    """이 테이블, 이 모델의 벡터가 몇 개인가."""
    query = select(func.count()).where(RoundMemory.table_id == table_id, RoundMemory.model == model)
    return await session.scalar(query) or 0


async def memory_distances(
    session: AsyncSession, table_id: uuid.UUID, model: str, vector: list[float]
) -> dict[int, float]:
    """
    이 테이블, 이 모델의 벡터마다 vector 와의 코사인 거리. 라운드의 번호에서 거리로.

    색인 없이 테이블의 벡터를 모두 견준다. 고르는 규칙은 app/memory/retrieval.py 의 순수 함수가 정한다.
    """
    distance = RoundMemory.embedding.cosine_distance(vector)
    query = select(RoundMemory.round_number, distance).where(
        RoundMemory.table_id == table_id, RoundMemory.model == model
    )
    return {number: float(value) for number, value in await session.execute(query)}
