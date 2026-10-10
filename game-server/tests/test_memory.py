# game-server/tests/test_memory.py

"""
지난 라운드의 기억(app/memory/)을 검증한다. 임베딩 모델은 가짜다(낱말이 겹치는 글끼리 가깝다).

보는 것은 넷이다.
  - 라운드로 기억을 만들고, 자르고, 고르는 순수한 함수들.
  - 색인: 다음 라운드가 있는 라운드만 벡터가 된다. 없는 것만 만들고, 모델이 실패하면 멈춘다.
  - 고르기: 장면에 나온 인물의 기억을 최근 것부터 먼저, 그다음 뜻이 가까운 것. 지난 기록에 든 최근 라운드는 빼고,
    임베딩이 실패해도 인물로는 고른다.
  - 라운드를 닫으면 고른 기억이 프롬프트에 들어가고, 어느 라운드를 넣었는지 AI 호출의 기록에 남는다.
"""

import logging
import uuid
from dataclasses import dataclass, field

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.call_log import DbCallLog
from app.ai.fake import FakeEmbedder, FakeProvider
from app.ai.models import AiInvocation
from app.assets.models import LoreKind
from app.assets.scenarios.snapshot import EntrySnapshot
from app.main import API_PREFIX
from app.memory import indexing, repository
from app.memory.models import RoundMemory
from app.memory.retrieval import (
    MemoryRetriever,
    MemoryThresholds,
    about_people,
    choose_memories,
    eligible,
    near_enough,
    nearest_within,
    note_text,
    people_in,
    pick,
    to_note,
)
from app.memory.texts import NOBODY_DECLARED, Memory, clip, memories_of, memory_text, missing_memories
from app.rounds import prompt
from app.rounds.llm_narrator import LLMNarrator
from app.rounds.narrator import NO_PREVIEW, Move, NarrationRequest, PastRound, Preview
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
OPENING = '사이렌이 울린다.'

# 테스트에 쓰는 예시. 공개 저장소에 올라가도 되는 개그 설정이다.
# 진짜 이름은 설정에만 있고, 장면에서는 "악역영애"로 불리는 인물
LADY = {'name': '비올레타', 'keywords': ['악역영애', '부채'], 'content': '금빛 리무진을 탄다.', 'kind': 'person'}
# 라운드마다 플레이어가 한 말과 그 결과(다음 라운드의 장면). 1~4 라운드에 사건이 있고, 뒤는 비슷한 길이 이어진다
PLAYED = [
    ('톨게이트 차단기를 넘는다.', '드워프가 톨게이트 차단기를 망치로 부쉈다. 파편이 도로에 흩어졌다.'),
    ('악역영애에게 인사한다.', '악역영애가 부채를 접으며 웃었다. 리무진 창문으로 홍차를 권했다.'),
    ('주유소에 들른다.', '별빛 주유소의 수프 냄새가 퍼졌다. 주인이 국자를 휘둘렀다.'),
    ('리무진을 앞지른다.', '악역영애가 은하 경찰에게 엘프가 간 길을 손짓으로 알려 주었다.'),
    ('계속 달린다.', '고속도로가 은은하게 빛났다. 별자리 차선이 끝없이 이어졌다.'),
    ('계속 달린다.', '고속도로가 은은하게 빛났다. 운석이 멀리 지나갔다.'),
    ('계속 달린다.', '고속도로가 은은하게 빛났다. 엔진이 낮게 울었다.'),
    ('계속 달린다.', '고속도로가 은은하게 빛났다. 사이렌이 멀어졌다.'),
]
# 기억을 다 쓰고 연 라운드의 번호(1 라운드 + 닫은 라운드의 수)
CURRENT = len(PLAYED) + 1


def past(number: int, scene: str, *lines: str) -> PastRound:
    return PastRound(number=number, scene=scene, lines=list(lines))


def memory(number: int, result: str = '결과', *lines: str) -> Memory:
    return Memory(number=number, lines=tuple(lines), result=result)


