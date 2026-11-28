# shared/reference-core/src/reference_core/repository.py

"""
참고 자료와 그 벡터를 읽고 쓰는 쿼리. 커밋은 부르는 쪽이 한다.

tables 는 서버의 표 둘이다(reference_core/tables.py). 맨 앞에 받는다. 서버가 제 표에 한 번 묶어 두고(partial)
제 코드에서는 표를 넘기지 않고 부른다(서버의 app/references/repository.py). 모델 목록의 쿼리(catalog_core)와 같다.
벡터의 거리는 pgvector 의 코사인 거리다. PostgreSQL 에서만 돈다.
"""

import uuid
from collections.abc import Collection, Sequence
from typing import Any

from sqlalchemy import ColumnElement, and_, delete, exists, func, or_, select, true, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from reference_core.records import ReferenceKind, ReferenceRecord, ReferenceSource, StoredReference
from reference_core.tables import ReferenceTables


def to_stored(entry: Any) -> StoredReference:
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
        source=entry.source,
        look_ko=entry.look_ko,
    )


async def list_stored(tables: ReferenceTables, session: AsyncSession, source: ReferenceSource) -> list[StoredReference]:
    """자료 하나의 줄 전부. key 의 차례다."""
    query = select(tables.entry).where(tables.entry.source == source).order_by(tables.entry.key)
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
        'look_ko': record.look_ko,
    }


async def add_entries(
    tables: ReferenceTables, session: AsyncSession, source: ReferenceSource, records: Sequence[ReferenceRecord]
) -> None:
    """줄들을 더한다."""
    if records:
        await session.execute(insert(tables.entry).values([entry_values(source, record) for record in records]))


async def update_entries(
    tables: ReferenceTables, session: AsyncSession, source: ReferenceSource, records: Sequence[ReferenceRecord]
) -> None:
    """줄들을 파일의 값으로 고친다. 자료와 key 로 찾는다. id 는 그대로다."""
    for record in records:
        statement = (
            update(tables.entry)
            .where(tables.entry.source == source, tables.entry.key == record.key)
            .values(entry_values(source, record))
        )
        await session.execute(statement)


async def delete_entries(tables: ReferenceTables, session: AsyncSession, ids: Collection[uuid.UUID]) -> None:
    """줄들을 지운다. 그 줄들의 벡터도 함께 지워진다(외래 키의 CASCADE)."""
    if ids:
        await session.execute(delete(tables.entry).where(tables.entry.id.in_(ids)))


async def delete_embeddings(
    tables: ReferenceTables, session: AsyncSession, source: ReferenceSource, keys: Collection[str]
) -> None:
    """자료의 그 key 들의 벡터를 모든 모델에서 지운다. 글이 바뀐 줄이다."""
    if not keys:
        return
    ids = select(tables.entry.id).where(tables.entry.source == source, tables.entry.key.in_(keys))
    await session.execute(delete(tables.embedding).where(tables.embedding.reference_id.in_(ids)))


def without_vector(tables: ReferenceTables, model: str):
    """이 모델의 벡터가 아직 없는 줄이라는 조건."""
    has_vector = exists().where(tables.embedding.reference_id == tables.entry.id, tables.embedding.model == model)
    return ~has_vector


async def list_missing(tables: ReferenceTables, session: AsyncSession, model: str) -> list[StoredReference]:
    """이 모델의 벡터가 아직 없는 줄들. 자료와 key 의 차례다."""
    query = select(tables.entry).where(without_vector(tables, model)).order_by(tables.entry.source, tables.entry.key)
    return [to_stored(entry) for entry in await session.scalars(query)]


async def add_embeddings(
    tables: ReferenceTables, session: AsyncSession, model: str, vectors: dict[uuid.UUID, list[float]]
) -> None:
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
    await session.execute(insert(tables.embedding).values(rows).on_conflict_do_nothing())


async def list_aliased(tables: ReferenceTables, session: AsyncSession) -> list[StoredReference]:
    """다른 이름(한국어 이름 등)이 있는 줄들. 장면의 글에 그 이름이 나왔는지 볼 때 쓴다. 자료와 key 의 차례다."""
    query = (
        select(tables.entry)
        .where(func.cardinality(tables.entry.aliases) > 0)
        .order_by(tables.entry.source, tables.entry.key)
    )
    return [to_stored(entry) for entry in await session.scalars(query)]


