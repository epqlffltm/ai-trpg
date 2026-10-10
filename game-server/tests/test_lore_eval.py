# game-server/tests/test_lore_eval.py

"""
로어북 검색 평가 도구(evals/lore, scripts/eval_lore.py)를 검증한다.

DB 도 모델도 쓰지 않는다. 벡터는 손으로 적거나 가짜 임베더(낱말이 겹치는지만 보는 것)로 만든다.
실제 평가 데이터(chase.yaml)도 늘 읽어 본다. 손으로 늘리다 생긴 실수가 CI 에서 걸린다.
"""

import argparse
import copy
import math
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from app.ai.fake import FakeEmbedder
from app.ai.openai_embedder import OpenAICompatEmbedder
from app.ai.provider import ProviderError
from app.assets.scenarios.snapshot import EntrySnapshot
from app.lore.retrieval import KEYWORD_MAX_DISTANCE, MAX_DISTANCE, Thresholds, choose, query_text
from app.rounds.narrator import NarrationRequest
from evals.lore.dataset import (
    DEFAULT_PATH,
    EMPTY_KINDS,
    DatasetError,
    Kind,
    Query,
    entry_id,
    find_problems,
    load_dataset,
    only_set,
    parse_dataset,
)
from evals.lore.metrics import (
    Method,
    Outcome,
    Ranked,
    Rule,
    Score,
    chosen_by,
    cosine_distance,
    empty_rate,
    f1,
    five_numbers,
    hit_distances,
    micro_precision,
    query_distances,
    rank,
    ranking_recall_at,
    recall,
    reciprocal_rank,
    score,
    split_distances,
    within_gate,
)
from evals.lore.report import ModelResult, best, best_gate, full_report, miss_lines, name_recall
from evals.lore.runner import (
    GATE_SWEEP,
    SWEEP,
    evaluate,
    evaluate_current,
    measure,
    sweep,
    sweep_gates,
    window_distances,
)
from evals.lore.windows import sentences, windows_for
from scripts.eval_lore import NoQueries, failure_message, make_embedders, read_dataset, run


def small_document() -> dict:
    """작은 평가 문서. 항목 셋, 질의 넷(종류마다 하나)."""
    return {
        'title': '작은 추격전',
        'entries': [
            {'name': '리엔', 'keywords': ['엘프'], 'content': '엘프 폭주족의 우두머리.'},
            {'name': '토르빈', 'keywords': ['드워프', '망치'], 'content': '망치로 다 고치는 드워프 정비공.'},
            {'name': '홍차', 'keywords': [], 'content': '악역영애가 추격 중에도 마시는 차.'},
        ],
        'queries': [
            {
                'id': 'a1',
                'set': 'v1',
                'kind': 'name',
                'scene': '고속도로.',
                'moves': [{'character': '카이', 'content': '리엔을 부른다.'}],
                'expected': ['리엔'],
            },
            {
                'id': 'a2',
                'set': 'v1',
                'kind': 'meaning',
                'scene': '정비소.',
                'moves': [{'character': '모모', 'content': '정비공에게 엔진을 맡긴다.'}],
                'expected': ['토르빈'],
            },
            {'id': 'a3', 'set': 'v2', 'kind': 'distractor', 'scene': '계획을 망치고 말았다.', 'expected': []},
            {'id': 'a4', 'set': 'v2', 'kind': 'none', 'scene': '조용한 밤이다.', 'moves': [], 'expected': []},
        ],
    }


def entry(name: str, content: str = '내용') -> EntrySnapshot:
    """이름만 정한 항목."""
    return EntrySnapshot(id=entry_id(name), name=name, keywords=[], content=content)


def outcome(chosen: list[str], expected: list[str], kind: Kind = Kind.NAME) -> Outcome:
    """고른 것과 정답만 정한 결과."""
    request = NarrationRequest(round_number=1, scene='장면', moves=[])
    return Outcome(Query('q', 'v1', kind, request, frozenset(expected)), chosen)


# --- 실제 평가 데이터 ---


