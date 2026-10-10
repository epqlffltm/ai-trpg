# game-server/tests/test_memory_eval.py

"""
지난 일 검색의 평가 도구(evals/memory, scripts/eval_memory.py)를 검증한다. 임베딩 모델은 가짜다.

보는 것은 셋이다.
  - 평가 데이터를 읽고, 실수(고를 수 없는 라운드를 정답으로 적음 등)를 모두 잡는다. 실제 데이터 파일도 늘 읽어 본다.
  - 고르는 것은 서버의 규칙 그대로다. 거리 기준을 바꿔 가며 다시 매겨도 모델을 다시 부르지 않는다.
  - 보고서가 만들어지고, 스크립트가 가짜 임베더로 끝까지 돈다.
"""

import argparse
import copy
import math

import pytest

from app.ai.fake import FakeEmbedder
from app.assets.models import LoreKind
from app.lore.retrieval import query_text
from app.memory import history
from app.memory.retrieval import MemoryThresholds, choose_memories, eligible, people_in
from evals.lore.dataset import DatasetError, Kind
from evals.memory.dataset import DEFAULT_PATH, find_problems, load_dataset, parse_dataset
from evals.memory.report import full_report, miss_lines
from evals.memory.runner import (
    DISTANCE_SWEEP,
    GATE_SWEEP,
    Measurement,
    best,
    evaluate,
    history_outcomes,
    history_recall,
    measure,
    split_distances,
    sweep,
)
from scripts import eval_memory


def small_document() -> dict:
    """작은 평가 문서. 라운드 여섯(기억 다섯), 질의 셋."""
    rounds = [
        {'number': 1, 'scene': '출발선.', 'lines': ['카이: 달린다.']},
        {'number': 2, 'scene': '악역영애가 웃었다.', 'lines': ['모모: 인사한다.']},
        {'number': 3, 'scene': '차단기가 부서졌다.', 'lines': []},
        {'number': 4, 'scene': '비가 왔다.', 'lines': ['카이: 우산을 편다.']},
        {'number': 5, 'scene': '해가 떴다.'},
        {'number': 6, 'scene': '결승선이 보였다.'},
    ]
    return {
        'title': '작은 추격전',
        'people': [{'name': '비올레타', 'keywords': ['악역영애']}],
        'rounds': rounds,
        'queries': [
            {'id': 'a1', 'kind': 'name', 'round': 6, 'scene': '악역영애가 다시 웃는다.', 'expected': [1]},
            {'id': 'a2', 'kind': 'meaning', 'round': 7, 'scene': '부서진 차단기.', 'expected': [2]},
            {'id': 'a3', 'kind': 'none', 'round': 7, 'scene': '하품을 한다.', 'expected': []},
        ],
        # 7 라운드에 모을 수 있는 서술은 2, 3 라운드의 장면이다. 차단기의 문장에는 악역영애의 이름이 없다
        'histories': [{'id': 'h1', 'person': '비올레타', 'round': 7, 'expected': ['악역영애가 웃었다', '차단기가']}],
    }


def broken(change) -> list[str]:
    document = copy.deepcopy(small_document())
    change(document)
    return find_problems(document)


# --- 데이터 ---


def test_the_real_dataset_has_no_problems():
    dataset = load_dataset(DEFAULT_PATH)

    assert len(dataset.memories) == 19
    assert len(dataset.queries) >= 18
    assert {query.kind for query in dataset.queries} == set(Kind)
    assert len(dataset.histories) >= 4


def test_the_real_dataset_keeps_private_settings_out():
    assert '가나폴리' not in DEFAULT_PATH.read_text(encoding='utf-8')


def test_a_document_becomes_people_memories_and_queries():
    dataset = parse_dataset(small_document())

    assert [person.name for person in dataset.people] == ['비올레타']
    assert dataset.people[0].kind == LoreKind.PERSON
    # 다음 라운드가 있는 라운드만 기억이 된다. 기억 1 은 1 라운드에 한 말과 2 라운드의 장면이다
    assert [memory.number for memory in dataset.memories] == [1, 2, 3, 4, 5]
    assert (dataset.memories[0].lines, dataset.memories[0].result) == (('카이: 달린다.',), '악역영애가 웃었다.')
    first = dataset.queries[0]
    assert (first.request.round_number, first.expected) == (6, frozenset({'1'}))


def test_a_good_document_has_no_problems():
    assert find_problems(small_document()) == []