async def nearest(
    tables: ReferenceTables, session: AsyncSession, model: str, vector: list[float], max_distance: float, limit: int
) -> list[tuple[StoredReference, float]]:
    """
    이 모델의 벡터 중 vector 와 가까운 줄들과 그 거리. 거리가 max_distance 이하인 것, 가까운 순으로 limit 개까지.

    거리는 코사인 거리다. 색인 없이 이 모델의 벡터를 모두 견준다(자료가 천 줄 안쪽이다).
    """
    distance = tables.embedding.embedding.cosine_distance(vector)
    query = (
        select(tables.entry, distance)
        .join(tables.embedding, tables.embedding.reference_id == tables.entry.id)
        .where(tables.embedding.model == model, distance <= max_distance)
        .order_by(distance)
        .limit(limit)
    )
    return [(to_stored(entry), float(value)) for entry, value in await session.execute(query)]


async def distances_of(
    tables: ReferenceTables, session: AsyncSession, model: str, vector: list[float], ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, float]:
    """그 줄들의 이 모델의 벡터와 vector 의 거리. 벡터가 없는 줄은 빠진다."""
    if not ids:
        return {}
    distance = tables.embedding.embedding.cosine_distance(vector)
    query = select(tables.embedding.reference_id, distance).where(
        tables.embedding.model == model, tables.embedding.reference_id.in_(ids)
    )
    return {reference_id: float(value) for reference_id, value in await session.execute(query)}


async def find_many(
    tables: ReferenceTables, session: AsyncSession, ids: Collection[uuid.UUID]
) -> list[StoredReference]:
    """그 id 들의 줄. 없는 id 는 빠진다. 차례는 정하지 않는다."""
    if not ids:
        return []
    query = select(tables.entry).where(tables.entry.id.in_(ids))
    return [to_stored(entry) for entry in await session.scalars(query)]


def escape_like(text: str) -> str:
    """LIKE 의 특수 글자(%, _, \\)를 글자 그대로 찾게 한다."""
    return text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def search_filter(
    tables: ReferenceTables, text: str, kind: ReferenceKind | None, sources: Collection[str]
) -> ColumnElement[bool]:
    """
    찾는 조건. 글이 비면 그 자료들의 전부다. 이름(원본, 한국어)과 다른 이름에 글이 들어 있는 줄이다.
    대소문자는 가리지 않는다.
    """
    conditions: list[ColumnElement[bool]] = [tables.entry.source.in_(sorted(sources))]
    if text:
        pattern = f'%{escape_like(text)}%'
        conditions.append(
            or_(
                tables.entry.name.ilike(pattern, escape='\\'),
                tables.entry.name_ko.ilike(pattern, escape='\\'),
                func.array_to_string(tables.entry.aliases, ' ').ilike(pattern, escape='\\'),
            )
        )
    if kind is not None:
        conditions.append(tables.entry.kind == kind)
    return and_(true(), *conditions)


async def search(
    tables: ReferenceTables,
    session: AsyncSession,
    text: str,
    kind: ReferenceKind | None,
    sources: Collection[str],
    limit: int,
    offset: int,
) -> tuple[list[StoredReference], int]:
    """
    sources 의 자료에서 이름으로 찾은 줄들의 한 쪽과 전체 개수. 보이는 이름(한국어 이름, 없으면 원본)의 차례다.

    벡터로 찾지 않는다. 제작자는 이름을 알고 고른다. 임베딩 모델이 없어도 돈다.
    차례는 글자의 코드 순(C 정렬)이다. DB 의 기본 정렬(로케일)은 서버마다 달라 영어와 한글의 앞뒤가 바뀐다.
    코드 순이면 어디서나 같다. 한글끼리는 가나다 순이고, 번역이 없는 영어 이름이 앞에 온다.
    """
    condition = search_filter(tables, text, kind, sources)
    shown = func.coalesce(func.nullif(tables.entry.name_ko, ''), tables.entry.name).collate('C')
    query = select(tables.entry).where(condition).order_by(shown, tables.entry.key).limit(limit).offset(offset)
    total = await session.scalar(select(func.count()).select_from(tables.entry).where(condition))
    return [to_stored(entry) for entry in await session.scalars(query)], total or 0


async def find_by_key(tables: ReferenceTables, session: AsyncSession, source: str, key: str) -> StoredReference | None:
    """자료와 key 로 줄 하나. 없으면 None 이다(다시 넣을 때 원본에서 빠졌다)."""
    query = select(tables.entry).where(tables.entry.source == source, tables.entry.key == key)
    entry = await session.scalar(query)
    return None if entry is None else to_stored(entry)
