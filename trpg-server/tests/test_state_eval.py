# trpg-server/tests/test_state_eval.py

"""
상태 지키기 평가 도구(evals/state, scripts/eval_state.py)를 검증한다. 모델을 부르지 않는다.

보는 것은 넷이다.
  - 검사: 금지한 낱말, 꼭 나올 낱말, 따옴표 속 글(짧은 소리까지 센다), 어느 장면에나 보는 의심거리.
    퀘스트의 기한의 낱말(서두름, 놓침)은 기한이 다 됐거나 끝을 맺은 표현만 센다(측정의 장면을 읽고 정했다).
  - 장면: 서버의 조립을 거쳐 프롬프트가 만들어진다. 금지한 낱말이 프롬프트에 먼저 있지 않다(있으면 검사가 뜻이 없다).
    진짜 이름은 GM 메모에만 있다. 말을 못 하게 한 장면에는 말할 수 있는 NPC 가 없다. 판정의 성패가 장면의 뜻과 맞다.
  - 돌리기: 가짜 provider 로 서술하고 검사한다. provider 의 실패와 잘린 답도 결과에 적고 멈추지 않는다.
  - 보고서와 스크립트: 걸린 수를 세고, 스크립트가 가짜로 끝까지 돈다. 남긴 보고서를 다시 읽어 지금의 검사로 다시 센다.
"""

import argparse
import re
from dataclasses import replace

import pytest
from ai_core.fake import FakeProvider
from ai_core.provider import ChatMessage, Completion, GenerationParams, ProviderError, Reasoning, TextSink, ignore_text

from app.rounds import prompt
from app.rounds.cast import CONDITIONS
from app.rounds.llm_narrator import NARRATION_PARAMS
from app.rounds.narrator import Move
from app.rounds.prompt import build_messages
from evals.lore.narration import prompt_text
from evals.state import cases
from evals.state.cases import CASES, HIDDEN_NAME, TRUE_NAME
from evals.state.checks import Finding, Forbid, NoSpeech, Pattern, Require, general_hints, run_checks
from evals.state.report import full_report, read_report, tally_lines, total_line
from evals.state.runner import inspect, narrate, rescore, run_cases
from scripts import eval_state

BY_NAME = {case.name: case for case in CASES}
# 상태를 어기지 않은 장면. 쓰러진 악역영애는 말이 없고, 진짜 이름도 숨긴 설정도 없다
QUIET = '리엔의 주먹에 악역영애가 쓰러졌다. 토르빈이 바닥에 떨어진 부채를 집어 들었다. 쿵, 하고 리무진의 문이 닫혔다.'


def without_secrets(move: Move) -> Move:
    """서 있는 곳의 숨은 길을 지운 한 일. 숨은 길은 GM 만 보는 맵 절에 들어간다."""
    if move.place is None:
        return move
    return replace(move, place=replace(move.place, hidden=[]))


def prompt_of(case: cases.StateCase, without_memo: bool = False) -> str:
    """
    장면의 프롬프트 전부를 한 글로. without_memo 면 GM 만 아는 것(GM 메모, 맵의 숨은 길)을 비운다.
    """
    request = case.request
    if without_memo:
        moves = [without_secrets(move) for move in request.moves]
        request = replace(request, story=replace(request.story, gm_notes=''), moves=moves)
    return prompt_text(build_messages(request))


# --- 검사 ---


def test_forbidden_words_are_caught():
    assert Forbid('x', ('비올레타', '끄나풀')).violations('비올레타가 웃었다.') == ['비올레타']
    assert Forbid('x', ('비올레타',)).violations(QUIET) == []


def test_required_words_pass_when_any_appears():
    assert Require('x', ('팔', '골절')).violations('부러진 팔이 욱신거렸다.') == []
    assert Require('x', ('팔', '골절')).violations(QUIET) == ['팔/골절 없음']