def person(name: str, *keywords: str) -> EntrySnapshot:
    return EntrySnapshot(id=uuid.uuid4(), name=name, keywords=list(keywords), content='', kind=LoreKind.PERSON)


# --- 기억 만들기 ---


def test_a_round_and_the_scene_after_it_make_a_memory():
    rounds = [past(1, '도입부', '엘프: 달린다.'), past(2, '차단기가 부서졌다.', '엘프: 넘는다.'), past(3, '비가 온다.')]

    memories = memories_of(rounds)

    # 2 라운드에 한 말과 그 결과(3 라운드의 장면)가 한 기억이다. 3 라운드는 아직 결과가 없다
    assert memories == [memory(1, '차단기가 부서졌다.', '엘프: 달린다.'), memory(2, '비가 온다.', '엘프: 넘는다.')]


def test_memories_follow_the_numbers_even_when_rounds_come_mixed():
    rounds = [past(3, 'c'), past(1, 'a'), past(2, 'b')]

    assert [item.number for item in memories_of(rounds)] == [1, 2]


def test_a_gap_in_the_rounds_makes_no_memory():
    # 다음 라운드가 아닌 것을 결과로 잇지 않는다
    assert memories_of([past(1, 'a'), past(3, 'c')]) == []


def test_the_memory_text_is_what_was_said_and_what_came_of_it():
    assert memory_text(memory(2, '차단기가 부서졌다.', '엘프: 넘는다.', '드워프: 부순다.')) == (
        '엘프: 넘는다.\n드워프: 부순다.\n결과: 차단기가 부서졌다.'
    )
    assert memory_text(memory(2, '비가 온다.')) == f'{NOBODY_DECLARED}\n결과: 비가 온다.'


def test_only_memories_without_a_vector_are_missing():
    memories = [memory(1), memory(2), memory(3)]

    assert missing_memories(memories, {1, 3}) == [memory(2)]


# --- 자르기 ---


def test_a_short_text_is_not_clipped():
    assert clip('차단기가 부서졌다.', 20) == '차단기가 부서졌다.'


def test_a_long_text_is_clipped_at_the_end_of_a_sentence():
    text = '차단기가 부서졌다. 파편이 흩어졌다. 경찰이 왔다.'

    clipped = clip(text, 22)

    # 문장 중간에서 자르면 모델이 이어 쓰려 한다
    assert clipped == '차단기가 부서졌다. 파편이 흩어졌다.…'
    assert len(clipped) <= 22


@pytest.mark.parametrize('end', ['!', '?', '…'])
def test_other_sentence_ends_count(end: str):
    assert clip(f'멈춰{end} 엔진이 낮게 울었다', 10) == f'멈춰{end}…'


def test_a_line_break_ends_a_sentence():
    assert clip('엘프: 달린다\n결과: 차단기가 부서졌다', 12) == '엘프: 달린다…'


def test_a_text_without_a_sentence_end_is_cut_at_the_limit():
    clipped = clip('가' * 30, 10)

    assert clipped == '가' * 9 + '…'
    assert len(clipped) == 10


# --- 고르기의 순수한 함수 ---


def test_only_memories_before_the_recent_rounds_can_be_chosen():
    memories = [memory(number) for number in range(1, 9)]

    # 9 라운드를 서술할 때 지난 기록은 6, 7, 8 라운드다. 그 앞의 것만 고른다
    assert [item.number for item in eligible(memories, 9)] == [1, 2, 3, 4, 5]
    assert eligible(memories, 4) == []


def test_people_in_the_text_are_person_entries_named_or_called_there():
    lady = person('비올레타', '악역영애')
    dwarf = person('토르빈', '드워프')
    car = EntrySnapshot(id=uuid.uuid4(), name='리무진', keywords=[], content='', kind=LoreKind.ITEM)

    # 인물이 아닌 항목은 이름이 나와도 세지 않는다
    assert people_in([lady, dwarf, car], '악역영애가 리무진에서 내린다') == [lady]


