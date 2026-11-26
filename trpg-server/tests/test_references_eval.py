# trpg-server/tests/test_references_eval.py

"""
참고 자료의 평가 도구(evals/references/, scripts/eval_references.py)를 검증한다. 모델도 DB 도 쓰지 않는다.

보는 것.
  - 데이터: 저장소의 장면 파일이 읽힌다(정답이 자료에 있다). 틀린 장면은 틀린 곳을 모두 모아 알린다.
  - 검색: 잰 거리로 서버의 규칙과 같이 고르고, 맞힘·정밀도·비우기를 센다. 거리 기준을 바꿔 가며 매긴다.
  - 서술: 장면마다 끈 것과 켠 것을 서술하게 하고, 켠 것에만 참고 자료가 들어간다. 샌 수치와 토큰을 센다.
  - 보고서와 명령줄: --fake 로 끝까지 돈다. 틀린 묶음은 1 로 끝난다.
"""

import math
import uuid
from pathlib import Path

import pytest
from ai_core.fake import FakeEmbedder
from ai_core.provider import ChatMessage, Completion, GenerationParams, ProviderError
from reference_core.records import ReferenceKind, StoredReference
from reference_core.selection import ReferenceThresholds, alias_hits, choose

from app.lore.retrieval import query_text
from app.rounds.narrator import Move, NarrationRequest, StoryContext
from evals.references.dataset import (
    DEFAULT_SCENES,
    Dataset,
    DatasetError,
    Scene,
    SceneKind,
    chosen_sets,
    load_dataset,
)
from evals.references.narration import Mode, Trial, run_pairs, tally
from evals.references.report import ModelResult, best, full_report
from evals.references.runner import (
    Closest,
    Measurement,
    Order,
    alias_distances,
    closest_answer,
    evaluate,
    hit_at,
    measure,
    nearest,
    pick_for,
    score,
    spread,
    sweep,
    sweep_keyword,
    sweep_orders,
)
from scripts import eval_references

STORY = StoryContext(title='평가', rating='all', guide='숲의 모험')
HEADER = """
story: 숲
scenes:
"""


def reference(key: str, name: str, content: str = '', aliases: list[str] | None = None) -> StoredReference:
    return StoredReference(
        id=uuid.uuid5(uuid.NAMESPACE_URL, key),
        key=key,
        name=name,
        aliases=aliases or [],
        content=content,
        kind=ReferenceKind.ITEM,
        source='srd51',
    )


TORCH = reference('equipment/torch', 'Torch', 'A torch burns.')
WOLF = reference('monsters/wolf', 'Wolf', 'A wolf howls.', ['늑대'])
SHIP = reference('equipment/sailing-ship', 'Sailing ship', 'Ship.')


def scene(name: str, text: str, expected: set[str], kind: SceneKind = SceneKind.NAMED) -> Scene:
    request = NarrationRequest(round_number=1, scene=text, moves=[Move('엘프', text)], story=STORY)
    return Scene(name=name, set='v1', kind=kind, request=request, expected=frozenset(expected))


LIGHT = scene('light', '횃불을 켠다', {TORCH.key})
HOWL = scene('howl', '늑대가 운다', {WOLF.key})
MARKET = scene('market', '시장에서 흥정한다', set(), SceneKind.NONE)
SMALL = Dataset(story='숲', scenes=(LIGHT, HOWL, MARKET), references=(TORCH, WOLF, SHIP))
# 장면마다 줄마다의 거리. 횃불 장면은 횃불이 가깝고, 늑대 장면은 아무것도 가깝지 않다(다른 이름으로만 걸린다)
DISTANCES = {
    'light': {TORCH.id: 0.30, WOLF.id: 0.70, SHIP.id: 0.60},
    'howl': {TORCH.id: 0.80, WOLF.id: 0.48, SHIP.id: 0.90},
    'market': {TORCH.id: 0.50, WOLF.id: 0.75, SHIP.id: 0.42},
}
MEASURED = Measurement(model='m', distances=DISTANCES, seconds=0.0)


# --- 데이터 ---


def test_the_scenes_in_the_repository_load():
    dataset = load_dataset()

    kinds = {scene.kind for scene in dataset.scenes}
    assert kinds == set(SceneKind)
    # SRD 5.1 과 위키백과의 줄이 모두 든다. 자료와 한국어 글도 DB 에 넣은 것과 같이 옮긴다
    sources = {reference.source for reference in dataset.references}
    assert sources == {'srd51', 'wikipedia'}
    assert len([reference for reference in dataset.references if reference.source == 'srd51']) == 810
    assert {scene.set for scene in dataset.scenes} == {'v1', 'v2', 'v3'}
    galleon = next(reference for reference in dataset.references if reference.key == 'ko/갈레온')
    assert '갤리온' in galleon.aliases
    english = next(reference for reference in dataset.references if reference.key == 'en/Portcullis')
    assert english.shown_name == '내리닫이 쇠창살' and english.content_ko
    assert all(scene.expected or scene.kind == SceneKind.NONE for scene in dataset.scenes)