def test_the_real_dataset_has_no_problems():
    dataset = load_dataset(DEFAULT_PATH)

    assert len(dataset.entries) >= 30
    assert len(dataset.queries) >= 40
    assert {query.kind for query in dataset.queries} == set(Kind)


def test_the_real_dataset_labels_fit_their_kinds():
    dataset = load_dataset(DEFAULT_PATH)

    for query in dataset.queries:
        assert (not query.expected) == (query.kind in EMPTY_KINDS), query.id


def test_the_real_dataset_keeps_private_settings_out():
    text = DEFAULT_PATH.read_text(encoding='utf-8')

    assert '가나폴리' not in text


# --- 데이터 검사 ---


def test_a_good_document_has_no_problems():
    assert find_problems(small_document()) == []


def test_a_document_becomes_entries_and_requests():
    dataset = parse_dataset(small_document())

    assert dataset.title == '작은 추격전'
    assert [item.name for item in dataset.entries] == ['리엔', '토르빈', '홍차']
    first = dataset.queries[0]
    assert first.kind == Kind.NAME
    assert first.expected == frozenset({'리엔'})
    assert '리엔을 부른다.' in query_text(first.request)


def test_entry_ids_come_from_names():
    assert entry_id('리엔') == entry_id('리엔')
    assert entry_id('리엔') != entry_id('토르빈')
    assert parse_dataset(small_document()).entries[0].id == entry_id('리엔')


def broken(change) -> list[str]:
    """작은 문서를 고쳐 틀린 곳들을 찾는다."""
    document = copy.deepcopy(small_document())
    change(document)
    return find_problems(document)


@pytest.mark.parametrize(
    ('change', 'expected'),
    [
        (lambda d: d['queries'][0].update(expected=['미르']), '없는 항목을 정답으로'),
        (lambda d: d['queries'][2].update(expected=['토르빈']), '정답이 비어 있어야'),
        (lambda d: d['queries'][1].update(expected=[]), '정답이 없다'),
        (lambda d: d['queries'][0].update(kind='guess'), 'kind 는'),
        (lambda d: d['queries'][0].update(kind=['name']), 'kind 는'),
        (lambda d: d['queries'][0].pop('scene'), 'scene 가 없다'),
        (lambda d: d['queries'][0].update(expected='리엔'), 'expected 가 목록이 아니다'),
        (lambda d: d['queries'][0].update(moves=[{'content': '누가?'}]), 'moves 는'),
        (lambda d: d['queries'][1].update(id='a1'), '질의 id 가 겹친다: a1'),
        (lambda d: d['entries'].append({'name': '리엔'}), '항목 이름이 겹친다: 리엔'),
        (lambda d: d['entries'][0].pop('name'), 'name 이 없다'),
        (lambda d: d['entries'][0].update(name='가' * 101), '이름이'),
        (lambda d: d['entries'][0].update(keywords=['a'] * 6), '키워드는 5개까지'),
        (lambda d: d['entries'][0].update(keywords=['가' * 31]), '키워드는 빈 글이 아니고'),
        (lambda d: d['entries'][0].update(keywords=['  ']), '키워드는 빈 글이 아니고'),
        (lambda d: d['entries'][0].update(content='가' * 501), '내용은'),
        (lambda d: d['entries'].append('리엔'), '하나하나가 사전'),
    ],
)
def test_mistakes_are_found(change, expected: str):
    problems = broken(change)

    assert any(expected in problem for problem in problems), problems


@pytest.mark.parametrize('document', [None, [], '글', {'entries': '리엔', 'queries': []}])
def test_a_document_of_the_wrong_shape_is_a_problem(document):
    assert find_problems(document)


def test_every_mistake_is_reported_at_once():
    def change(document: dict) -> None:
        document['queries'][0]['expected'] = ['미르']
        document['queries'][3]['expected'] = ['홍차']

    with pytest.raises(DatasetError) as caught:
        parse_dataset(copy.deepcopy(small_document()) | {'queries': broken_queries(change)})

    assert len(caught.value.problems) == 2


