# shared/reference-core/tests/test_store.py

"""
참고 자료의 표를 읽고 쓰는 것을 실제 PostgreSQL(pgvector)에서 검증한다(tests/conftest.py).

보는 것.
  - 넣기(reference_core/loading.py): 처음에는 모두 더하고, 두 번째는 아무것도 바꾸지 않는다.
    글이 바뀐 줄은 벡터를 지우고 id 는 그대로다. 수치만 바뀐 줄은 벡터를 둔다. 파일에서 빠진 줄은 지운다
  - 색인(reference_core/indexing.py): 없는 벡터만 모델마다 만든다. 모델이 실패하면 앞의 묶음은 남는다
  - 찾기(reference_core/search.py): 다른 이름과 뜻으로 고른다. 모델이 실패하면 다른 이름으로만.
    자리가 없으면 읽지 않는다
  - 쿼리(reference_core/repository.py): 이름 찾기(자료, 종류, LIKE 의 특수 글자), id 와 key 로 찾기
"""

import uuid
from dataclasses import dataclass
from typing import ClassVar, cast

import pytest
from ai_core.embedder import Embedder
from ai_core.fake import FakeEmbedder, word_vector
from ai_core.provider import ProviderError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reference_core import repository
from reference_core.indexing import batched, index_references
from reference_core.loading import load_document
from reference_core.records import (
    ReferenceDocument,
    ReferenceKind,
    ReferenceOrigin,
    ReferenceRecord,
    ReferenceSource,
)
from reference_core.search import find_references
from reference_core.selection import ReferenceThresholds
from tests.tables import TABLES, Embedding

# 거리를 넓게 둔다. 낱말 벡터(word_vector)는 겹치는 낱말이 있으면 가깝다. 다른 이름으로 걸린 줄은 거리를 보지 않는다
WIDE = ReferenceThresholds(max_distance=0.99, keyword_max_distance=1.0)


def record(key: str, **values) -> ReferenceRecord:
    defaults = {'kind': ReferenceKind.ITEM, 'name': key.title(), 'content': f'{key} 의 글'}
    return ReferenceRecord(key=key, **{**defaults, **values})


def document(*records: ReferenceRecord, source: ReferenceSource = ReferenceSource.SRD51) -> ReferenceDocument:
    origin = ReferenceOrigin(dataset='test', revision='abc', license='test', attribution='test')
    return ReferenceDocument(format=1, source=source, origin=origin, entries=list(records))


async def vector_count(session: AsyncSession, model: str) -> int:
    query = select(func.count()).select_from(Embedding).where(Embedding.model == model)
    return await session.scalar(query) or 0


@dataclass
class FailingAfter:
    """앞의 몇 번은 FakeEmbedder 처럼 답하고, 그 뒤로는 실패한다."""

    calls: int
    model: str = 'fake'
    inner: ClassVar[FakeEmbedder] = FakeEmbedder()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self.calls == 0:
            raise ProviderError('timeout')
        self.calls -= 1
        return await self.inner.embed(texts)


def test_items_are_batched():
    assert batched([1, 2, 3], size=2) == [[1, 2], [3]]
    assert batched([]) == []


async def test_loading_adds_once_then_changes_nothing(session: AsyncSession):
    first = await load_document(TABLES, session, document(record('torch'), record('rope')))
    again = await load_document(TABLES, session, document(record('torch'), record('rope')))

    assert [line.key for line in first.added] == ['torch', 'rope']
    assert not again.changed
    assert [line.key for line in await repository.list_stored(TABLES, session, ReferenceSource.SRD51)] == [
        'rope',
        'torch',
    ]


async def test_a_reworded_line_loses_its_vectors_and_a_removed_line_goes(
    session_factory: async_sessionmaker[AsyncSession], session: AsyncSession
):
    await load_document(TABLES, session, document(record('torch'), record('rope'), record('lamp')))
    await index_references(TABLES, session_factory, FakeEmbedder())
    (torch,) = [
        line for line in await repository.list_stored(TABLES, session, ReferenceSource.SRD51) if line.key == 'torch'
    ]

    plan = await load_document(
        TABLES, session, document(record('torch', content='새 글'), record('rope', data={'weight': 1}))
    )

    assert plan.reworded == {'torch'} and [line.key for line in plan.removed] == ['lamp']
    stored = {line.key: line for line in await repository.list_stored(TABLES, session, ReferenceSource.SRD51)}
    assert stored['torch'].id == torch.id and stored['rope'].data == {'weight': 1}
    missing = await repository.list_missing(TABLES, session, 'fake')
    assert [line.key for line in missing] == ['torch']


async def test_indexing_makes_only_missing_vectors_per_model(
    session_factory: async_sessionmaker[AsyncSession], session: AsyncSession
):
    await load_document(TABLES, session, document(record('torch'), record('rope')))

    first = await index_references(TABLES, session_factory, FakeEmbedder())
    again = await index_references(TABLES, session_factory, FakeEmbedder())
    other = await index_references(TABLES, session_factory, FakeEmbedder(model='other'))

    assert (first.added, again.added, other.added) == (2, 0, 2)
    assert await vector_count(session, 'fake') == 2