def test_a_wrong_scene_is_reported_with_every_problem(tmp_path: Path):
    path = tmp_path / 'scenes.yaml'
    path.write_text(
        HEADER
        + """
  - {name: a, set: v1, kind: named, scene: 장면, moves: [[엘프, 간다]], expected: [monsters/nothing]}
  - {name: a, set: v1, kind: none, scene: 장면, moves: [[엘프, 간다]], expected: [equipment/torch]}
  - {name: b, set: v1, kind: weird, scene: 장면, moves: [[엘프, 간다]]}
  - {name: c, kind: named, moves: [[엘프, 간다]], expected: [equipment/torch]}
""",
        encoding='utf-8',
    )

    with pytest.raises(DatasetError) as caught:
        load_dataset(path)

    problems = caught.value.problems
    assert 'a: 자료에 없는 key monsters/nothing' in problems
    assert 'a: 이름이 겹친다' in problems
    assert sum('none 이면 정답이 비고' in problem for problem in problems) == 2
    assert 'b: kind 가 틀렸다(weird)' in problems
    assert {'c: set 이(가) 없다', 'c: scene 이(가) 없다'} <= set(problems)


def test_sets_can_be_chosen():
    assert chosen_sets(SMALL, None) == SMALL
    assert chosen_sets(SMALL, ['v2']).scenes == ()


# --- 검색 ---


def test_choosing_follows_the_server_rules():
    outcomes = evaluate(SMALL, MEASURED, ReferenceThresholds(max_distance=0.45, keyword_max_distance=0.50))

    # 늑대는 다른 이름으로 걸리고 거리(0.48)가 상한 안이다. 시장은 배가 거리 기준(0.45) 안이라 잘못 고른다
    assert [outcome.chosen for outcome in outcomes] == [[TORCH.key], [WOLF.key], [SHIP.key]]
    result = score(outcomes)
    assert (result.hit, result.precision, result.empty) == (1.0, 2 / 3, 0.0)
    # 다른 이름의 상한을 좁히면 늑대를 놓친다
    strict = score(evaluate(SMALL, MEASURED, ReferenceThresholds(max_distance=0.45, keyword_max_distance=0.40)))
    assert strict.hit == 0.5


def test_the_nearest_comes_first_within_the_limit():
    (market,) = [o for o in evaluate(SMALL, MEASURED, ReferenceThresholds(0.55, limit=1)) if o.scene.name == 'market']

    # 횃불(0.50)과 배(0.42)가 모두 기준 안이다. 한 줄이면 가까운 배다
    assert market.chosen == [SHIP.key]


def test_the_distance_can_be_swept_and_the_best_is_marked():
    swept = sweep(SMALL, MEASURED, ReferenceThresholds())

    by_distance = dict(swept)
    assert by_distance[0.40].empty == 1.0
    assert by_distance[0.45].empty == 0.0
    # 맞힘과 비우기가 모두 좋은 가장 작은 기준이다
    assert best(swept) == 0.30


def test_the_keyword_limit_can_be_swept_and_the_alias_distances_are_shown():
    # 늑대 장면에서 늑대가 다른 이름으로 걸리지만 0.58 로 멀다
    far = Measurement(model='m', distances={**DISTANCES, 'howl': {**DISTANCES['howl'], WOLF.id: 0.58}}, seconds=0)

    by_limit = dict(sweep_keyword(SMALL, far, ReferenceThresholds(max_distance=0.45)))

    assert (by_limit[0.50].hit, by_limit[0.60].hit, by_limit[math.inf].hit) == (0.5, 1.0, 1.0)
    assert alias_distances(HOWL, SMALL, far) == [(WOLF.key, 0.58)]
    assert alias_distances(LIGHT, SMALL, far) == []


# 다른 이름으로 걸린 줄(방패, 도끼)이 자리를 채우면 뜻이 가까운 정답(녹 괴물)이 들어가지 못한다
SHIELD = reference('equipment/shield', 'Shield', 'A shield.', ['방패'])
AXE = reference('equipment/axe', 'Axe', 'An axe.', ['도끼'])
RUST = reference('monsters/rust-monster', 'Rust Monster', 'It eats metal.')
RUSTY = scene('rusty', '방패와 도끼를 든다', {RUST.key}, SceneKind.MEANING)
ARMORY = Dataset(story='숲', scenes=(RUSTY,), references=(SHIELD, AXE, RUST))
ARMORY_MEASURED = Measurement(model='m', distances={'rusty': {SHIELD.id: 0.50, AXE.id: 0.52, RUST.id: 0.35}}, seconds=0)


