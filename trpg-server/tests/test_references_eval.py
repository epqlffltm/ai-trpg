# trpg-server/tests/test_references_eval.py

"""
참고 자료의 평가 도구(evals/references/, scripts/eval_references.py)를 검증한다. 모델도 DB 도 쓰지 않는다.

보는 것.
  - 데이터: 저장소의 장면 파일이 읽힌다(정답이 자료에 있다). 틀린 장면은 틀린 곳을 모두 모아 알린다.
  - 검색: 잰 거리로 서버의 규칙과 같이 고르고, 맞힘·정밀도·비우기를 센다. 거리 기준을 바꿔 가며 매긴다.
  - 서술: 장면마다 끈 것과 켠 것을 서술하게 하고, 켠 것에만 참고 자료가 들어간다. 샌 수치와 토큰을 센다.
  - 보고서와 명령줄: --fake 로 끝까지 돈다. 틀린 묶음은 1 로 끝난다.
"""

import uuid
from pathlib import Path

import pytest
from ai_core.fake import FakeEmbedder
from ai_core.provider import ChatMessage, Completion, GenerationParams, ProviderError

from app.references.records import ReferenceKind, StoredReference
from app.references.retrieval import ReferenceThresholds
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
from evals.references.runner import Measurement, evaluate, hit_at, measure, score, spread, sweep
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
    assert len(dataset.references) == 810
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
    assert on.mean_input_tokens > off.mean_input_tokens
    assert off.leaked == off.runs and on.failed == 0
    assert trials[0].leaked == ['DC 12']


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
