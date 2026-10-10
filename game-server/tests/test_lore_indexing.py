# game-server/tests/test_lore_indexing.py

"""
게시한 판의 로어북 항목을 벡터로 바꿔 저장하는 것(app/lore/)을 검증한다. 임베딩 모델은 가짜다.

보는 것은 넷이다.
  - 항목을 벡터로 바꿀 글(이름, 키워드, 내용)과, 판에서 항목을 고르는 순수한 함수들.
  - 색인은 없는 것만 만들고, 여러 번 돌려도 같다. 모델마다 따로 만든다.
  - 모델이 실패하면 거기서 멈추고, 앞에서 만든 것은 남는다. 게시는 성공한다.
  - 게시하면 뒤에서 색인이 돌고, 저장한 벡터로 가까운 항목을 찾을 수 있다(pgvector).
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.fake import FakeEmbedder, word_vector
from app.ai.provider import ProviderError
from app.assets.models import ScenarioVersion
from app.assets.scenarios.router import get_indexer
from app.assets.scenarios.snapshot import EntrySnapshot, LorebookSnapshot, read_snapshot
from app.lore import indexing, repository, texts
from app.lore.models import LoreEmbedding
from app.lore.texts import batched, entry_text, missing_entries, version_entries
from app.main import API_PREFIX
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')

# 테스트에 쓰는 예시. 공개 저장소에 올라가도 되는 개그 설정이다
ENTRIES = [
    {'name': '엘프 폭주족', 'keywords': ['폭주족', '바이크'], 'content': '은하에서 가장 빠른 바이크를 탄다.'},
    {'name': '드워프', 'keywords': ['망치'], 'content': '톨게이트 차단기를 망치로 부순다.'},
    {'name': '악역영애', 'keywords': [], 'content': '금빛 리무진을 탄다. 부채를 접으며 웃는다.'},
]


def make_entry(name: str = '드워프', keywords: list[str] | None = None, content: str = '') -> EntrySnapshot:
    return EntrySnapshot(id=uuid.uuid4(), name=name, keywords=keywords or [], content=content)


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(ME)))
    return {'Authorization': f'Bearer {token}'}


async def publish_with_lore(client: AsyncClient, me: dict[str, str], entries: list[dict] = ENTRIES) -> uuid.UUID:
    """로어북 하나(항목 entries)를 붙인 시나리오를 게시하고 판의 id 를 돌려준다."""
    rulebook = (await client.post(f'{API_PREFIX}/rulebooks', json={'title': '룰북'}, headers=me)).json()
    lorebook = (await client.post(f'{API_PREFIX}/lorebooks', json={'title': '인명사전'}, headers=me)).json()
    for entry in entries:
        await client.post(f'{API_PREFIX}/lorebooks/{lorebook["id"]}/entries', json=entry, headers=me)
    body = {
        'title': '열일곱 행성 추격전',
        'rulebook_id': rulebook['id'],
        'lorebook_ids': [lorebook['id']],
        'openings': ['사이렌이 울린다.'],
        'default_sheet': SHEET,
    }
    scenario = (await client.post(f'{API_PREFIX}/scenarios', json=body, headers=me)).json()
    version = await client.post(f'{API_PREFIX}/scenarios/{scenario["id"]}/versions', json={}, headers=me)
    assert version.status_code == status.HTTP_201_CREATED, version.text
    return uuid.UUID(version.json()['id'])


async def stored(session: AsyncSession, version_id: uuid.UUID) -> list[LoreEmbedding]:
    """이 판의 벡터들. 저장된 것을 다시 읽는다."""
    session.expire_all()
    query = select(LoreEmbedding).where(LoreEmbedding.version_id == version_id)
    return list(await session.scalars(query))


# --- 글과 고르기 ---


def test_an_entry_becomes_its_name_keywords_and_content():
    entry = make_entry('드워프', ['망치', '톨게이트'], '차단기를 부순다.')

    assert entry_text(entry) == '드워프\n키워드: 망치, 톨게이트\n차단기를 부순다.'


def test_missing_parts_leave_no_empty_lines():
    assert entry_text(make_entry('악역영애')) == '악역영애'


def test_every_entry_of_every_lorebook_is_taken_in_order():
    first, second, third = make_entry('가'), make_entry('나'), make_entry('다')
    lorebooks = [
        LorebookSnapshot(id=uuid.uuid4(), title='하나', entries=[first, second]),
        LorebookSnapshot(id=uuid.uuid4(), title='둘', entries=[third]),
    ]

    @dataclass
    class Snapshot:
        lorebooks: list[LorebookSnapshot]

    assert version_entries(Snapshot(lorebooks)) == [first, second, third]


def test_only_entries_without_a_vector_are_missing():
    done, todo = make_entry('가'), make_entry('나')

    assert missing_entries([done, todo], {done.id}) == [todo]


@pytest.mark.parametrize(('count', 'sizes'), [(0, []), (3, [3]), (32, [32]), (33, [32, 1]), (70, [32, 32, 6])])
def test_entries_are_sent_in_batches(count: int, sizes: list[int]):
    assert [len(batch) for batch in batched(list(range(count)))] == sizes


# --- 색인 ---


async def test_every_entry_gets_a_vector(client: AsyncClient, me: dict, app: FastAPI, session: AsyncSession):
    version_id = await publish_with_lore(client, me)
    await app.state.jobs.drain()
    embedder = FakeEmbedder()

    # 게시할 때 이미 돌았다. 다시 돌려도 새로 만들 것이 없다
    assert await indexing.index_version(app.state.session_factory, embedder, version_id) == 0
    assert embedder.calls == []

    rows = await stored(session, version_id)
    assert len(rows) == len(ENTRIES)
    assert {row.model for row in rows} == {'fake'}


async def test_the_vector_is_that_of_the_entry_text(client: AsyncClient, me: dict, app: FastAPI, session: AsyncSession):
    version_id = await publish_with_lore(client, me, ENTRIES[:1])
    await app.state.jobs.drain()

    (row,) = await stored(session, version_id)
    text = '엘프 폭주족\n키워드: 폭주족, 바이크\n은하에서 가장 빠른 바이크를 탄다.'
    assert row.embedding == pytest.approx(word_vector(text), abs=1e-6)


async def test_only_the_missing_ones_are_made(client: AsyncClient, me: dict, app: FastAPI, session: AsyncSession):
    version_id = await publish_with_lore(client, me)
    await app.state.jobs.drain()
    rows = await stored(session, version_id)
    await session.delete(rows[0])
    await session.commit()
    embedder = FakeEmbedder()

    added = await indexing.index_version(app.state.session_factory, embedder, version_id)

    assert added == 1
    assert len(embedder.calls) == 1
    assert len(embedder.calls[0]) == 1
    assert len(await stored(session, version_id)) == len(ENTRIES)


async def test_each_model_gets_its_own_vectors(client: AsyncClient, me: dict, app: FastAPI, session: AsyncSession):
    version_id = await publish_with_lore(client, me)
    await app.state.jobs.drain()

    # 모델이 다르면 벡터의 공간이 다르다. 모델을 바꾸면 그 모델의 것을 새로 만든다
    added = await indexing.index_version(app.state.session_factory, FakeEmbedder(model='bge-m3'), version_id)

    assert added == len(ENTRIES)
    rows = await stored(session, version_id)
    assert sorted(row.model for row in rows) == ['bge-m3'] * len(ENTRIES) + ['fake'] * len(ENTRIES)


@dataclass
class CountingIndexer:
    """맡긴 판의 id 를 적어 두는 것. 색인을 실제로 돌리지 않는다."""

    scheduled: list[uuid.UUID] = field(default_factory=list)

    def schedule(self, version_id: uuid.UUID) -> None:
        self.scheduled.append(version_id)


async def test_a_version_without_lore_is_not_scheduled(client: AsyncClient, me: dict, app: FastAPI):
    counting = CountingIndexer()
    app.dependency_overrides[get_indexer] = lambda: counting

    with_lore = await publish_with_lore(client, me)
    await publish_with_lore(client, me, entries=[])

    # 항목이 없는 판은 할 일이 없다. 작업을 띄우지 않는다
    assert counting.scheduled == [with_lore]


async def test_a_version_without_lore_calls_no_model(client: AsyncClient, me: dict, app: FastAPI):
    version_id = await publish_with_lore(client, me, entries=[])
    await app.state.jobs.drain()
    embedder = FakeEmbedder()

    assert await indexing.index_version(app.state.session_factory, embedder, version_id) == 0
    assert embedder.calls == []


async def test_an_unknown_version_calls_no_model(app: FastAPI):
    embedder = FakeEmbedder()

    assert await indexing.index_version(app.state.session_factory, embedder, uuid.uuid4()) == 0
    assert embedder.calls == []


# --- 실패 ---


async def test_a_failing_model_leaves_the_version_published(
    client: AsyncClient, me: dict, app: FastAPI, session: AsyncSession, caplog: pytest.LogCaptureFixture
):
    app.state.embedder = FakeEmbedder(error='unreachable')

    with caplog.at_level(logging.WARNING):
        version_id = await publish_with_lore(client, me)
        await app.state.jobs.drain()

    # 게시는 이미 끝났다. 벡터가 없는 동안 검색은 키워드로만 찾는다
    assert await stored(session, version_id) == []
    assert 'unreachable' in caplog.text
    # 로그에는 이유만 남는다. 항목의 글(AI 만 보는 글)은 남지 않는다
    assert '은하에서 가장 빠른' not in caplog.text


@dataclass
class FailingLater:
    """처음 몇 번은 벡터를 주고 그다음부터 실패하는 임베더."""

    successes: int
    model: str = 'fake'
    inner: FakeEmbedder = field(default_factory=FakeEmbedder)
    kind = 'flaky'

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self.successes == 0:
            raise ProviderError('timeout')
        self.successes -= 1
        return await self.inner.embed(texts)


async def test_batches_made_before_a_failure_are_kept(
    client: AsyncClient, me: dict, app: FastAPI, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    app.state.embedder = FakeEmbedder(error='unreachable')
    version_id = await publish_with_lore(client, me)
    await app.state.jobs.drain()
    monkeypatch.setattr(indexing, 'batched', lambda items: texts.batched(items, 2))

    added = await indexing.index_version(app.state.session_factory, FailingLater(successes=1), version_id)

    # 첫 묶음(2개)은 저장되고, 두 번째 묶음에서 멈춘다. 다음에 남은 1개부터 만든다
    assert added == 2
    assert len(await stored(session, version_id)) == 2
    assert await indexing.index_version(app.state.session_factory, FakeEmbedder(), version_id) == 1


@dataclass
class MeetingEmbedder:
    """둘이 모두 모델을 부를 때까지 기다렸다가 답하는 임베더. 두 작업이 같은 항목을 함께 만드는 상황을 만든다."""

    barrier: asyncio.Barrier
    model: str = 'fake'
    kind = 'meeting'

    async def embed(self, texts: list[str]) -> list[list[float]]:
        await self.barrier.wait()
        return [word_vector(text) for text in texts]


async def test_two_jobs_indexing_the_same_version_do_not_clash(
    client: AsyncClient, me: dict, app: FastAPI, session: AsyncSession
):
    app.state.embedder = FakeEmbedder(error='unreachable')
    version_id = await publish_with_lore(client, me)
    await app.state.jobs.drain()
    embedder = MeetingEmbedder(asyncio.Barrier(2))

    # 둘 다 "아직 없다"고 읽은 뒤에 저장한다. 늦은 쪽이 실패하지 않고, 하나씩만 남는다
    results = await asyncio.gather(
        indexing.index_version(app.state.session_factory, embedder, version_id),
        indexing.index_version(app.state.session_factory, embedder, version_id),
    )

    assert results == [len(ENTRIES), len(ENTRIES)]
    assert len(await stored(session, version_id)) == len(ENTRIES)


# --- 게시와 검색 ---


async def test_publishing_schedules_the_indexing(client: AsyncClient, me: dict, app: FastAPI, session: AsyncSession):
    version_id = await publish_with_lore(client, me)

    # 응답은 색인을 기다리지 않는다. 뒤에서 도는 작업이 끝나면 벡터가 있다
    await app.state.jobs.drain()

    assert len(await stored(session, version_id)) == len(ENTRIES)


async def test_the_distance_to_every_entry_is_read(client: AsyncClient, me: dict, app: FastAPI, session: AsyncSession):
    version_id = await publish_with_lore(client, me)
    await app.state.jobs.drain()
    query = word_vector('드워프가 망치로 톨게이트 차단기를 내려친다')

    distances = await repository.entry_distances(session, version_id, 'fake', query)

    # 저장한 벡터로 pgvector 가 거리를 잰다. 판의 항목마다 하나씩, 낱말이 가장 많이 겹치는 항목이 가장 가깝다
    names = await entry_names(session, version_id)
    assert set(distances) == set(names)
    assert names[min(distances, key=distances.get)] == '드워프'
    assert all(0.0 <= distance <= 2.0 for distance in distances.values())


async def test_distances_are_only_for_that_model(client: AsyncClient, me: dict, app: FastAPI, session: AsyncSession):
    version_id = await publish_with_lore(client, me)
    await app.state.jobs.drain()

    assert await repository.entry_distances(session, version_id, 'bge-m3', word_vector('드워프')) == {}


async def entry_names(session: AsyncSession, version_id: uuid.UUID) -> dict[uuid.UUID, str]:
    """판의 항목 id 에서 이름으로. 판을 DB 에서 읽는다."""
    version = await session.get(ScenarioVersion, version_id)
    return {entry.id: entry.name for entry in version_entries(read_snapshot(version.snapshot))}