def test_the_default_order_is_the_servers_choose():
    thresholds = ReferenceThresholds(max_distance=0.45, keyword_max_distance=0.60, limit=2)
    distances = ARMORY_MEASURED.distances['rusty']

    hits = alias_hits(ARMORY.references, query_text(RUSTY.request))
    near = nearest(ARMORY.references, distances, thresholds.max_distance, thresholds.limit)
    server = choose(hits, distances, near, thresholds, thresholds.max_chars)

    assert pick_for(RUSTY, ARMORY.references, distances, thresholds) == server == [SHIELD, AXE]


def test_the_orders_differ_when_the_aliases_fill_the_room():
    thresholds = ReferenceThresholds(max_distance=0.45, keyword_max_distance=0.60, limit=2)

    chosen = {order: evaluate(ARMORY, ARMORY_MEASURED, thresholds, order)[0].chosen for order in Order}

    assert chosen[Order.ALIAS_FIRST] == [SHIELD.key, AXE.key]
    assert chosen[Order.BY_DISTANCE] == [RUST.key, SHIELD.key]
    assert chosen[Order.ALIAS_CAP] == [SHIELD.key, RUST.key]
    swept = sweep_orders(ARMORY, ARMORY_MEASURED, thresholds)
    assert len(swept) == len(Order) * 3
    by = {(order, distance): result for order, distance, result in swept}
    assert (by[(Order.ALIAS_FIRST, 0.40)].hit, by[(Order.BY_DISTANCE, 0.40)].hit) == (0.0, 1.0)


def test_the_closest_answer_and_its_rank():
    assert closest_answer(RUSTY, ARMORY, ARMORY_MEASURED) == Closest(RUST.key, 0.35, 1)
    assert closest_answer(MARKET, SMALL, MEASURED) is None
    # 늑대 장면에서 늑대(0.48)는 횃불(0.80), 배(0.90)보다 가깝다
    assert closest_answer(HOWL, SMALL, MEASURED) == Closest(WOLF.key, 0.48, 1)


def test_hits_without_a_threshold_and_the_spread():
    shifted = Measurement(model='m', distances={**DISTANCES, 'howl': {**DISTANCES['howl'], SHIP.id: 0.40}}, seconds=0)

    assert hit_at(SMALL, MEASURED, 1) == 1.0
    # 늑대 장면에서 배가 더 가까우면 첫째에는 없고 셋 안에는 있다
    assert (hit_at(SMALL, shifted, 1), hit_at(SMALL, shifted, 3)) == (0.5, 1.0)
    spread_of = spread(SMALL, MEASURED)
    assert sorted(spread_of.expected) == [0.30, 0.48]
    assert sorted(spread_of.others) == [0.42, 0.60, 0.80]


async def test_measuring_embeds_every_reference_and_scene():
    embedder = FakeEmbedder()
    ticks = iter([1.0, 3.5])

    measured = await measure(embedder, SMALL, clock=lambda: next(ticks))

    assert set(measured.distances) == {'light', 'howl', 'market'}
    assert set(measured.distances['light']) == {TORCH.id, WOLF.id, SHIP.id}
    assert measured.seconds == 2.5
    assert sum(len(call) for call in embedder.calls) == 6


# --- 서술 ---


class CountingProvider:
    """입력 토큰을 알려 주는 provider. 받은 프롬프트의 글자 수를 토큰으로 친다. fail 이면 실패한다."""

    kind = 'fake'
    model = 'counting'

    def __init__(self, reply: str, fail: bool = False) -> None:
        self.reply = reply
        self.fail = fail
        self.prompts: list[str] = []

    async def complete(self, messages: list[ChatMessage], params: GenerationParams, on_text=None) -> Completion:
        if self.fail:
            raise ProviderError('timeout')
        prompt = '\n'.join(message.content for message in messages)
        self.prompts.append(prompt)
        return Completion(text=self.reply, model=self.model, input_tokens=len(prompt), output_tokens=len(self.reply))


async def test_each_scene_is_narrated_off_and_on():
    provider = CountingProvider('엘프가 횃불을 든다. DC 12 를 넘긴다.')
    seen: list[Trial] = []

    trials = await run_pairs(provider, SMALL, MEASURED, ReferenceThresholds(), repeat=2, on_trial=seen.append)

    assert len(trials) == len(seen) == 3 * 2 * 2
    light_on = [trial for trial in trials if trial.scene_name == 'light' and trial.mode == Mode.ON]
    assert all(trial.references == ['Torch'] for trial in light_on)
    assert all(trial.references == [] for trial in trials if trial.mode == Mode.OFF)
    # 켠 서술의 프롬프트가 더 길다
    off, on = tally(trials, Mode.OFF), tally(trials, Mode.ON)
    assert on.mean_input_tokens is not None and off.mean_input_tokens is not None
    assert on.mean_input_tokens > off.mean_input_tokens
    assert off.leaked == off.runs and on.failed == 0
    assert trials[0].leaked == ['DC 12']