@pytest.mark.parametrize(
    ('scene', 'caught'),
    [
        ('악역영애가 "아직이야." 하고 말했다.', ['아직이야.']),
        ('“이건 끝이 아니야”라는 말이 들렸다.', ['이건 끝이 아니야']),
        # 의식이 없는 NPC 는 신음도 못 내고, PC 의 소리도 따옴표로 쓰지 않는다
        ('"윽!" 하는 소리가 났다.', ['윽!']),
        (QUIET, []),
    ],
)
def test_every_quoted_text_is_caught(scene: str, caught: list[str]):
    assert NoSpeech('x').violations(scene) == caught


def test_a_pattern_is_caught_once_per_text():
    check = Pattern('x', re.compile(r'\d+시'))

    assert check.violations('22시가 지나고 22시의 바람이 불었다. 23시였다.') == ['22시', '23시']
    assert check.violations(QUIET) == []


@pytest.mark.parametrize(
    ('scene', 'caught'),
    [
        # narration-23 을 재 본 장면에서 옮겼다
        ('3일째 22시 20분, 밤의 어둠이 짙게 깔린 고속도로', ['3일째', '22시', '20분']),
        ('시간이 흘러 13시 10분이 되었을 때', ['13시', '10분']),
        ('10분의 시간이 흐른 뒤', ['10분']),
        ('밤 10시 20분의 고속도로', ['10시', '20분']),
        # 시각이 아닌 숫자와, 숫자 없는 때의 말은 걸리지 않는다
        ('17번째 행성의 정오를 갓 지난 열기', []),
        ('새벽빛이 내려앉았다. 밤새 비바람이 몰아쳤다.', []),
    ],
)
def test_clock_digits_are_caught(scene: str, caught: list[str]):
    assert cases.CLOCK_DIGITS.violations(scene) == caught


@pytest.mark.parametrize(
    ('scene', 'passed'),
    [
        # narration-41, 42 를 재 본 장면에서 옮겼다. 기한이나 기회가 다 됐다는 표현은 센다
        ('도난당한 엔진의 행방을 쫓는 시간은 이제 얼마 남지 않았다.', True),
        ('도주하는 불빛이 멀어지는 만큼 시간의 끝이 코앞까지 다가오고 있었다.', True),
        ('놓치면 다시는 기회가 오지 않을 것 같은 예감이 심장을 두드렸다.', True),
        # 기한과 상관없는 압박감과 그냥 쫓는 장면은 세지 않는다
        ('길 위로 드리워진 그림자는 조금씩 길을 가로막으며 기묘한 압박감을 더했다.', False),
        ('리엔은 앞선 바이크가 남긴 자국을 놓치지 않으려 시선을 고정했다.', False),
    ],
)
def test_hurry_counts_only_a_deadline_running_out(scene: str, passed: bool):
    (finding,) = run_checks(scene, (Require('서두름', cases.HURRY_WORDS),))

    assert finding.passed is passed


@pytest.mark.parametrize(
    ('scene', 'passed'),
    [
        # 일이 틀어졌다고 맺은 장면은 센다
        ('리엔의 시선이 닿는 곳에는 더 이상 되찾을 수 없는 빈자리만이 남겨져 있었다.', True),
        ('잡아야 했던 기회는 이미 저 멀리 은하의 너머로 흘러가 버렸다.', True),
        # 아직 쫓는 장면은 세지 않는다
        ('멀어지는 화물선의 거대한 실루엣을 향해 바이크는 궤적을 그리며 질주했다.', False),
        ('잡을 수 있을 것 같으면서도 결코 닿지 않을 듯한 거리였다.', False),
    ],
)
def test_lost_counts_only_an_ending(scene: str, passed: bool):
    (finding,) = run_checks(scene, (Require('놓침', cases.LOST_WORDS),))

    assert finding.passed is passed


def test_checks_run_in_order_and_report_passing():
    findings = run_checks('비올레타가 웃었다.', (Require('팔', ('팔',)), Forbid('이름', ('비올레타',))))

    assert [finding.label for finding in findings] == ['팔', '이름']
    assert [finding.passed for finding in findings] == [False, False]
    assert Finding('x', ()).passed