def test_memories_about_the_people_come_latest_first():
    lady = person('비올레타', '악역영애')
    memories = [memory(1, '악역영애가 웃었다.'), memory(2, '비가 왔다.'), memory(3, '엘프', '엘프: 악역영애를 부른다.')]

    assert [item.number for item in about_people(memories, [lady])] == [3, 1]
    assert about_people(memories, []) == []


def test_a_person_hit_is_near_enough_within_the_limit_or_without_a_distance():
    item = memory(1)

    assert near_enough(item, {1: 0.4}, 0.5)
    assert not near_enough(item, {1: 0.6}, 0.5)
    # 벡터가 아직 없는 기억은 거리를 모른다. 인물로 걸렸으면 넣는다
    assert near_enough(item, {}, 0.5)


def test_nearest_memories_are_within_the_distance_in_order():
    memories = [memory(1), memory(2), memory(3), memory(4)]

    chosen = nearest_within(memories, {1: 0.5, 2: 0.2, 3: 0.9}, 0.6)

    # 거리를 모르는 4 는 고르지 않는다
    assert [item.number for item in chosen] == [2, 1]


def test_picking_stops_at_the_count_and_the_characters():
    short = [memory(number, '짧다.') for number in (1, 2, 3)]
    long = memory(4, '가' * 900 + '.')

    assert [item.number for item in pick(short, 2, 2000)] == [1, 2]
    # 들어가지 않는 것은 건너뛰고 뒤의 짧은 것을 넣는다
    assert [item.number for item in pick([long, long, *short], 3, 1000)] == [4, 1, 2]
    assert pick(short, 0, 2000) == []


def test_people_hits_come_before_closer_memories():
    lady = person('비올레타', '악역영애')
    memories = [memory(1, '악역영애가 웃었다.'), memory(2, '차단기가 부서졌다.'), memory(3, '악역영애가 배신했다.')]
    thresholds = MemoryThresholds(max_distance=0.5, keyword_max_distance=0.8)

    chosen = choose_memories(memories, [lady], {1: 0.7, 2: 0.1, 3: 0.6}, thresholds)

    # 인물의 일은 최근 것(3)부터. 2 가 더 가깝지만 두 자리가 인물의 일로 찼다
    assert [item.number for item in chosen] == [3, 1]


def test_a_far_person_hit_is_left_out_but_kept_without_distances():
    lady = person('비올레타', '악역영애')
    memories = [memory(1, '악역영애가 웃었다.'), memory(2, '차단기가 부서졌다.')]
    thresholds = MemoryThresholds(max_distance=0.5, keyword_max_distance=0.6)

    assert [item.number for item in choose_memories(memories, [lady], {1: 0.9, 2: 0.1}, thresholds)] == [2]
    # 임베딩이 실패하면 거리를 모른다. 인물로 걸린 것만 고른다
    assert [item.number for item in choose_memories(memories, [lady], {}, thresholds)] == [1]


def test_a_note_carries_the_round_and_the_clipped_text():
    item = memory(4, '차단기가 부서졌다. ' * 200, '엘프: 넘는다.')

    note = to_note(item)

    assert note.round_number == 4
    assert note.text == note_text(item)
    assert note.text.startswith('엘프: 넘는다.\n결과: 차단기가 부서졌다.')
    assert len(note.text) <= 1000


# --- 테이블에서 ---


@dataclass
class ScriptedNarrator:
    """정해 둔 결과를 차례로 쓰는 서술자. 받은 요청을 적어 둔다."""

    scenes: list[str]
    requests: list[NarrationRequest] = field(default_factory=list)

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        self.requests.append(request)
        return self.scenes[len(self.requests) - 1]


@dataclass
class CountingIndexer:
    """맡긴 테이블의 id 를 적어 두는 것. 색인을 실제로 돌리지 않는다."""

    scheduled: list[uuid.UUID] = field(default_factory=list)

    def schedule(self, table_id: uuid.UUID) -> None:
        self.scheduled.append(table_id)


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(ME)))
    return {'Authorization': f'Bearer {token}'}


