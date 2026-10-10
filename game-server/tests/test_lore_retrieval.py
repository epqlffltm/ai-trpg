# game-server/tests/test_lore_retrieval.py

"""
서술하기 직전에 로어북 항목을 고르는 것(app/lore/retrieval.py)을 검증한다. 임베딩 모델은 가짜다.

가짜 임베더는 낱말이 겹치는 글끼리 가까운 벡터를 낸다(app/ai/fake.py).
뜻은 모르지만 "가까운 것을 고르는지"는 볼 수 있다.

보는 것은 넷이다.
  - 찾는 글, 키워드 일치, 글자 수 안에서 고르기, 거리 기준(순수한 함수).
  - 키워드로 고른 것이 먼저, 그다음 벡터로 가까운 것. 먼 것은 고르지 않는다. 키워드로 걸려도 멀면 넣지 않는다.

가짜 임베더의 거리는 bge-m3 와 크기가 달라서, 테스트 설정은 가짜에 맞춘 거리 기준을 쓴다(tests/conftest.py).
거리 기준 자체는 거리를 손으로 적은 순수 함수의 테스트로 본다.
  - 임베딩 모델이 실패하면 키워드로만, 벡터가 모자라면 색인을 다시 맡긴다. 서술은 막지 않는다.
  - 라운드를 닫으면 고른 항목이 프롬프트에 들어가고, 어느 항목을 넣었는지 AI 호출의 기록에 남는다.
  - 인물 항목만, 이름이 장면에 안 나왔으면 장면의 호칭으로 이름표를 바꾼다. 다른 항목의 내용 속 이름도 바꾼다(#105).
"""

import logging
import uuid
from dataclasses import dataclass, field

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.call_log import DbCallLog
from app.ai.fake import FakeEmbedder, FakeProvider, word_vector
from app.ai.models import AiInvocation
from app.assets.models import LoreKind
from app.assets.scenarios.snapshot import EntrySnapshot
from app.lore import indexing, repository
from app.lore.models import LoreEmbedding
from app.lore.retrieval import (
    LORE_MAX_CHARS,
    LoreRetriever,
    Thresholds,
    choose,
    keyword_hits,
    load_candidates,
    mentions,
    near_enough,
    nearest_within,
    pick,
    query_text,
    relabel,
    scene_label,
    scene_labels,
    to_note,
)
from app.main import API_PREFIX
from app.rounds import prompt
from app.rounds.llm_narrator import LLMNarrator
from app.rounds.narrator import Move, NarrationRequest
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')

# 테스트에 쓰는 예시. 공개 저장소에 올라가도 되는 개그 설정이다
DWARF = {'name': '드워프', 'keywords': ['망치'], 'content': '톨게이트 차단기를 내려치는 습관이 있다.'}
ELF = {'name': '엘프 폭주족', 'keywords': ['바이크'], 'content': '은하에서 가장 빠른 바이크를 탄다.'}
LADY = {'name': '악역영애', 'keywords': [], 'content': '금빛 리무진을 탄다 부채를 접으며 웃는다'}
STAR = {'name': '열일곱째 행성', 'keywords': [], 'content': '고속도로의 끝에 있는 얼음 행성이다'}
OPENING = '사이렌이 울린다.'
# 진짜 이름은 설정에만 있고, 장면에서는 호칭으로 불리는 인물과, 그 인물이 내용에 나오는 물건
VIOLETTA = {
    'name': '비올레타',
    'keywords': ['영애', '악역영애', '부채'],
    'content': '금빛 리무진을 탄다.',
    'kind': 'person',
}
LIMO = {'name': '금빛 리무진', 'keywords': ['리무진'], 'content': '비올레타의 차. 순금으로 덮여 있다.', 'kind': 'item'}


def make_entry(
    name: str, keywords: list[str] | None = None, content: str = '', kind: LoreKind = LoreKind.OTHER
) -> EntrySnapshot:
    return EntrySnapshot(id=uuid.uuid4(), name=name, keywords=keywords or [], content=content, kind=kind)


def make_request(table_id: uuid.UUID | None, scene: str = OPENING, *declarations: str) -> NarrationRequest:
    """테이블의 라운드 하나를 서술해 달라는 요청. 선언은 엘프가 한 것으로 둔다."""
    moves = [Move('엘프', content) for content in declarations] or [Move('엘프', None)]
    return NarrationRequest(round_number=1, scene=scene, moves=moves, table_id=table_id)