def test_general_hints_find_made_up_numbers_foreign_letters_and_markdown():
    hints = general_hints('**리엔**이 77 미터를 달렸다. 速度 speed', prompt='리엔 17')

    assert hints == ['보낸 적 없는 숫자(77)', '한자 2자', '영어 낱말 1개', '마크다운']
    assert general_hints('리엔이 17 번째 행성에 닿았다.', prompt='리엔 17') == []


# --- 장면 ---


def test_case_names_are_unique():
    assert len(BY_NAME) == len(CASES)
    assert tuple(BY_NAME) == cases.CASE_NAMES


@pytest.mark.parametrize('case', CASES, ids=lambda case: case.name)
def test_every_case_builds_a_prompt_with_its_moves(case: cases.StateCase):
    text = prompt_of(case)

    assert prompt.PROMPT_VERSION == 'narration-50'
    assert all(move.content in text for move in case.request.moves)


@pytest.mark.parametrize('case', CASES, ids=lambda case: case.name)
def test_forbidden_words_are_not_in_the_prompt_outside_the_memo(case: cases.StateCase):
    text = prompt_of(case, without_memo=True)
    forbidden = [word for check in case.checks if isinstance(check, Forbid) for word in check.words]

    # 프롬프트에 이미 있는 낱말을 금지하면 따라 쓴 것과 어긴 것을 가를 수 없다
    assert [word for word in forbidden if word in text] == []


@pytest.mark.parametrize('case', [case for case in CASES if HIDDEN_NAME in case.checks], ids=lambda case: case.name)
def test_the_true_name_is_only_in_the_memo(case: cases.StateCase):
    assert TRUE_NAME in prompt_of(case)
    assert TRUE_NAME not in prompt_of(case, without_memo=True)


@pytest.mark.parametrize(
    'case', [case for case in CASES if cases.HIDDEN_PLACE in case.checks], ids=lambda case: case.name
)
def test_the_hidden_place_is_only_in_the_map_for_the_gm(case: cases.StateCase):
    text = prompt_of(case)

    # 숨은 장소의 이름은 맵 절의 "숨은 길(플레이어는 모름, 실마리로만)" 에만 있다. 한 일의 줄에는 없다
    assert f'실마리로만): {cases.HIDDEN_PLACE_NAME}' in text
    assert prompt.MAP_NOTE in text
    assert cases.HIDDEN_PLACE_NAME not in prompt_of(case, without_memo=True)


def test_the_map_cases_cover_hiding_searching_and_travelling():
    map_cases = [case.name for case in CASES if case.name.startswith('map_')]

    assert map_cases == ['map_hidden', 'map_search_failed', 'map_search_found', 'map_travel', 'map_travel_failed']
    # 찾은 장면에서만 숨었던 장소의 이름이 나와도 된다(나와야 한다)
    assert cases.HIDDEN_PLACE not in BY_NAME['map_search_found'].checks
    assert '(찾기: 찾은 것이 없다)' in prompt_of(BY_NAME['map_search_failed'])
    assert '(가려던 곳: 주유소. 그쪽으로 이어진 길이 없었다)' in prompt_of(BY_NAME['map_travel_failed'])


def test_the_found_case_carries_the_found_route_and_its_rule():
    text = prompt_of(BY_NAME['map_search_found'])

    assert f'(찾기: 길을 찾아냈다. {cases.HIDDEN_PLACE_NAME}(으)로 이어진다)' in text
    assert prompt.FOUND_NOTE in text
    # 찾은 길은 출구다. 숨은 길로 다시 적히지 않는다
    assert '실마리로만)' not in text


@pytest.mark.parametrize(
    'case', [case for case in CASES if cases.NO_HIDDEN_HINT in case.checks], ids=lambda case: case.name
)
def test_hints_are_forbidden_only_where_nothing_is_hidden(case: cases.StateCase):
    # 숨은 길이 있는 장소에서는 실마리가 맞는 서술이다. 그런 장면에 이 검사를 걸면 잘한 것을 어겼다고 센다
    assert all(not move.place.hidden for move in case.request.moves if move.place is not None)