def broken_queries(change) -> list[dict]:
    """질의들을 고친 것."""
    document = copy.deepcopy(small_document())
    change(document)
    return document['queries']


def test_a_set_keeps_only_its_queries():
    dataset = parse_dataset(small_document())

    assert [query.id for query in only_set(dataset, 'v2').queries] == ['a3', 'a4']
    assert only_set(dataset, None) is dataset
    assert only_set(dataset, 'v9').queries == []


def test_a_file_is_read(tmp_path: Path):
    path = tmp_path / 'tiny.yaml'
    path.write_text('title: 작은\nentries:\n  - name: 리엔\nqueries: []\n', encoding='utf-8')

    dataset = load_dataset(path)

    assert [item.name for item in dataset.entries] == ['리엔']


# --- 거리와 순서 ---


@pytest.mark.parametrize(
    ('left', 'right', 'distance'),
    [([1, 0], [2, 0], 0.0), ([1, 0], [0, 1], 1.0), ([1, 0], [-1, 0], 2.0), ([0, 0], [1, 0], 1.0)],
)
def test_the_cosine_distance(left, right, distance):
    assert cosine_distance(left, right) == pytest.approx(distance)


def test_entries_are_ranked_nearest_first_and_those_without_vectors_are_left_out():
    near, far, missing = entry('가'), entry('나'), entry('다')
    vectors = {near.id: [1.0, 0.1], far.id: [0.0, 1.0]}

    ranked = rank([1.0, 0.0], [far, missing, near], vectors)

    assert [item.entry.name for item in ranked] == ['가', '나']
    assert ranked[0].distance < ranked[1].distance


def test_the_methods_choose_as_the_server_does():
    dataset = parse_dataset(small_document())
    query = dataset.queries[0]
    entries = dataset.entries
    # 리엔은 이름이 나왔지만 가장 멀고, 홍차는 가깝다
    ranked = [Ranked(entries[2], 0.1), Ranked(entries[1], 0.4), Ranked(entries[0], 0.9)]

    rule = Rule(0.5)

    assert chosen_by(Method.KEYWORD, entries, query, ranked, {}, rule) == ['리엔']
    assert chosen_by(Method.VECTOR, entries, query, ranked, {}, rule) == ['홍차', '토르빈']
    assert chosen_by(Method.HYBRID, entries, query, ranked, {}, rule) == ['리엔', '홍차', '토르빈']
    # 키워드의 상한을 끈 서버의 고르기와 같다
    server = choose(entries, query_text(query.request), query_distances(ranked), Thresholds(0.5, math.inf))
    assert [item.name for item in server] == ['리엔', '홍차', '토르빈']


def test_the_gated_method_is_the_server_rule():
    dataset = parse_dataset(small_document())
    entries = dataset.entries
    query = dataset.queries[0]
    ranked = [Ranked(entries[2], 0.1), Ranked(entries[1], 0.4), Ranked(entries[0], 0.6)]
    distances = query_distances(ranked)

    for gate in (0.5, 0.7):
        server = choose(entries, query_text(query.request), distances, Thresholds(0.5, gate))
        assert chosen_by(Method.GATED, entries, query, ranked, {}, Rule(0.5, gate)) == [item.name for item in server]
    assert chosen_by(Method.GATED, entries, query, ranked, {}, Rule(0.5, 0.5)) == ['홍차', '토르빈']
    assert chosen_by(Method.GATED, entries, query, ranked, {}, Rule(0.5, 0.7)) == ['리엔', '홍차', '토르빈']


def test_the_length_cap_applies_to_every_method():
    long_ones = [entry(f'항목{number}', '가' * 1400) for number in range(3)]
    document = small_document()
    query = parse_dataset(document).queries[3]
    ranked = [Ranked(item, 0.1) for item in long_ones]

    assert len(chosen_by(Method.VECTOR, long_ones, query, ranked, {}, Rule(0.5))) == 2