@dataclass
class CountingIndexer:
    """맡긴 판의 id 를 적어 두는 것. 색인을 실제로 돌리지 않는다."""

    scheduled: list[uuid.UUID] = field(default_factory=list)

    def schedule(self, version_id: uuid.UUID) -> None:
        self.scheduled.append(version_id)


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(ME)))
    return {'Authorization': f'Bearer {token}'}


async def open_table(client: AsyncClient, me: dict[str, str], entries: list[dict]) -> dict:
    """로어북 하나(항목 entries)를 붙인 시나리오를 게시하고, 그 판으로 혼자 앉는 테이블을 연다."""
    rulebook = (await client.post(f'{API_PREFIX}/rulebooks', json={'title': '룰북'}, headers=me)).json()
    lorebook = (await client.post(f'{API_PREFIX}/lorebooks', json={'title': '인명사전'}, headers=me)).json()
    for entry in entries:
        await client.post(f'{API_PREFIX}/lorebooks/{lorebook["id"]}/entries', json=entry, headers=me)
    body = {
        'title': '열일곱 행성 추격전',
        'rulebook_id': rulebook['id'],
        'lorebook_ids': [lorebook['id']],
        'openings': [OPENING],
        'default_sheet': SHEET,
    }
    scenario = (await client.post(f'{API_PREFIX}/scenarios', json=body, headers=me)).json()
    await client.post(f'{API_PREFIX}/scenarios/{scenario["id"]}/versions', json={}, headers=me)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 1}
    table = await client.post(f'{API_PREFIX}/tables', json=body, headers=me)
    assert table.status_code == status.HTTP_201_CREATED, table.text
    return table.json()


def make_retriever(
    app: FastAPI, embedder: FakeEmbedder | None = None, thresholds: Thresholds | None = None
) -> tuple[LoreRetriever, CountingIndexer]:
    """
    검색하는 것과 색인을 맡긴 기록. 거리 기준을 주지 않으면 테스트 설정의 것(가짜 임베더에 맞춘 값)이다.
    """
    indexer = CountingIndexer()
    settings = app.state.settings
    chosen = thresholds or Thresholds(settings.lore_max_distance, settings.lore_keyword_max_distance)
    return LoreRetriever(app.state.session_factory, embedder or FakeEmbedder(), indexer, chosen), indexer


def names(notes) -> list[str]:
    return [note.name for note in notes]


# --- 순수한 함수 ---


def distances_of(*pairs: tuple[EntrySnapshot, float]) -> dict[uuid.UUID, float]:
    """항목마다 거리를 손으로 적는다."""
    return {entry.id: distance for entry, distance in pairs}


def test_nearest_within_keeps_the_order_the_limit_and_the_distance():
    a, b, c, unknown = make_entry('가'), make_entry('나'), make_entry('다'), make_entry('라')
    distances = distances_of((a, 0.4), (b, 0.1), (c, 0.3))

    assert nearest_within([a, b, c, unknown], distances, 0.35, 8) == [b, c]
    assert nearest_within([a, b, c, unknown], distances, 0.45, 2) == [b, c]
    assert nearest_within([a, b, c, unknown], distances, 0.4, 8) == [b, c, a]


def test_a_keyword_hit_is_near_enough_within_the_limit_or_without_a_distance():
    near, far, unknown = make_entry('가'), make_entry('나'), make_entry('다')
    distances = distances_of((near, 0.5), (far, 0.51))

    assert near_enough(near, distances, 0.5)
    assert not near_enough(far, distances, 0.5)
    # 벡터가 없으면 거리를 모른다. 키워드를 믿는다
    assert near_enough(unknown, distances, 0.5)


def test_a_far_keyword_hit_is_left_out():
    # 계획을 망치고 → 키워드 망치. 글 전체의 뜻은 드워프와 멀다
    dwarf = make_entry('드워프', ['망치'], '톨게이트 차단기를 내려친다.')
    lady = make_entry('악역영애', [], '부채를 접으며 웃는다.')
    text = '모모: 이번 계획을 망치고 싶지 않다.'

    far = choose([dwarf, lady], text, distances_of((dwarf, 0.6), (lady, 0.9)), Thresholds(0.45, 0.5))
    near = choose([dwarf, lady], text, distances_of((dwarf, 0.4), (lady, 0.9)), Thresholds(0.45, 0.5))

    assert far == []
    assert near == [dwarf]