def test_the_right_naming_reveals_the_name_everywhere_it_is_used():
    case = BY_NAME['naming_right']

    assert HIDDEN_NAME not in case.checks
    assert [person.name for person in case.request.people] == [TRUE_NAME]
    assert [note.name for note in case.request.lore] == [TRUE_NAME]
    assert '→ 지목 맞음: 악역영애의 진짜 이름은 비올레타' in prompt_of(case)


def test_the_wrong_naming_carries_the_rule_line():
    text = prompt_of(BY_NAME['naming_wrong'])

    assert "→ 지목 틀림: 악역영애의 진짜 이름은 '로즈'(이)가 아니다" in text
    assert prompt.NAMING_NOTE in text


@pytest.mark.parametrize('case', [case for case in CASES if cases.SILENT in case.checks], ids=lambda case: case.name)
def test_silent_cases_have_no_npc_who_can_speak(case: cases.StateCase):
    # 따옴표를 모두 세는 장면에는 말할 수 있는 NPC 가 없어야 한다(쓰러졌거나, 죽었거나, 아무도 없다)
    assert all(person.condition in CONDITIONS.values() for person in case.request.people)


def test_the_silent_cases_are_the_ones_without_a_speaker():
    silent = [case.name for case in CASES if cases.SILENT in case.checks]

    assert silent == ['downed_npc', 'dead_npc', 'treatment_healed', 'treatment_worse']


def test_the_lore_entry_is_only_given_when_the_lady_is_in_the_scene():
    for case in CASES:
        assert bool(case.request.lore) == bool(case.request.people)


@pytest.mark.parametrize(
    ('name', 'success'),
    [('downed_npc', True), ('injured_pc', False), ('injured_npc', True), ('treatment_healed', True)],
)
def test_the_verdicts_match_the_story_of_the_case(name: str, success: bool):
    verdicts = [move.verdict for move in BY_NAME[name].request.moves if move.verdict is not None]

    assert [verdict.success for verdict in verdicts] == [success]
    assert all(verdict.total == verdict.roll + verdict.modifier for verdict in verdicts)


def test_the_failed_treatment_is_a_failure():
    (verdict,) = [move.verdict for move in BY_NAME['treatment_worse'].request.moves if move.verdict is not None]

    assert not verdict.success
    assert verdict.treatment.mishap == 'worsen'


def test_injuries_come_from_the_template():
    assert cases.injury_note('broken_arm').name == '팔 골절'
    assert cases.injury_note('lost_eye').fact.startswith('한쪽 눈')


# --- 돌리기 ---


class BrokenProvider:
    """늘 실패하는 provider."""

    kind = 'fake'
    model = 'broken'

    async def complete(
        self, messages: list[ChatMessage], params: GenerationParams, on_text: TextSink = ignore_text
    ) -> Completion:
        raise ProviderError('unreachable')


async def test_a_scene_is_narrated_and_inspected():
    provider = FakeProvider(reply=QUIET)
    case = BY_NAME['downed_npc']

    trial = inspect(await narrate(provider, case, 1, Reasoning.LOW), case)

    assert trial.scene == QUIET
    assert trial.broken == ()
    assert [finding.label for finding in trial.findings] == [check.label for check in case.checks]
    # 서버와 같은 생성 설정과 조립으로 부른다
    (call,) = provider.calls
    assert call.messages == build_messages(case.request)
    assert call.params == replace(NARRATION_PARAMS, reasoning=Reasoning.LOW)


async def test_a_broken_scene_is_caught():
    case = BY_NAME['downed_npc']
    trial = inspect(await narrate(FakeProvider(reply=eval_state.FAKE_SCENE), case, 1, Reasoning.NONE), case)

    assert {finding.label for finding in trial.broken} == {'따옴표 속 말', '깨어 있음', '진짜 이름'}


async def test_failures_are_written_down_and_not_inspected():
    case = BY_NAME['naming_wrong']

    failed = inspect(await narrate(BrokenProvider(), case, 1, Reasoning.NONE), case)
    cut = inspect(await narrate(FakeProvider(reply=QUIET, truncated=True), case, 2, Reasoning.NONE), case)

    assert (failed.scene, failed.problem, failed.findings) == (None, 'provider 실패: unreachable', ())
    assert cut.problem == '장면으로 받지 않음: cut_off'
    assert cut.findings == ()