@pytest.mark.parametrize(
    ('change', 'expected'),
    [
        # 6 라운드의 지난 기록은 3~5 라운드다. 기억 3 은 고를 수 없다
        (lambda d: d['queries'][0].update(expected=[3]), '고를 수 없는 기억을 정답으로'),
        (lambda d: d['queries'][0].update(expected=[9]), '고를 수 없는 기억을 정답으로'),
        (lambda d: d['queries'][0].update(expected=['1']), '라운드 번호의 목록'),
        (lambda d: d['queries'][2].update(expected=[1]), '정답이 비어 있어야'),
        (lambda d: d['queries'][1].update(expected=[]), '정답이 없다'),
        (lambda d: d['queries'][0].update(round=9), 'round 는 1 부터 7 까지'),
        (lambda d: d['queries'][0].pop('round'), 'round 는'),
        (lambda d: d['queries'][0].update(kind='guess'), 'kind 는'),
        (lambda d: d['queries'][0].pop('scene'), 'scene 가 없다'),
        (lambda d: d['queries'][0].update(moves=[{'content': '누가?'}]), 'moves 는'),
        (lambda d: d['queries'][1].update(id='a1'), '질의 id 가 겹친다: a1'),
        (lambda d: d['rounds'][2].update(number=4), 'number 는 3 여야'),
        (lambda d: d['rounds'][0].update(scene=' '), 'scene 이 없다'),
        (lambda d: d['rounds'][0].update(lines='카이: 달린다.'), 'lines 는 글의 목록'),
        (lambda d: d['people'].append({'name': '비올레타'}), '인물 이름이 겹친다'),
        (lambda d: d['people'].append({'keywords': []}), 'name 이 없다'),
        (lambda d: d['people'][0].update(keywords='악역영애'), 'keywords 는 글의 목록'),
        (lambda d: d['histories'][0].update(person='토르빈'), 'person 은 people 의 이름'),
        (lambda d: d['histories'][0].update(round=8), 'round 는 1 부터 7 까지'),
        (lambda d: d['histories'][0].update(expected=[]), 'expected 는 빈 글이 아닌'),
        (lambda d: d['histories'][0].update(expected=['']), 'expected 는 빈 글이 아닌'),
        # 4 라운드의 장면은 7 라운드의 지난 기록(4~6 라운드)에 있다. 이력으로 모으지 않는다
        (lambda d: d['histories'][0].update(expected=['비가 왔다']), '모을 수 있는 서술에 없는 문장(비가 왔다)'),
        (lambda d: d['histories'][0].update(expected=['출발선']), '모을 수 있는 서술에 없는 문장(출발선)'),
        (lambda d: d['histories'].append({**d['histories'][0]}), '이력 질의 id 가 겹친다: h1'),
        (lambda d: d.update(histories='h1'), 'histories 는 목록'),
    ],
)
def test_mistakes_are_found(change, expected: str):
    problems = broken(change)

    assert any(expected in problem for problem in problems), problems


@pytest.mark.parametrize('document', [None, [], {'rounds': '출발선', 'people': [], 'queries': []}])
def test_a_document_of_the_wrong_shape_is_a_problem(document):
    assert find_problems(document)


def test_a_broken_document_is_not_read():
    with pytest.raises(DatasetError):
        parse_dataset({**small_document(), 'queries': [{'id': 'x'}]})


# --- 재고 매기기 ---


async def test_every_query_is_measured_against_every_memory():
    dataset = parse_dataset(small_document())
    embedder = FakeEmbedder()

    measurement = await measure(embedder, dataset)

    assert set(measurement.distances) == {'a1', 'a2', 'a3'}
    assert all(set(distances) == {1, 2, 3, 4, 5} for distances in measurement.distances.values())
    # 기억은 한 묶음으로, 질의는 하나씩 보낸다(서버도 찾는 글을 하나씩 보낸다)
    assert [len(texts) for texts in embedder.calls] == [5, 1, 1, 1]


async def test_choosing_is_the_server_rule():
    dataset = load_dataset(DEFAULT_PATH)
    measurement = await measure(FakeEmbedder(), dataset)
    thresholds = MemoryThresholds(max_distance=0.5, keyword_max_distance=0.6)

    evaluation = evaluate(dataset, measurement, thresholds)

    for outcome in evaluation.outcomes:
        request = outcome.query.request
        expected = choose_memories(
            eligible(dataset.memories, request.round_number),
            people_in(dataset.people, query_text(request)),
            measurement.distances[outcome.query.id],
            thresholds,
        )
        assert outcome.chosen == [str(memory.number) for memory in expected]


async def test_sweeping_does_not_call_the_model_again():
    dataset = parse_dataset(small_document())
    embedder = FakeEmbedder()
    measurement = await measure(embedder, dataset)
    calls = len(embedder.calls)

    swept = sweep(dataset, measurement)

    assert len(swept) == len(DISTANCE_SWEEP) * len(GATE_SWEEP)
    assert len(embedder.calls) == calls