def test_without_distances_keyword_hits_are_all_kept():
    dwarf = make_entry('드워프', ['망치'])
    lady = make_entry('악역영애')

    # 임베딩이 실패했다. 거리를 모르니 키워드로만, 상한 없이 고른다
    assert choose([dwarf, lady], '망치를 든다', {}, Thresholds(0.45, 0.5)) == [dwarf]


def test_keyword_hits_come_before_the_nearest():
    dwarf = make_entry('드워프')
    lady = make_entry('악역영애')
    star = make_entry('열일곱째 행성')
    distances = distances_of((dwarf, 0.45), (lady, 0.1), (star, 0.3))

    assert choose([dwarf, lady, star], '드워프', distances, Thresholds(0.4, 0.5)) == [dwarf, lady, star]


def test_the_query_is_the_scene_and_the_declarations():
    request = NarrationRequest(
        round_number=1, scene='사이렌이 울린다.', moves=[Move('엘프', '달린다.'), Move('영애', None)]
    )

    # 선언하지 않은 사람은 뺀다
    assert query_text(request) == '사이렌이 울린다.\n엘프: 달린다.'


@pytest.mark.parametrize(
    'text',
    [
        '드워프가 쫓아온다.',  # 조사가 붙어도 들어 있다
        '망치를 든 누군가',  # 키워드
        'DWARF 가 온다',  # 대소문자를 가리지 않는다
    ],
)
def test_a_name_or_keyword_in_the_text_is_a_hit(text: str):
    entry = make_entry('드워프', ['망치', 'dwarf'])

    assert mentions(entry, text)


def test_an_entry_not_mentioned_is_not_a_hit():
    assert not mentions(make_entry('드워프', ['망치']), '엘프가 바이크를 탄다.')


def test_hits_keep_the_order_of_the_entries():
    first, second, third = make_entry('엘프'), make_entry('드워프'), make_entry('악역영애')

    assert keyword_hits([first, second, third], '악역영애와 엘프') == [first, third]


def test_picking_stops_at_the_character_budget_but_lets_a_shorter_one_in():
    big = make_entry('큰 항목', content='가' * 2900)
    too_big = make_entry('더 큰 항목', content='나' * 200)
    small = make_entry('작은', content='다' * 50)

    picked = pick([big, too_big, small])

    # 들어가지 않는 것은 건너뛰고, 뒤의 짧은 것은 넣는다
    assert picked == [big, small]
    assert sum(len(entry.name) + len(entry.content) for entry in picked) <= LORE_MAX_CHARS


def test_picking_takes_an_entry_once():
    entry = make_entry('드워프', content='망치')

    assert pick([entry, entry]) == [entry]


# --- 이름표 ---


def test_a_person_named_in_the_scene_keeps_the_name():
    lady = make_entry('비올레타', ['악역영애'], kind=LoreKind.PERSON)

    assert scene_label(lady, '비올레타가 악역영애처럼 웃는다') == '비올레타'
    # 대소문자는 가리지 않는다
    assert scene_label(make_entry('Rien', ['Elf'], kind=LoreKind.PERSON), 'rien the elf') == 'Rien'


def test_a_person_not_named_is_called_by_the_longest_keyword_in_the_scene():
    lady = make_entry('비올레타', ['영애', '악역영애', '부채'], kind=LoreKind.PERSON)

    # "영애"도 나왔지만 "악역영애"가 장면의 호칭에 더 가깝다. 장면에 없는 키워드(부채)는 쓰지 않는다
    assert scene_label(lady, '악역영애가 웃는다') == '악역영애'
    # 대소문자는 가리지 않는다
    assert scene_label(make_entry('Rien', ['Elf'], kind=LoreKind.PERSON), 'an elf rides') == 'Elf'


def test_a_person_not_in_the_scene_at_all_keeps_the_name():
    lady = make_entry('비올레타', ['악역영애'], kind=LoreKind.PERSON)

    assert scene_label(lady, '사이렌이 울린다') == '비올레타'