async def test_every_case_is_run_repeat_times_in_order():
    seen = []

    trials = await run_cases(FakeProvider(reply=QUIET), CASES[:2], 3, on_trial=seen.append)

    assert [(trial.case, trial.attempt) for trial in trials] == [
        ('downed_npc', 1),
        ('downed_npc', 2),
        ('downed_npc', 3),
        ('dead_npc', 1),
        ('dead_npc', 2),
        ('dead_npc', 3),
    ]
    assert seen == trials


# --- 보고서와 스크립트 ---


async def test_the_report_counts_caught_checks_per_case():
    case = BY_NAME['downed_npc']
    good = inspect(await narrate(FakeProvider(reply=QUIET), case, 1, Reasoning.NONE), case)
    bad = inspect(await narrate(FakeProvider(reply=eval_state.FAKE_SCENE), case, 2, Reasoning.NONE), case)
    failed = await narrate(BrokenProvider(), case, 3, Reasoning.NONE)

    lines = tally_lines([good, bad, replace(failed, model='fake')])
    report = full_report([good, bad])

    assert lines[2] == '| fake | downed_npc | 3 | 1 | 따옴표 속 말 1/2, 깨어 있음 1/2, 진짜 이름 1/2, 숨긴 설정 0/2 |'
    assert total_line([good, bad, failed]) == '받은 장면 2개 중 검사에 걸린 장면 1개, 실패 1개'
    assert '- 걸림: 진짜 이름(비올레타)' in report
    assert QUIET in report


def test_cases_keep_their_written_order():
    assert [case.name for case in eval_state.chosen_cases(['naming_right', 'downed_npc'])] == [
        'downed_npc',
        'naming_right',
    ]


async def test_the_script_runs_with_the_fake_provider(tmp_path):
    arguments = argparse.Namespace(fake=True, case=['naming_wrong'], repeat=2, reasoning='none', out=None, rescore=None)

    trials = await eval_state.run_all(arguments)

    assert [(trial.case, trial.model) for trial in trials] == [('naming_wrong', 'fake'), ('naming_wrong', 'fake')]
    assert all(trial.broken for trial in trials)


# --- 다시 세기 ---


async def test_a_saved_report_is_read_back_with_its_scenes():
    case = BY_NAME['treatment_healed']
    long = f'{QUIET}\n\n"천박하기 짝이 없군요."'
    trials = [
        inspect(await narrate(FakeProvider(reply=long), case, 1, Reasoning.NONE), case),
        await narrate(BrokenProvider(), case, 2, Reasoning.NONE),
    ]

    read = read_report(full_report(trials))

    assert [(trial.case, trial.attempt, trial.model) for trial in read] == [
        ('treatment_healed', 1, 'fake'),
        ('treatment_healed', 2, 'broken'),
    ]
    # 문단이 여럿인 장면도 그대로 돌아온다
    assert read[0].scene == long
    assert (read[1].scene, read[1].problem) == (None, '다시 읽음: 장면 없음')


def test_rescoring_uses_the_checks_of_today():
    text = '## injured_pc #1 / m / 2.0초\n설명\n\n토르빈의 한쪽 팔이 기괴한 각도로 꺾였다.\n'

    (trial,) = rescore(read_report(text))

    assert [finding.label for finding in trial.broken] == ['부상이 새로 생김']


def test_a_report_with_a_broken_head_is_refused():
    with pytest.raises(ValueError, match='머리 줄'):
        read_report('## 아무 말\n\n글')


def test_the_script_rescores_without_calling_a_model(tmp_path):
    saved = tmp_path / 'state-eval.md'
    saved.write_text('표\n\n## dead_npc #1 / m / 1.0초\n설명\n\n악역영애가 눈을 떴다.\n', encoding='utf-8')
    arguments = argparse.Namespace(rescore=saved)

    (trial,) = eval_state.collect(arguments)

    assert {finding.label for finding in trial.broken} == {'되살아남'}