@pytest.mark.parametrize('text', ['횃불은 반경 20피트를 밝힌다.', '3 파운드짜리 망치', '5gp 를 낸다'])
def test_a_measure_from_the_reference_is_counted_as_leaked(text: str):
    trial = Trial('light', 'm', Mode.ON, 1, ['Torch'], text, None, 100, 10)

    assert trial.leaked


async def test_a_clean_narration_is_not_counted_as_leaked():
    trials = await run_pairs(CountingProvider('엘프가 횃불을 든다.'), SMALL, MEASURED, ReferenceThresholds(), repeat=1)

    assert tally(trials, Mode.ON).leaked == 0


async def test_a_failed_narration_is_counted_not_raised():
    trials = await run_pairs(CountingProvider('', fail=True), SMALL, MEASURED, ReferenceThresholds(), repeat=1)

    counted = tally(trials, Mode.ON)
    assert (counted.runs, counted.failed, counted.mean_chars) == (3, 3, None)
    assert trials[0].error == 'timeout'


# --- 보고서와 명령줄 ---


def test_the_report_has_the_tables_and_the_scenes():
    outcomes = evaluate(SMALL, MEASURED, ReferenceThresholds())
    swept = sweep(SMALL, MEASURED, ReferenceThresholds())
    trial = Trial('light', 'm', Mode.ON, 1, ['Torch'], 'DC 12 의 횃불', None, 100, 10)

    report = full_report(SMALL, [ModelResult(MEASURED, outcomes, swept)], ReferenceThresholds(), [trial])
    plain = full_report(SMALL, [ModelResult(MEASURED, outcomes, swept)], ReferenceThresholds())

    assert '## m' in report and '0.30 (가장 나음)' in report
    assert '| light O |' in report and '| market X |' not in report
    assert '**수치가 샜다**: DC 12' in report
    assert '## 켠 서술과 끈 서술' not in plain
    # 머리말은 자료마다 센다. 다른 이름의 상한을 재지 않았으면 그 표가 없다
    assert '자료 3줄(SRD 5.1 3줄)' in report
    assert '다른 이름의 상한을 바꿔 가며' not in report
    assert f'| {WOLF.key} 0.480 |' in report


def test_the_report_marks_an_alias_cut_by_the_keyword_limit():
    far = Measurement(model='m', distances={**DISTANCES, 'howl': {**DISTANCES['howl'], WOLF.id: 0.58}}, seconds=0)
    thresholds = ReferenceThresholds(keyword_max_distance=0.50)
    result = ModelResult(
        far, evaluate(SMALL, far, thresholds), sweep(SMALL, far, thresholds), sweep_keyword(SMALL, far, thresholds)
    )

    report = full_report(SMALL, [result], thresholds)

    assert f'{WOLF.key} 0.580 (뺌)' in report
    assert '**다른 이름의 상한을 바꿔 가며**' in report and '| 없음 |' in report


def test_the_report_has_the_orders_and_the_closest_answer():
    thresholds = ReferenceThresholds(keyword_max_distance=0.60, limit=2)
    result = ModelResult(
        ARMORY_MEASURED,
        evaluate(ARMORY, ARMORY_MEASURED, thresholds),
        sweep(ARMORY, ARMORY_MEASURED, thresholds),
        order_swept=sweep_orders(ARMORY, ARMORY_MEASURED, thresholds),
    )

    report = full_report(ARMORY, [result], thresholds)

    assert '**넣는 차례를 바꿔 가며**' in report
    assert '| 거리 순 | 0.40 | 100% |' in report and '| 다른 이름 먼저(지금) | 0.40 | 0% |' in report
    assert f'{RUST.key} 0.350 (1번째)' in report


def test_the_fake_run_goes_to_the_end(tmp_path: Path, capsys: pytest.CaptureFixture):
    out = tmp_path / 'report.md'

    code = eval_references.main(['--fake', '--narrate', '--set', 'v1', '--out', str(out)])

    assert code == 0
    assert out.read_text(encoding='utf-8').startswith('# 참고 자료 평가')
    assert 'torch-cave on 1회' in capsys.readouterr().out


def test_an_unknown_set_ends_with_one(capsys: pytest.CaptureFixture):
    assert eval_references.main(['--fake', '--set', 'v9']) == 1
    assert '그 묶음의 장면이 없다' in capsys.readouterr().err


def test_the_threshold_comes_from_the_command_line():
    arguments = eval_references.read_arguments(['--fake', '--max-distance', '0.6'])

    assert eval_references.thresholds_of(arguments).max_distance == 0.6
    assert eval_references.read_arguments([]).scenes == DEFAULT_SCENES