def test_a_gate_on_the_query_distance_drops_far_keyword_hits():
    dataset = parse_dataset(small_document())
    entries = dataset.entries
    # 리엔은 이름이 나왔지만 질의와 0.9 만큼 멀다
    ranked = [Ranked(entries[2], 0.1), Ranked(entries[0], 0.9)]
    query = dataset.queries[0]

    assert chosen_by(Method.GATED, entries, query, ranked, {}, Rule(0.5, gate=0.95)) == ['리엔', '홍차']
    assert chosen_by(Method.GATED, entries, query, ranked, {}, Rule(0.5, gate=0.5)) == ['홍차']


def test_a_gate_on_the_sentence_distance_looks_only_at_the_sentence():
    dataset = parse_dataset(small_document())
    entries = dataset.entries
    ranked = [Ranked(entries[2], 0.1), Ranked(entries[0], 0.9)]
    query = dataset.queries[0]
    # 질의 전체와는 멀어도 이름이 나온 문장과는 가깝다
    windows = {entries[0].id: 0.3}

    assert chosen_by(Method.WINDOWED, entries, query, ranked, windows, Rule(0.5, gate=0.4)) == ['리엔', '홍차']
    assert chosen_by(Method.WINDOWED, entries, query, ranked, windows, Rule(0.5, gate=0.2)) == ['홍차']
    # 문장의 거리를 모르면 넣지 않는다
    assert chosen_by(Method.WINDOWED, entries, query, ranked, {}, Rule(0.5, gate=0.9)) == ['홍차']


def test_without_a_gate_the_gated_methods_choose_as_hybrid_does():
    dataset = parse_dataset(small_document())
    entries = dataset.entries
    ranked = [Ranked(entries[2], 0.1), Ranked(entries[0], 0.9)]
    query = dataset.queries[0]
    windows = {entries[0].id: 0.99}

    hybrid = chosen_by(Method.HYBRID, entries, query, ranked, windows, Rule(0.5))

    assert chosen_by(Method.GATED, entries, query, ranked, windows, Rule(0.5)) == hybrid
    assert chosen_by(Method.WINDOWED, entries, query, ranked, windows, Rule(0.5)) == hybrid


def test_within_gate_keeps_only_known_near_hits():
    near, far, unknown = entry('가'), entry('나'), entry('다')
    distances = {near.id: 0.2, far.id: 0.8}

    assert within_gate([near, far, unknown], distances, 0.5) == [near]
    assert within_gate([near, far, unknown], distances, 0.8) == [near, far]


# --- 문장 ---


def test_text_is_split_into_sentences():
    text = '비가 온다. 리엔이 웃는다!\n카이: 엔진을 켠다… 모모: 정말?'

    assert sentences(text) == ['비가 온다.', '리엔이 웃는다!', '카이: 엔진을 켠다…', '모모: 정말?']
    assert sentences('  ') == []


def test_windows_are_the_sentences_that_mention_the_entry():
    lien = EntrySnapshot(id=entry_id('리엔'), name='리엔', keywords=['엘프'], content='')
    text = '비가 온다. 리엔이 웃는다.\n카이: 엘프에게 손을 흔든다.'

    assert windows_for(lien, text) == ['리엔이 웃는다.', '카이: 엘프에게 손을 흔든다.']


def test_a_keyword_cut_by_a_sentence_end_falls_back_to_the_whole_text():
    odd = EntrySnapshot(id=entry_id('끝. 시작'), name='끝. 시작', keywords=[], content='')
    text = '이야기의 끝. 시작이다.'

    assert windows_for(odd, text) == [text]


# --- 지표 ---


def test_recall_counts_the_expected_that_were_chosen():
    assert recall(['가', '다'], frozenset({'가', '나'})) == 0.5
    assert recall([], frozenset({'가'})) == 0.0
    assert recall(['가'], frozenset()) is None


def test_the_reciprocal_rank_is_of_the_first_right_one():
    assert reciprocal_rank(['다', '가'], frozenset({'가'})) == 0.5
    assert reciprocal_rank(['가'], frozenset({'가'})) == 1.0
    assert reciprocal_rank(['다'], frozenset({'가'})) == 0.0
    assert reciprocal_rank(['다'], frozenset()) is None