async def test_a_failing_model_keeps_the_batches_before_it(
    session_factory: async_sessionmaker[AsyncSession], session: AsyncSession
):
    await load_document(TABLES, session, document(*(record(f'item-{number:02}') for number in range(40))))

    result = await index_references(TABLES, session_factory, cast(Embedder, FailingAfter(calls=1)))

    assert (result.added, result.left) == (32, 8)
    assert await vector_count(session, 'fake') == 32


async def test_lines_are_found_by_alias_and_meaning(
    session_factory: async_sessionmaker[AsyncSession], session: AsyncSession
):
    galleon = record('galleon', name='Galleon', aliases=['갤리온'], content='돛대 셋 큰 배')
    castle = record('castle', name='Castle', aliases=['성채'], content='돌 성벽 탑')
    await load_document(TABLES, session, document(galleon, castle))
    await index_references(TABLES, session_factory, FakeEmbedder())

    by_alias = await find_references(TABLES, session_factory, FakeEmbedder(), '갤리온이 보인다', WIDE, room=1000)
    by_meaning = await find_references(TABLES, session_factory, FakeEmbedder(), '돌 성벽 위', WIDE, room=1000)

    assert [line.key for line in by_alias][0] == 'galleon'
    assert 'castle' in [line.key for line in by_meaning]


async def test_without_the_model_only_aliases_are_found(
    session_factory: async_sessionmaker[AsyncSession], session: AsyncSession
):
    await load_document(TABLES, session, document(record('galleon', aliases=['갤리온']), record('castle')))

    found = await find_references(
        TABLES, session_factory, FakeEmbedder(error='timeout'), '갤리온이 보인다', WIDE, room=1000
    )

    assert [line.key for line in found] == ['galleon']


async def test_no_room_reads_nothing(session_factory: async_sessionmaker[AsyncSession]):
    embedder = FailingAfter(calls=0)

    # 모델을 부르면 실패한다. 부르지 않으니 빈 목록이다
    assert await find_references(TABLES, session_factory, cast(Embedder, embedder), '아무 글', WIDE, room=0) == []


async def test_the_nearest_and_distances_use_the_model_vectors(
    session_factory: async_sessionmaker[AsyncSession], session: AsyncSession
):
    await load_document(TABLES, session, document(record('torch', content='불 타는 막대')))
    await index_references(TABLES, session_factory, FakeEmbedder())
    (torch,) = await repository.list_stored(TABLES, session, ReferenceSource.SRD51)

    vector = word_vector('불 타는 막대')
    near = await repository.nearest(TABLES, session, 'fake', vector, 0.99, 3)
    distances = await repository.distances_of(TABLES, session, 'fake', vector, [torch.id])

    assert [line.key for line, _ in near] == ['torch']
    assert set(distances) == {torch.id}
    assert await repository.distances_of(TABLES, session, 'fake', vector, []) == {}
    assert await repository.nearest(TABLES, session, 'other', vector, 0.99, 3) == []


async def test_search_by_name_kind_and_source(session: AsyncSession):
    await load_document(
        TABLES,
        session,
        document(
            record('torch', name='Torch', name_ko='횃불'),
            record('wolf', kind=ReferenceKind.MONSTER, name='Wolf', aliases=['늑대']),
            record('rope', name='Rope 50% silk'),
        ),
    )
    await load_document(TABLES, session, document(record('ko/캐럭', name='캐럭'), source=ReferenceSource.WIKIPEDIA))
    srd = [ReferenceSource.SRD51]

    everything, total = await repository.search(TABLES, session, '', None, srd, 10, 0)
    by_alias, _ = await repository.search(TABLES, session, '늑대', None, srd, 10, 0)
    monsters, _ = await repository.search(TABLES, session, '', ReferenceKind.MONSTER, srd, 10, 0)
    percent, _ = await repository.search(TABLES, session, '%', None, srd, 10, 0)
    wiki, _ = await repository.search(TABLES, session, '캐럭', None, [ReferenceSource.WIKIPEDIA], 10, 0)
    hidden, _ = await repository.search(TABLES, session, '캐럭', None, srd, 10, 0)

    assert total == 3 and [line.shown_name for line in everything] == ['Rope 50% silk', 'Wolf', '횃불']
    assert [line.key for line in by_alias] == ['wolf']
    assert [line.key for line in monsters] == ['wolf']
    assert [line.key for line in percent] == ['rope']
    assert [line.key for line in wiki] == ['ko/캐럭'] and hidden == []


async def test_lines_are_found_by_id_and_key(session: AsyncSession):
    await load_document(TABLES, session, document(record('torch')))
    (torch,) = await repository.list_stored(TABLES, session, ReferenceSource.SRD51)

    assert [line.key for line in await repository.find_many(TABLES, session, [torch.id, uuid.uuid4()])] == ['torch']
    assert await repository.find_many(TABLES, session, []) == []
    assert (await repository.find_by_key(TABLES, session, ReferenceSource.SRD51, 'torch')).id == torch.id
    assert await repository.find_by_key(TABLES, session, ReferenceSource.SRD51, 'none') is None


@pytest.mark.parametrize('model', ['fake'])
async def test_adding_no_vectors_does_nothing(session: AsyncSession, model: str):
    await repository.add_embeddings(TABLES, session, model, {})
    await repository.delete_embeddings(TABLES, session, ReferenceSource.SRD51, set())

    assert await vector_count(session, model) == 0
