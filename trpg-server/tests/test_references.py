# trpg-server/tests/test_references.py

"""
참고 자료를 DB 에 넣는 것(app/references/loading.py)과 벡터로 바꾸는 것(app/references/indexing.py),
관리 명령(scripts/references.py)을 검증한다. 테스트의 DB 를 쓴다. 임베딩 모델은 가짜다.

보는 것.
  - 넣기: 처음에는 다 더한다. 같은 파일을 다시 넣으면 아무것도 바꾸지 않는다.
    글이 바뀐 줄은 고치고(id 그대로) 벡터를 지운다. 수치만 바뀐 줄의 벡터는 그대로다. 파일에서 빠진 줄은 지운다(벡터도).
    다른 자료의 줄은 건드리지 않는다.
  - 색인: 벡터가 없는 줄만 만든다. 다 있으면 모델을 부르지 않는다. 모델마다 따로다.
    모델이 실패하면 앞의 묶음은 남고, 다시 돌리면 남은 것부터 만든다.
  - 저장소의 SRD 파일이 DB 의 제약 안에 들어간다.
  - 관리 명령: 찍는 글과 끝낼 번호(남은 벡터가 있으면 1).
"""

import uuid
from dataclasses import dataclass, field
from typing import ClassVar

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.fake import FakeEmbedder, word_vector
from app.ai.provider import ProviderError
from app.references import repository
from app.references.indexing import IndexResult, index_references
from app.references.loading import load_document
from app.references.models import ReferenceEmbedding, ReferenceEntry
from app.references.records import (
    ReferenceDocument,
    ReferenceKind,
    ReferenceOrigin,
    ReferenceRecord,
    ReferenceSource,
    read_document,
    write_document,
)
from scripts import references as script
from tests.test_srd_references import DATA_FILE

pytestmark = pytest.mark.usefixtures('clean_tables')

OTHER_MODEL = 'other-embedding'


def entry(number: int, **values) -> ReferenceRecord:
    defaults = {'kind': ReferenceKind.ITEM, 'name': f'Item {number}', 'content': f'Thing number {number}.'}
    return ReferenceRecord(key=f'items/{number}', **{**defaults, **values})


def document(records: list[ReferenceRecord]) -> ReferenceDocument:
    origin = ReferenceOrigin(dataset='test', revision='abc', license='CC-BY-4.0', attribution='SRD 5.1')
    return ReferenceDocument(format=1, source=ReferenceSource.SRD51, origin=origin, entries=records)


def factory_of(app: FastAPI) -> async_sessionmaker[AsyncSession]:
    return app.state.session_factory


async def ids_by_key(session: AsyncSession) -> dict[str, uuid.UUID]:
    rows = await session.execute(select(ReferenceEntry.key, ReferenceEntry.id))
    return dict(rows.all())


async def vectors_of(session: AsyncSession, model: str) -> set[uuid.UUID]:
    query = select(ReferenceEmbedding.reference_id).where(ReferenceEmbedding.model == model)
    return set(await session.scalars(query))


@dataclass
class BreakingEmbedder:
    """calls 번째 부름부터 실패하는 임베더. 앞의 묶음만 성공한다."""

    kind: ClassVar[str] = 'fake'
    model: str = 'breaking'
    succeed: int = 1
    calls: list[list[str]] = field(default_factory=list)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if len(self.calls) > self.succeed:
            raise ProviderError('timeout')
        return [word_vector(text) for text in texts]


# --- 넣기 ---


async def test_loading_adds_everything_once(session: AsyncSession):
    first = await load_document(session, document([entry(1), entry(2)]))
    again = await load_document(session, document([entry(1), entry(2)]))

    assert (len(first.added), first.updated, first.removed) == (2, [], [])
    assert not again.changed
    stored = await repository.list_stored(session, ReferenceSource.SRD51)
    assert [(item.key, item.name, item.content) for item in stored] == [
        ('items/1', 'Item 1', 'Thing number 1.'),
        ('items/2', 'Item 2', 'Thing number 2.'),
    ]


