# trpg-server/app/references/repository.py

"""참고 자료와 그 벡터를 읽고 쓰는 쿼리. 커밋은 부르는 쪽이 한다."""

import uuid
from collections.abc import Collection, Sequence

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.references.models import ReferenceEmbedding, ReferenceEntry
from app.references.records import ReferenceRecord, ReferenceSource, StoredReference


def to_stored(entry: ReferenceEntry) -> StoredReference:
    """DB 의 줄을 넣기와 색인이 보는 모양으로."""
    return StoredReference(
        id=entry.id,
        key=entry.key,
        name=entry.name,
        aliases=list(entry.aliases),
        content=entry.content,
        kind=entry.kind,
        data=dict(entry.data),
        name_ko=entry.name_ko,
        content_ko=entry.content_ko,
    )


async def list_stored(session: AsyncSession, source: ReferenceSource) -> list[StoredReference]:
    """자료 하나의 줄 전부. key 의 차례다."""
    query = select(ReferenceEntry).where(ReferenceEntry.source == source).order_by(ReferenceEntry.key)
    return [to_stored(entry) for entry in await session.scalars(query)]


def entry_values(source: ReferenceSource, record: ReferenceRecord) -> dict:
    """파일의 줄을 테이블의 칸으로."""
    return {
        'source': source,
        'key': record.key,
        'kind': record.kind,
        'name': record.name,
        'aliases': list(record.aliases),
        'content': record.content,
        'data': record.data,
        'name_ko': record.name_ko,
        'content_ko': record.content_ko,
    }


async def add_entries(session: AsyncSession, source: ReferenceSource, records: Sequence[ReferenceRecord]) -> None:
    """줄들을 더한다."""
    if records:
        await session.execute(insert(ReferenceEntry).values([entry_values(source, record) for record in records]))


async def update_entries(session: AsyncSession, source: ReferenceSource, records: Sequence[ReferenceRecord]) -> None:
    """줄들을 파일의 값으로 고친다. 자료와 key 로 찾는다. id 는 그대로다."""
    for record in records:
        statement = (
            update(ReferenceEntry)
            .where(ReferenceEntry.source == source, ReferenceEntry.key == record.key)
            .values(entry_values(source, record))
        )
        await session.execute(statement)


async def delete_entries(session: AsyncSession, ids: Collection[uuid.UUID]) -> None:
    """줄들을 지운다. 그 줄들의 벡터도 함께 지워진다(외래 키의 CASCADE)."""
    if ids:
        await session.execute(delete(ReferenceEntry).where(ReferenceEntry.id.in_(ids)))


async def delete_embeddings(session: AsyncSession, source: ReferenceSource, keys: Collection[str]) -> None:
    """자료의 그 key 들의 벡터를 모든 모델에서 지운다. 글이 바뀐 줄이다."""
    if not keys:
        return
    ids = select(ReferenceEntry.id).where(ReferenceEntry.source == source, ReferenceEntry.key.in_(keys))
    await session.execute(delete(ReferenceEmbedding).where(ReferenceEmbedding.reference_id.in_(ids)))


def without_vector(model: str):
    """이 모델의 벡터가 아직 없는 줄이라는 조건."""
    has_vector = exists().where(ReferenceEmbedding.reference_id == ReferenceEntry.id, ReferenceEmbedding.model == model)
    return ~has_vector


async def list_missing(session: AsyncSession, model: str) -> list[StoredReference]:
    """이 모델의 벡터가 아직 없는 줄들. 자료와 key 의 차례다."""
    query = select(ReferenceEntry).where(without_vector(model)).order_by(ReferenceEntry.source, ReferenceEntry.key)
    return [to_stored(entry) for entry in await session.scalars(query)]


async def add_embeddings(session: AsyncSession, model: str, vectors: dict[uuid.UUID, list[float]]) -> None:
    """
    줄들의 벡터를 넣는다. vectors 는 줄의 id 에서 벡터로.

    이미 있는 것(같은 모델, 같은 줄)은 건너뛴다. 두 작업이 함께 만들어도 실패하지 않는다.
    그 사이 지워진 줄(다시 넣기가 지운 것)의 벡터는 외래 키가 막는다. 넣기와 색인을 함께 돌리지 않는다(README).
    """
    if not vectors:
        return
    rows = [
        {'reference_id': reference_id, 'model': model, 'embedding': vector} for reference_id, vector in vectors.items()
    ]
    await session.execute(insert(ReferenceEmbedding).values(rows).on_conflict_do_nothing())


async def list_aliased(session: AsyncSession) -> list[StoredReference]:
    """다른 이름(한국어 이름 등)이 있는 줄들. 장면의 글에 그 이름이 나왔는지 볼 때 쓴다. 자료와 key 의 차례다."""
    query = (
        select(ReferenceEntry)
        .where(func.cardinality(ReferenceEntry.aliases) > 0)
        .order_by(ReferenceEntry.source, ReferenceEntry.key)
    )
    return [to_stored(entry) for entry in await session.scalars(query)]


async def nearest(
    session: AsyncSession, model: str, vector: list[float], max_distance: float, limit: int
) -> list[tuple[StoredReference, float]]:
    """
    이 모델의 벡터 중 vector 와 가까운 줄들과 그 거리. 거리가 max_distance 이하인 것, 가까운 순으로 limit 개까지.

    거리는 코사인 거리다. 색인 없이 이 모델의 벡터를 모두 견준다(자료가 천 줄 안쪽이다).
    """
    distance = ReferenceEmbedding.embedding.cosine_distance(vector)
    query = (
        select(ReferenceEntry, distance)
        .join(ReferenceEmbedding, ReferenceEmbedding.reference_id == ReferenceEntry.id)
        .where(ReferenceEmbedding.model == model, distance <= max_distance)
        .order_by(distance)
        .limit(limit)
    )
    return [(to_stored(entry), float(value)) for entry, value in await session.execute(query)]


async def distances_of(
    session: AsyncSession, model: str, vector: list[float], ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, float]:
    """그 줄들의 이 모델의 벡터와 vector 의 거리. 벡터가 없는 줄은 빠진다."""
    if not ids:
        return {}
    distance = ReferenceEmbedding.embedding.cosine_distance(vector)
    query = select(ReferenceEmbedding.reference_id, distance).where(
        ReferenceEmbedding.model == model, ReferenceEmbedding.reference_id.in_(ids)
    )
    return {reference_id: float(value) for reference_id, value in await session.execute(query)}