def test_precision_counts_choices_on_queries_without_answers_as_wrong():
    outcomes = [outcome(['가', '나'], ['가']), outcome(['다'], [], Kind.NONE)]

    assert micro_precision(outcomes) == pytest.approx(1 / 3)
    assert micro_precision([outcome([], ['가'])]) is None


def test_the_empty_rate_looks_only_at_queries_without_answers():
    outcomes = [outcome([], ['가']), outcome([], [], Kind.NONE), outcome(['다'], [], Kind.DISTRACTOR)]

    assert empty_rate(outcomes) == 0.5
    assert empty_rate([outcome([], ['가'])]) is None


def test_a_score_averages_recall_over_queries_with_answers_only():
    outcomes = [outcome(['가'], ['가']), outcome([], ['나']), outcome([], [], Kind.NONE)]

    result = score(outcomes)

    assert result.recall == 0.5
    assert result.precision == 1.0
    assert result.mrr == 0.5
    assert result.empty == 1.0
    assert result.queries == 3


def test_f1_is_zero_without_recall_or_precision():
    assert f1(Score(recall=0.5, precision=1.0, mrr=None, empty=None, queries=1)) == pytest.approx(2 / 3)
    assert f1(Score(recall=None, precision=1.0, mrr=None, empty=None, queries=1)) == 0.0
    assert f1(Score(recall=0.5, precision=0.0, mrr=None, empty=None, queries=1)) == 0.0


def test_ranking_recall_looks_at_the_nearest_k_without_a_distance_limit():
    dataset = parse_dataset(small_document())
    entries = dataset.entries
    ranked = {
        'a1': [Ranked(entries[2], 0.9), Ranked(entries[0], 0.95)],
        'a2': [Ranked(entries[1], 0.9)],
        'a3': [Ranked(entries[1], 0.1)],
        'a4': [],
    }

    assert ranking_recall_at(ranked, dataset.queries, 1) == 0.5
    assert ranking_recall_at(ranked, dataset.queries, 2) == 1.0


def test_distances_are_split_into_right_and_other():
    dataset = parse_dataset(small_document())
    entries = dataset.entries
    ranked = {'a1': [Ranked(entries[0], 0.2), Ranked(entries[1], 0.7)], 'a2': [], 'a3': [Ranked(entries[1], 0.3)]}
    ranked['a4'] = []

    assert split_distances(ranked, dataset.queries) == ([0.2], [0.7, 0.3])


def test_five_numbers():
    assert five_numbers([]) is None
    assert five_numbers([0.4]) == (0.4,) * 5
    assert five_numbers([0.1, 0.2, 0.3, 0.4, 0.5]) == pytest.approx((0.1, 0.2, 0.3, 0.4, 0.5))


# --- 돌리기 ---


async def test_measuring_ranks_every_entry_for_every_query():
    dataset = parse_dataset(small_document())

    measurement = await measure(FakeEmbedder(), dataset)

    assert measurement.model == 'fake'
    assert set(measurement.ranked) == {'a1', 'a2', 'a3', 'a4'}
    assert all(len(ranked) == 3 for ranked in measurement.ranked.values())
    assert len(measurement.query_ms) == 4


async def test_queries_are_embedded_one_at_a_time_with_the_server_text():
    dataset = parse_dataset(small_document())
    embedder = FakeEmbedder()

    await measure(embedder, dataset)

    calls = iter(embedder.calls[1:])
    # 질의마다 그 글 하나만 든 호출이 차례대로 있다(사이사이에 문장들의 호출이 낀다)
    for query in dataset.queries:
        assert [query_text(query.request)] in calls


async def test_sentences_with_keyword_hits_are_measured_for_those_entries_only():
    dataset = parse_dataset(small_document())
    embedder = FakeEmbedder()

    measurement = await measure(embedder, dataset)

    lien, torvin = dataset.entries[0].id, dataset.entries[1].id
    assert set(measurement.windows['a1']) == {lien}
    # 계획을 망치고 → 토르빈의 키워드 망치
    assert set(measurement.windows['a3']) == {torvin}
    assert measurement.windows['a4'] == {}
    assert ['계획을 망치고 말았다.'] in embedder.calls
    # 걸린 항목이 있는 질의만 문장을 보낸다
    assert len(measurement.window_ms) == 2