async def test_a_reworded_entry_loses_its_vectors_but_keeps_its_id(app: FastAPI, session: AsyncSession):
    await load_document(session, document([entry(1), entry(2), entry(3)]))
    await index_references(factory_of(app), FakeEmbedder())
    before = await ids_by_key(session)

    plan = await load_document(
        session,
        document([entry(1, content='A new story.'), entry(2, aliases=['횃불']), entry(3, data={'weight': 1})]),
    )

    assert [record.key for record in plan.updated] == ['items/1', 'items/2', 'items/3']
    # 글(이름, 다른 이름, 내용)이 바뀐 줄만 벡터를 다시 만든다. 수치만 바뀐 줄은 그대로다
    assert plan.reworded == {'items/1', 'items/2'}
    assert await ids_by_key(session) == before
    assert await vectors_of(session, FakeEmbedder().model) == {before['items/3']}
    (third,) = [item for item in await repository.list_stored(session, ReferenceSource.SRD51) if item.key == 'items/3']
    assert third.data == {'weight': 1}


async def test_entries_left_out_of_the_file_are_removed_with_their_vectors(app: FastAPI, session: AsyncSession):
    await load_document(session, document([entry(1), entry(2)]))
    await index_references(factory_of(app), FakeEmbedder())

    plan = await load_document(session, document([entry(2)]))

    assert [item.key for item in plan.removed] == ['items/1']
    assert list(await ids_by_key(session)) == ['items/2']
    assert await session.scalar(select(func.count()).select_from(ReferenceEmbedding)) == 1


async def test_the_srd_file_fits_the_database(app: FastAPI, session: AsyncSession):
    shipped = read_document(DATA_FILE)

    plan = await load_document(session, shipped)
    result = await index_references(factory_of(app), FakeEmbedder())

    assert len(plan.added) == len(shipped.entries)
    assert result == IndexResult(added=len(shipped.entries), left=0)


# --- 색인 ---


async def test_indexing_makes_only_missing_vectors_per_model(app: FastAPI, session: AsyncSession):
    await load_document(session, document([entry(1), entry(2)]))
    embedder = FakeEmbedder()

    first = await index_references(factory_of(app), embedder)
    again = await index_references(factory_of(app), embedder)
    other = await index_references(factory_of(app), FakeEmbedder(model=OTHER_MODEL))

    assert (first, again, other) == (IndexResult(2, 0), IndexResult(0, 0), IndexResult(2, 0))
    # 다 있으면 모델을 부르지 않는다. 벡터로 바꾸는 글은 이름과 내용이 한 줄씩이다
    assert embedder.calls == [['Item 1\nThing number 1.', 'Item 2\nThing number 2.']]
    assert len(await vectors_of(session, OTHER_MODEL)) == 2


async def test_a_failing_model_keeps_the_batches_before_it(app: FastAPI, session: AsyncSession):
    await load_document(session, document([entry(number) for number in range(40)]))

    broken = await index_references(factory_of(app), BreakingEmbedder(succeed=1))
    resumed = await index_references(factory_of(app), BreakingEmbedder(succeed=1))

    # 32 개씩 부른다. 첫 묶음은 남고, 다시 돌리면 남은 8 개부터 만든다
    assert broken == IndexResult(added=32, left=8)
    assert resumed == IndexResult(added=8, left=0)


# --- 관리 명령 ---


def test_the_commands_are_read():
    assert script.build_parser().parse_args(['load', 'data/references/srd51.json']).command == 'load'
    assert script.build_parser().parse_args(['index', '--model', 'bge-m3']).model == 'bge-m3'


async def test_the_commands_report_what_they_did(app: FastAPI, tmp_path):
    path = tmp_path / 'refs.json'
    write_document(document([entry(1)]), path)

    loaded = await script.load(factory_of(app), path)
    reloaded = await script.load(factory_of(app), path)
    indexed = await script.index(factory_of(app), FakeEmbedder())

    assert loaded == (script.DONE, ['srd51: 더함 1, 고침 0(벡터를 다시 만들 것 0), 지움 0'])
    assert reloaded == (script.DONE, ['srd51: 바뀐 것이 없다'])
    assert indexed == (script.DONE, [f'모델 {FakeEmbedder().model}: 벡터 1개를 새로 만들었다'])


async def test_the_index_command_ends_with_one_when_vectors_are_left(app: FastAPI, tmp_path):
    path = tmp_path / 'refs.json'
    write_document(document([entry(1)]), path)
    await script.load(factory_of(app), path)

    code, (line,) = await script.index(factory_of(app), FakeEmbedder(error='timeout'))

    assert code == script.UNFINISHED
    assert line.startswith('모델 fake') and '1개가 남았다' in line
