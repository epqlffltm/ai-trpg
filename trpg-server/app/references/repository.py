# trpg-server/app/references/repository.py

"""참고 자료와 그 벡터를 읽고 쓰는 쿼리. 커밋은 부르는 쪽이 한다."""

import uuid
from collections.abc import Collection, Sequence

from sqlalchemy import delete, exists, select, update
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