async def open_table(client: AsyncClient, me: dict[str, str], entries: list[dict]) -> str:
    """로어북 하나를 붙인 시나리오로 혼자 앉는 테이블을 열고 시작한다. 테이블의 주소를 돌려준다."""
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
    table = (await client.post(f'{API_PREFIX}/tables', json=body, headers=me)).json()
    table_url = f'{API_PREFIX}/tables/{table["id"]}'
    await client.put(f'{table_url}/character', json={'name': '엘프'}, headers=me)
    started = await client.post(f'{table_url}/start', headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return table_url


async def play(client: AsyncClient, app: FastAPI, me: dict[str, str], table_url: str, said: list[str]) -> None:
    """라운드마다 한 말을 내고 서술이 끝나기를 기다린다. 혼자 앉은 테이블이라 내면 라운드가 닫힌다."""
    for content in said:
        declared = await client.put(f'{table_url}/rounds/current/declaration', json={'content': content}, headers=me)
        assert declared.status_code == status.HTTP_200_OK, declared.text
        await app.state.jobs.drain()


async def played_table(client: AsyncClient, app: FastAPI, me: dict[str, str]) -> uuid.UUID:
    """PLAYED 대로 여덟 라운드를 닫은 테이블. 9 라운드가 열려 있다. 기억의 벡터는 아직 없다."""
    app.state.narrator = ScriptedNarrator([result for _, result in PLAYED])
    app.state.memories = MemoryRetriever(app.state.session_factory, FakeEmbedder(), CountingIndexer())
    table_url = await open_table(client, me, [LADY])
    await play(client, app, me, table_url, [said for said, _ in PLAYED])
    return uuid.UUID(table_url.rsplit('/', 1)[1])


def make_retriever(
    app: FastAPI, embedder: FakeEmbedder | None = None
) -> tuple[MemoryRetriever, CountingIndexer, FakeEmbedder]:
    """고르는 것과 색인을 맡긴 기록과 임베더. 거리 기준은 테스트 설정의 것(가짜 임베더에 맞춘 값)이다."""
    indexer = CountingIndexer()
    embedder = embedder or FakeEmbedder()
    settings = app.state.settings
    thresholds = MemoryThresholds(settings.memory_max_distance, settings.memory_keyword_max_distance)
    return MemoryRetriever(app.state.session_factory, embedder, indexer, thresholds), indexer, embedder


def request_for(table_id: uuid.UUID, scene: str, said: str = '달린다.', number: int = CURRENT) -> NarrationRequest:
    return NarrationRequest(round_number=number, scene=scene, moves=[Move('엘프', said)], table_id=table_id)


def numbers(notes) -> list[int]:
    return [note.round_number for note in notes]


async def stored_numbers(session: AsyncSession, table_id: uuid.UUID, model: str = 'fake') -> list[int]:
    query = select(RoundMemory.round_number).where(RoundMemory.table_id == table_id, RoundMemory.model == model)
    return sorted(await session.scalars(query))


# --- 색인 ---


async def test_rounds_with_a_result_become_vectors(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    table_id = await played_table(client, app, me)

    added = await indexing.index_table(app.state.session_factory, FakeEmbedder(), table_id)

    # 9 라운드는 아직 결과가 없다
    assert added == len(PLAYED)
    assert await stored_numbers(session, table_id) == list(range(1, CURRENT))


async def test_indexing_twice_adds_nothing_and_calls_no_model(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table_id = await played_table(client, app, me)
    await indexing.index_table(app.state.session_factory, FakeEmbedder(), table_id)
    embedder = FakeEmbedder()

    assert await indexing.index_table(app.state.session_factory, embedder, table_id) == 0
    assert embedder.calls == []


async def test_the_vector_is_of_what_was_said_and_its_result(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table_id = await played_table(client, app, me)
    embedder = FakeEmbedder()

    await indexing.index_table(app.state.session_factory, embedder, table_id)

    (texts,) = embedder.calls
    said, result = PLAYED[0]
    assert texts[0] == f'엘프: {said}\n결과: {result}'


async def test_each_model_has_its_own_vectors(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    table_id = await played_table(client, app, me)
    await indexing.index_table(app.state.session_factory, FakeEmbedder(), table_id)

    added = await indexing.index_table(app.state.session_factory, FakeEmbedder(model='other'), table_id)

    assert added == len(PLAYED)
    assert await stored_numbers(session, table_id, 'other') == list(range(1, CURRENT))


async def test_a_failing_model_stops_the_indexing(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession, caplog: pytest.LogCaptureFixture
):
    table_id = await played_table(client, app, me)

    with caplog.at_level(logging.WARNING):
        added = await indexing.index_table(app.state.session_factory, FakeEmbedder(error='timeout'), table_id)

    assert added == 0
    assert await stored_numbers(session, table_id) == []
    assert 'timeout' in caplog.text


async def test_vectors_go_with_the_table(client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession):
    table_id = await played_table(client, app, me)
    await indexing.index_table(app.state.session_factory, FakeEmbedder(), table_id)

    # 다른 테이블의 번호로는 찾지 못한다
    assert await repository.count_vectors(session, uuid.uuid4(), 'fake') == 0
    assert await repository.count_vectors(session, table_id, 'fake') == len(PLAYED)


# --- 고르기 ---


async def test_a_person_in_the_scene_brings_their_latest_memories_first(
    client: AsyncClient, app: FastAPI, me: dict[str, str]
):
    table_id = await played_table(client, app, me)
    await indexing.index_table(app.state.session_factory, FakeEmbedder(), table_id)
    retriever, _, _ = make_retriever(app)

    notes = await retriever.find(request_for(table_id, '리무진 창문이 내려간다.', '악역영애에게 손을 흔든다.'))

    # 악역영애가 나온 2 와 4 라운드. 배신한 4 라운드가 먼저다
    assert numbers(notes) == [4, 2]
    assert notes[0].text == f'엘프: {PLAYED[3][0]}\n결과: {PLAYED[3][1]}'


async def test_a_memory_close_in_meaning_is_found_without_a_person(
    client: AsyncClient, app: FastAPI, me: dict[str, str]
):
    table_id = await played_table(client, app, me)
    await indexing.index_table(app.state.session_factory, FakeEmbedder(), table_id)
    retriever, _, _ = make_retriever(app)

    notes = await retriever.find(request_for(table_id, '톨게이트 차단기를 망치로 부순 드워프가 파편을 치운다.', ''))

    assert numbers(notes)[0] == 1


async def test_the_recent_rounds_are_never_chosen(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table_id = await played_table(client, app, me)
    await indexing.index_table(app.state.session_factory, FakeEmbedder(), table_id)
    retriever, _, _ = make_retriever(app)

    # 6, 7, 8 라운드의 글과 거의 같은 장면이다. 그 라운드들은 지난 기록으로 이미 들어간다
    notes = await retriever.find(
        request_for(table_id, '고속도로가 은은하게 빛났다. 엔진이 낮게 울었다.', '계속 달린다.')
    )

    assert notes
    assert all(number < CURRENT - prompt.HISTORY_ROUNDS for number in numbers(notes))


async def test_too_early_a_round_has_no_memories_and_calls_no_model(
    client: AsyncClient, app: FastAPI, me: dict[str, str]
):
    table_id = await played_table(client, app, me)
    retriever, indexer, embedder = make_retriever(app)

    # 4 라운드를 서술할 때 지난 기록은 1~3 라운드다. 그 앞은 없다
    assert await retriever.find(request_for(table_id, '악역영애가 웃는다.', number=4)) == []
    assert embedder.calls == []
    # 벡터가 모자라면 그래도 색인은 맡긴다
    assert indexer.scheduled == [table_id]


async def test_missing_vectors_are_asked_for_and_people_still_work(
    client: AsyncClient, app: FastAPI, me: dict[str, str]
):
    table_id = await played_table(client, app, me)
    retriever, indexer, _ = make_retriever(app)

    notes = await retriever.find(request_for(table_id, '악역영애가 웃는다.'))

    # 벡터가 없는 기억은 거리를 모른다. 인물로 걸린 것은 넣는다
    assert numbers(notes) == [4, 2]
    assert indexer.scheduled == [table_id]


async def test_full_vectors_ask_for_nothing(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table_id = await played_table(client, app, me)
    await indexing.index_table(app.state.session_factory, FakeEmbedder(), table_id)
    retriever, indexer, _ = make_retriever(app)

    await retriever.find(request_for(table_id, '악역영애가 웃는다.'))

    assert indexer.scheduled == []


async def test_a_failing_model_still_picks_by_people(
    client: AsyncClient, app: FastAPI, me: dict[str, str], caplog: pytest.LogCaptureFixture
):
    table_id = await played_table(client, app, me)
    await indexing.index_table(app.state.session_factory, FakeEmbedder(), table_id)
    retriever, _, _ = make_retriever(app, FakeEmbedder(error='unreachable'))

    with caplog.at_level(logging.WARNING):
        notes = await retriever.find(request_for(table_id, '부서진 톨게이트 앞에서 악역영애가 웃는다.'))

    # 뜻으로 찾는 것(차단기의 1 라운드)은 못 하지만 인물의 일은 고른다. 서술은 막지 않는다
    assert numbers(notes) == [4, 2]
    assert 'unreachable' in caplog.text


async def test_a_far_memory_is_not_picked(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table_id = await played_table(client, app, me)
    await indexing.index_table(app.state.session_factory, FakeEmbedder(), table_id)
    retriever, _, _ = make_retriever(app)

    # 겹치는 낱말이 없으면 멀다. 상관없는 지난 일을 넣지 않는다
    assert await retriever.find(request_for(table_id, '아무 상관 없는 이야기', '')) == []


async def test_no_table_means_no_memories(app: FastAPI):
    retriever, _, embedder = make_retriever(app)
    request = NarrationRequest(round_number=CURRENT, scene=OPENING, moves=[])

    assert await retriever.find(request) == []
    assert await retriever.find(request_for(uuid.uuid4(), OPENING)) == []
    assert embedder.calls == []


async def test_the_app_uses_the_distances_in_the_settings(app: FastAPI):
    settings = app.state.settings

    assert app.state.memories.thresholds == MemoryThresholds(
        settings.memory_max_distance, settings.memory_keyword_max_distance
    )


# --- 라운드를 닫을 때 ---


async def test_closing_a_round_puts_the_memories_in_the_prompt_and_the_record(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    provider = FakeProvider(reply='고속도로가 은은하게 빛났다.')
    app.state.narrator = LLMNarrator(provider, DbCallLog(app.state.session_factory))
    table_url = await open_table(client, me, [LADY])

    # 지난 기록은 3 라운드다. 5 라운드를 서술할 때 처음으로 1 라운드의 기억을 고를 수 있다.
    # 그 전에 앞의 서술들이 색인을 맡겨 두었다(서술을 맡길 때 모자라면 맡긴다)
    await play(
        client, app, me, table_url, ['악역영애에게 인사한다.', '달린다.', '달린다.', '달린다.', '악역영애를 부른다.']
    )

    last = provider.calls[-1].messages[-1].content
    assert prompt.MEMORY_TITLE in last
    assert '(1 라운드)\n엘프: 악역영애에게 인사한다.' in last
    assert all(prompt.MEMORY_TITLE not in call.messages[-1].content for call in provider.calls[:4])
    rows = (await session.scalars(select(AiInvocation).order_by(AiInvocation.round_number))).all()
    assert [row.memory_rounds for row in rows] == [[], [], [], [], [1]]