def test_only_people_get_a_new_label():
    lady = make_entry('비올레타', ['악역영애'], kind=LoreKind.PERSON)
    named = make_entry('토르빈', ['드워프'], kind=LoreKind.PERSON)
    limo = make_entry('금빛 리무진', ['리무진'], kind=LoreKind.ITEM)
    other = make_entry('사이렌 대소동', ['사이렌'])

    labels = scene_labels([lady, named, limo, other], '악역영애가 리무진에서 내리자 토르빈이 사이렌을 울린다')

    # 장소나 물건의 이름은 세계의 고유명사라 그대로 둔다. 이름이 이미 나온 인물도 그대로다
    assert labels == {'비올레타': '악역영애'}


def test_relabel_replaces_longer_names_first():
    labels = {'그레고르': '콧수염', '그레고르 경감': '경감'}

    # 짧은 이름부터 바꾸면 "그레고르 경감"이 "콧수염 경감"이 된다
    assert relabel('그레고르 경감은 그레고르를 닮았다', labels) == '경감은 콧수염를 닮았다'


def test_a_note_carries_the_label_the_kind_and_the_same_id():
    lady = make_entry('비올레타', ['악역영애'], '부채를 접는다', kind=LoreKind.PERSON)
    limo = make_entry('금빛 리무진', ['리무진'], '비올레타의 차', kind=LoreKind.ITEM)
    labels = {'비올레타': '악역영애'}

    lady_note, limo_note = to_note(lady, labels), to_note(limo, labels)

    assert (lady_note.name, lady_note.content, lady_note.kind) == ('악역영애', '부채를 접는다', LoreKind.PERSON)
    # 다른 항목의 내용에 나오는 진짜 이름도 바꾼다. 항목의 id 는 그대로라 기록에는 어느 항목인지 남는다
    assert (limo_note.name, limo_note.content, limo_note.kind) == ('금빛 리무진', '악역영애의 차', LoreKind.ITEM)
    assert limo_note.entry_id == limo.id
    assert to_note(limo).content == '비올레타의 차'


# --- 고르기 ---


async def test_a_mentioned_entry_comes_first(client: AsyncClient, me: dict, app: FastAPI):
    table = await open_table(client, me, [ELF, DWARF])
    await app.state.jobs.drain()
    retriever, _ = make_retriever(app)

    notes = await retriever.find(make_request(uuid.UUID(table['id']), OPENING, '드워프를 따돌린다'))

    assert names(notes)[0] == '드워프'


async def test_a_mentioned_entry_goes_before_a_closer_one(client: AsyncClient, me: dict, app: FastAPI):
    table = await open_table(client, me, [DWARF, LADY])
    await app.state.jobs.drain()
    retriever, _ = make_retriever(app)

    # 장면은 악역영애의 내용과 거의 같지만, 선언에 드워프의 이름이 나온다. 이름이 나온 것을 먼저 넣는다
    request = make_request(uuid.UUID(table['id']), LADY['content'], '드워프')

    assert names(await retriever.find(request)) == ['드워프', '악역영애']


async def test_the_server_calls_a_person_by_the_name_in_the_scene(client: AsyncClient, me: dict, app: FastAPI):
    table = await open_table(client, me, [VIOLETTA, LIMO])
    await app.state.jobs.drain()
    retriever, _ = make_retriever(app)

    notes = await retriever.find(make_request(uuid.UUID(table['id']), '악역영애가 리무진에서 부채를 접는다.'))

    by_id = {note.entry_id: note for note in notes}
    lady, limo = by_id[await entry_id(app, table, '비올레타')], by_id[await entry_id(app, table, '금빛 리무진')]
    # 플레이어가 아직 모르는 진짜 이름은 서술자에게 가지 않는다
    assert (lady.name, lady.kind) == ('악역영애', LoreKind.PERSON)
    assert all('비올레타' not in f'{note.name} {note.content}' for note in notes)
    # 물건은 장면에 키워드만 나왔어도 이름 그대로다
    assert (limo.name, limo.content, limo.kind) == ('금빛 리무진', '악역영애의 차. 순금으로 덮여 있다.', LoreKind.ITEM)


async def test_an_entry_close_in_meaning_is_found_without_its_name(client: AsyncClient, me: dict, app: FastAPI):
    table = await open_table(client, me, [DWARF, LADY, STAR])
    await app.state.jobs.drain()
    retriever, _ = make_retriever(app)

    # 이름도 키워드도 없지만, 항목의 내용과 낱말이 겹친다
    notes = await retriever.find(make_request(uuid.UUID(table['id']), '금빛 리무진을 탄다'))

    assert names(notes) == ['악역영애']