def test_the_best_prefers_f1_then_recall_then_the_narrower_rule():
    dataset = parse_dataset(small_document())
    # 기억 1 은 a1 의 정답이고 가깝다. 나머지는 멀다
    distances = {'a1': {1: 0.2, 2: 0.9, 3: 0.9, 4: 0.9, 5: 0.9}, 'a2': {}, 'a3': {}}
    measurement = Measurement('test', distances)

    chosen = best(sweep(dataset, measurement))

    # 기준이 달라도 고르는 것이 같으면 점수가 같다. 그때는 좁은 기준을 고른다
    assert chosen.thresholds.max_distance == min(DISTANCE_SWEEP)
    assert chosen.thresholds.keyword_max_distance == min(GATE_SWEEP)


def test_distances_are_split_into_right_and_other_among_choosable_memories():
    dataset = parse_dataset(small_document())
    distances = {
        'a1': {1: 0.1, 2: 0.5, 3: 0.6, 4: 0.7, 5: 0.8},
        'a2': {1: 0.2, 2: 0.3, 3: 0.6, 4: 0.7, 5: 0.8},
        'a3': {1: 0.4, 2: 0.4, 3: 0.6, 4: 0.7, 5: 0.8},
    }

    right, other = split_distances(dataset, Measurement('test', distances))

    # a1(6 라운드)은 기억 1, 2 만, a2·a3(7 라운드)은 1~3 을 고를 수 있다
    assert sorted(right) == [0.1, 0.3]
    assert sorted(other) == [0.2, 0.4, 0.4, 0.5, 0.6, 0.6]


# --- 인물의 이력 ---


def test_a_history_outcome_tells_found_from_missed_for_want_of_a_name():
    dataset = parse_dataset(small_document())

    (outcome,) = history_outcomes(dataset)

    assert [line.text for line in outcome.chosen] == ['악역영애가 웃었다.']
    assert (outcome.found, outcome.unnamed, outcome.cut) == (['악역영애가 웃었다'], ['차단기가'], [])
    assert history_recall([outcome]) == 0.5


def test_a_named_line_pushed_out_by_the_limit_is_cut(monkeypatch: pytest.MonkeyPatch):
    document = small_document()
    document['rounds'][2]['scene'] = '악역영애가 차단기를 부쉈다.'
    document['histories'][0]['expected'] = ['악역영애가 웃었다', '악역영애가 차단기를']
    monkeypatch.setattr(history, 'HISTORY_LINES', 1)

    (outcome,) = history_outcomes(parse_dataset(document))

    # 최근 것(3 라운드의 장면)만 남는다. 앞의 것은 이름이 있지만 상한에 밀렸다
    assert (outcome.found, outcome.unnamed, outcome.cut) == (['악역영애가 차단기를'], [], ['악역영애가 웃었다'])


def test_no_history_queries_count_nothing():
    assert history_recall([]) is None


# --- 보고서와 스크립트 ---


async def test_the_report_has_the_current_rule_the_distances_the_sweep_and_the_misses():
    dataset = load_dataset(DEFAULT_PATH)
    result = await eval_memory.evaluate_model(FakeEmbedder(), dataset, MemoryThresholds())

    report = full_report(dataset, [result])

    assert report.startswith(f'# 지난 일 검색 평가: {dataset.title}')
    headings = (
        '### 지금 서버의 기준',
        '#### 지금 기준에서 틀린 질의',
        '### 거리 분포',
        '### 기준을 바꿔 가며',
        '가장 나은 기준:',
        '### 가장 나은 기준에서 틀린 질의',
        '## 인물의 이력(모델 없음)',
        '### 이름이나 키워드가 없어 놓친 문장',
    )
    for heading in headings:
        assert heading in report


def test_misses_name_what_was_expected_and_what_was_chosen():
    dataset = parse_dataset(small_document())
    distances = {'a1': {1: 0.9, 2: 0.9}, 'a2': {}, 'a3': {}}
    thresholds = MemoryThresholds(max_distance=0.5, keyword_max_distance=math.inf)

    lines = miss_lines(evaluate(dataset, Measurement('test', distances), thresholds))

    # a1 은 인물(악역영애)로 기억 1 을 고른다. a2 는 거리를 몰라 아무것도 고르지 못한다
    assert lines == ['- a2(meaning, 7 라운드): 정답 2 / 고름 없음']


async def test_the_script_runs_with_the_fake_embedder():
    arguments = argparse.Namespace(fake=True, data=DEFAULT_PATH, model=None, base_url=None, out=None)

    report = await eval_memory.run(arguments)

    assert '## fake' in report


def test_failures_are_one_line_without_the_answer():
    assert eval_memory.failure_message(DatasetError(['틀렸다'])) == '평가 데이터가 틀렸다.\n틀렸다'
    assert 'timeout' in eval_memory.failure_message(Exception('timeout'))