async def test_a_sentence_is_sent_once_and_the_nearest_counts():
    near, far = entry('가'), entry('나')
    vectors = {near.id: [1.0, 0.0], far.id: [0.0, 1.0]}

    class Recording:
        model = 'recording'
        calls: list[list[str]] = []

        async def embed(self, texts: list[str]) -> list[list[float]]:
            self.calls.append(texts)
            return [[1.0, 0.0] if text == '가깝다' else [0.0, 1.0] for text in texts]

    embedder = Recording()
    pairs = [(near, '가깝다'), (near, '멀다'), (far, '멀다')]

    distances = await window_distances(embedder, pairs, vectors)

    assert embedder.calls == [['가깝다', '멀다']]
    assert distances[near.id] == pytest.approx(0.0)
    assert distances[far.id] == pytest.approx(0.0)


async def test_sweeping_does_not_call_the_model_again():
    dataset = parse_dataset(small_document())
    embedder = FakeEmbedder()
    measurement = await measure(embedder, dataset)
    calls = len(embedder.calls)

    swept = sweep(dataset, measurement)

    assert len(embedder.calls) == calls
    assert [item.max_distance for item in swept] == list(SWEEP)


async def test_the_keyword_method_does_not_depend_on_the_distance():
    dataset = parse_dataset(small_document())
    measurement = await measure(FakeEmbedder(), dataset)

    tight, loose = evaluate(dataset, measurement, 0.0), evaluate(dataset, measurement, 2.0)

    assert tight.overall[Method.KEYWORD] == loose.overall[Method.KEYWORD]
    assert tight.overall[Method.VECTOR].precision is None
    assert loose.overall[Method.VECTOR].empty == 0.0


async def test_the_name_query_is_found_by_keyword():
    dataset = parse_dataset(small_document())
    measurement = await measure(FakeEmbedder(), dataset)

    result = evaluate(dataset, measurement, 0.0)

    assert result.by_kind[Method.KEYWORD][Kind.NAME].recall == 1.0
    # 망치고 의 망치 는 토르빈의 키워드에 걸린다. 키워드 방식이 낱말을 뜻으로 가리지 못함을 보여 준다
    assert result.by_kind[Method.KEYWORD][Kind.DISTRACTOR].empty == 0.0


# --- 보고서 ---


async def model_result(max_distance: float = 0.6) -> tuple:
    """작은 문서를 가짜 임베더로 잰 결과."""
    dataset = parse_dataset(small_document())
    measurement = await measure(FakeEmbedder(), dataset)
    swept = sweep(dataset, measurement)
    gated = sweep_gates(dataset, measurement, max_distance)
    return dataset, ModelResult(measurement, evaluate_current(dataset, measurement), swept, gated)


async def test_the_report_has_a_summary_and_a_section_per_model():
    dataset, result = await model_result()

    report = full_report(dataset, [result, result])

    assert report.startswith('# 로어북 검색 평가: 작은 추격전 (항목 3개, 질의 4개)')
    assert report.count('## fake') == 2
    assert '| 질의 기준 상한(서버) |' in report
    assert '### 틀린 질의 (서버, 거리 기준 0.45, 키워드 상한 0.50)' in report
    assert '←' in report
    assert '### 키워드에 상한을 두면' in report
    assert '| 없음(hybrid) |' in report
    assert '문장 기준, 아닌 항목' in report


async def test_misses_name_what_was_missed_and_what_was_wrong():
    dataset, result = await model_result(0.0)

    lines = miss_lines(dataset, result.measurement, Method.HYBRID, Rule(0.0))

    assert "- a2 (meaning): 놓침 ['토르빈']" in lines
    assert "- a3 (distractor): 잘못 넣음 ['토르빈']" in lines