async def test_the_server_leaves_out_a_keyword_hit_beyond_the_limit(client: AsyncClient, me: dict, app: FastAPI):
    table = await open_table(client, me, [DWARF, ELF])
    await app.state.jobs.drain()
    strict = Thresholds(max_distance=0.0, keyword_max_distance=0.0)
    retriever, _ = make_retriever(app, thresholds=strict)

    # 드워프의 이름이 나왔지만 글 전체와의 거리가 상한(0)보다 멀다
    assert await retriever.find(make_request(uuid.UUID(table['id']), OPENING, '드워프를 따돌린다')) == []


async def test_a_keyword_hit_without_a_vector_is_kept(
    client: AsyncClient, me: dict, app: FastAPI, session: AsyncSession
):
    table = await open_table(client, me, [DWARF, ELF])
    await app.state.jobs.drain()
    # 판의 벡터가 없다(게시 직후의 색인이 실패한 판)
    await session.execute(delete(LoreEmbedding))
    await session.commit()
    strict = Thresholds(max_distance=0.0, keyword_max_distance=0.0)
    retriever, indexer = make_retriever(app, thresholds=strict)

    notes = await retriever.find(make_request(uuid.UUID(table['id']), OPENING, '드워프를 따돌린다'))

    assert names(notes) == ['드워프']
    assert indexer.scheduled


async def test_when_the_embedder_fails_keyword_hits_skip_the_limit(client: AsyncClient, me: dict, app: FastAPI):
    table = await open_table(client, me, [DWARF, ELF])
    await app.state.jobs.drain()
    strict = Thresholds(max_distance=0.0, keyword_max_distance=0.0)
    retriever, _ = make_retriever(app, FakeEmbedder(error='unreachable'), strict)

    notes = await retriever.find(make_request(uuid.UUID(table['id']), OPENING, '드워프를 따돌린다'))

    assert names(notes) == ['드워프']


async def test_the_app_uses_the_distances_in_the_settings(app: FastAPI):
    settings = app.state.settings

    assert app.state.lore.thresholds == Thresholds(settings.lore_max_distance, settings.lore_keyword_max_distance)


async def test_a_far_entry_is_not_picked(client: AsyncClient, me: dict, app: FastAPI):
    table = await open_table(client, me, [DWARF, STAR])
    await app.state.jobs.drain()
    retriever, _ = make_retriever(app)

    # 겹치는 낱말이 없으면 멀다. 관련 없는 것까지 넣지 않는다
    assert await retriever.find(make_request(uuid.UUID(table['id']), '아무 상관 없는 이야기')) == []


async def test_vectors_of_entries_not_in_the_copy_are_dropped(
    client: AsyncClient, me: dict, app: FastAPI, session: AsyncSession
):
    table = await open_table(client, me, [DWARF])
    await app.state.jobs.drain()
    query = '금빛 리무진을 탄다'
    # 복사본에 없는 항목의 벡터(찾는 글과 똑같다). 벡터만 있고 글이 없으면 넣을 수 없다
    version_id = await version_of(app, table)
    await repository.add_embeddings(session, version_id, 'fake', {uuid.uuid4(): word_vector(query)})
    await session.commit()
    retriever, _ = make_retriever(app)

    assert await retriever.find(make_request(uuid.UUID(table['id']), query)) == []


async def test_a_table_without_lore_calls_no_model(client: AsyncClient, me: dict, app: FastAPI):
    table = await open_table(client, me, [])
    embedder = FakeEmbedder()
    retriever, _ = make_retriever(app, embedder)

    assert await retriever.find(make_request(uuid.UUID(table['id']), '드워프')) == []
    assert embedder.calls == []


@pytest.mark.parametrize('table_id', [None, uuid.UUID('00000000-0000-4000-8000-000000000000')])
async def test_no_table_means_no_lore(app: FastAPI, table_id: uuid.UUID | None):
    retriever, _ = make_retriever(app)

    assert await retriever.find(make_request(table_id, '드워프')) == []


# --- 실패와 모자람 ---


async def test_a_failing_model_still_picks_by_keyword(
    client: AsyncClient, me: dict, app: FastAPI, caplog: pytest.LogCaptureFixture
):
    table = await open_table(client, me, [DWARF, LADY])
    await app.state.jobs.drain()
    retriever, _ = make_retriever(app, FakeEmbedder(error='unreachable'))

    with caplog.at_level(logging.WARNING):
        notes = await retriever.find(make_request(uuid.UUID(table['id']), '드워프가 금빛 리무진을 탄다'))

    # 뜻으로 찾는 것은 못 하지만 이름이 나온 항목은 고른다. 서술은 막지 않는다
    assert names(notes) == ['드워프']
    assert 'unreachable' in caplog.text


async def test_missing_vectors_are_asked_for_and_keywords_still_work(client: AsyncClient, me: dict, app: FastAPI):
    app.state.embedder = FakeEmbedder(error='unreachable')
    table = await open_table(client, me, [DWARF, LADY])
    await app.state.jobs.drain()
    retriever, indexer = make_retriever(app)

    notes = await retriever.find(make_request(uuid.UUID(table['id']), '드워프'))

    # 게시 직후의 색인이 실패해 벡터가 없다. 다시 맡기고, 이번에는 키워드로 고른다
    assert names(notes) == ['드워프']
    assert indexer.scheduled == [await version_of(app, table)]


async def test_full_vectors_ask_for_nothing(client: AsyncClient, me: dict, app: FastAPI):
    table = await open_table(client, me, [DWARF, LADY])
    await app.state.jobs.drain()
    retriever, indexer = make_retriever(app)

    await retriever.find(make_request(uuid.UUID(table['id']), '드워프'))

    assert indexer.scheduled == []


async def test_the_indexer_fills_what_was_missing(client: AsyncClient, me: dict, app: FastAPI):
    app.state.embedder = FakeEmbedder(error='unreachable')
    table = await open_table(client, me, [DWARF, LADY])
    await app.state.jobs.drain()
    version_id = await version_of(app, table)

    added = await indexing.index_version(app.state.session_factory, FakeEmbedder(), version_id)

    # 다시 맡긴 색인이 돌면 그다음 라운드부터 뜻으로도 찾는다
    assert added == 2
    retriever, _ = make_retriever(app)
    assert names(await retriever.find(make_request(uuid.UUID(table['id']), '금빛 리무진을 탄다'))) == ['악역영애']


# --- 라운드를 닫을 때 ---


async def test_closing_a_round_puts_the_lore_in_the_prompt_and_the_record(
    client: AsyncClient, me: dict, app: FastAPI, session: AsyncSession
):
    table = await open_table(client, me, [DWARF, ELF, STAR])
    await app.state.jobs.drain()
    provider = FakeProvider(reply='엔진 소리가 골목을 메운다.')
    app.state.narrator = LLMNarrator(provider, DbCallLog(app.state.session_factory), digest_key=b'server-key')
    table_url = f'{API_PREFIX}/tables/{table["id"]}'
    await client.put(f'{table_url}/character', json={'name': '엘프'}, headers=me)
    await client.post(f'{table_url}/start', headers=me)

    # 혼자 앉은 테이블이라 선언하면 라운드가 닫힌다
    declared = await client.put(
        f'{table_url}/rounds/current/declaration', json={'content': '드워프의 망치를 피해 달린다.'}, headers=me
    )
    assert declared.status_code == status.HTTP_200_OK, declared.text
    await app.state.jobs.drain()

    (call,) = provider.calls
    last = call.messages[-1].content
    assert last.startswith(prompt.LORE_TITLE)
    assert f'- 드워프: {DWARF["content"]}' in last
    assert STAR['content'] not in last

    (row,) = await session.scalars(select(AiInvocation))
    dwarf_id = await entry_id(app, table, '드워프')
    assert dwarf_id in row.lore_entry_ids
    assert row.prompt_version == prompt.PROMPT_VERSION
    assert (row.temperature, row.max_tokens) == (0.8, 800)
    assert row.input_digest is not None and len(row.input_digest) == 64


async def entry_id(app: FastAPI, table: dict, name: str) -> uuid.UUID:
    """테이블의 복사본에서 이름이 name 인 항목의 id."""
    candidates = await load_candidates(app.state.session_factory, uuid.UUID(table['id']))
    return next(entry.id for entry in candidates.entries if entry.name == name)


async def version_of(app: FastAPI, table: dict) -> uuid.UUID:
    """테이블이 어느 판에서 왔는가."""
    candidates = await load_candidates(app.state.session_factory, uuid.UUID(table['id']))
    return candidates.version_id