async def test_the_best_threshold_has_the_highest_hybrid_f1():
    dataset, result = await model_result()

    chosen = best(result.swept)

    top = max(f1(item.overall[Method.HYBRID]) for item in result.swept)
    assert f1(chosen.overall[Method.HYBRID]) == top


# --- 스크립트 ---


def arguments(**values) -> argparse.Namespace:
    """스크립트의 명령줄 값."""
    defaults = {'model': None, 'set': None, 'data': DEFAULT_PATH, 'base_url': None, 'fake': False, 'out': None}
    return argparse.Namespace(**(defaults | values))


async def test_the_script_runs_with_the_fake_embedder():
    report = await run(arguments(fake=True, set='v1'))

    assert '## fake' in report
    assert '열일곱 행성 추격전' in report


async def test_each_model_gets_its_own_embedder():
    async with httpx.AsyncClient() as client:
        embedders = make_embedders(arguments(model=['bge-m3', ' qwen3-embedding:0.6b'], base_url='http://x/v1'), client)

    assert [item.model for item in embedders] == ['bge-m3', 'qwen3-embedding:0.6b']
    assert all(isinstance(item, OpenAICompatEmbedder) and item.base_url == 'http://x/v1' for item in embedders)


def test_a_set_without_queries_stops_the_script():
    with pytest.raises(NoQueries):
        read_dataset(arguments(set='없는묶음'))


def test_failures_are_one_line_without_the_answer():
    assert failure_message(ProviderError('unreachable')).startswith('임베딩 모델을 부르지 못했다: unreachable.')
    assert failure_message(NoQueries('v9')) == '그 묶음의 질의가 없다: v9'
    assert '리엔' in failure_message(DatasetError(['entries[0] 리엔: 이름이']))


async def test_sweeping_gates_does_not_call_the_model_again():
    dataset = parse_dataset(small_document())
    embedder = FakeEmbedder()
    measurement = await measure(embedder, dataset)
    calls = len(embedder.calls)

    gated = sweep_gates(dataset, measurement, 0.6)

    assert len(embedder.calls) == calls
    assert [item.rule.gate for item in gated] == list(GATE_SWEEP)
    assert all(item.max_distance == 0.6 for item in gated)
    assert set(gated[0].overall) == {Method.GATED, Method.WINDOWED}


async def test_a_tight_gate_drops_the_homonym_and_the_name():
    dataset = parse_dataset(small_document())
    measurement = await measure(FakeEmbedder(), dataset)

    (tight,) = sweep_gates(dataset, measurement, 0.0, [0.0])
    (loose,) = sweep_gates(dataset, measurement, 0.0, [2.0])

    assert tight.by_kind[Method.WINDOWED][Kind.DISTRACTOR].empty == 1.0
    assert name_recall(tight, Method.WINDOWED) == 0.0
    assert loose.by_kind[Method.WINDOWED][Kind.DISTRACTOR].empty == 0.0
    assert name_recall(loose, Method.WINDOWED) == 1.0


def test_hit_distances_are_split_into_right_and_wrong():
    dataset = parse_dataset(small_document())
    entries = dataset.entries
    ranked = {query.id: [Ranked(item, 0.5) for item in entries] for query in dataset.queries}
    distances = {'a1': {entries[0].id: 0.3}, 'a2': {}, 'a3': {entries[1].id: 0.7}, 'a4': {}}

    assert hit_distances(ranked, distances, dataset.queries) == ([0.3], [0.7])


async def test_the_best_gate_prefers_finding_names_then_the_looser_gate():
    dataset, result = await model_result()
    same = [replace(result.gated[0], rule=Rule(0.6, gate)) for gate in (0.5, 0.7)]

    assert best_gate(same, Method.WINDOWED).rule.gate == 0.7


async def test_the_current_evaluation_uses_the_server_defaults_for_every_method():
    dataset = parse_dataset(small_document())
    measurement = await measure(FakeEmbedder(), dataset)

    current = evaluate_current(dataset, measurement)

    assert current.rule == Rule(MAX_DISTANCE, KEYWORD_MAX_DISTANCE)
    assert set(current.overall) == set(Method)
