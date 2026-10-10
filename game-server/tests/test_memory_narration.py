# game-server/tests/test_memory_narration.py

"""
지난 일과 인물의 이력이 서술에 주는 효과를 보는 도구(evals/memory/narration.py, scripts/try_memory.py)를 검증한다.

모델은 가짜다. 숫자에 뜻은 없고, 도구가 서버와 같은 규칙으로 고르고 같은 조립으로 보내는지를 본다.
"""

from dataclasses import replace

import pytest

from app.ai.fake import FakeEmbedder, FakeProvider
from app.assets.models import NarrationStyle
from app.lore.retrieval import query_text
from app.memory.retrieval import MemoryThresholds, choose_memories, eligible, people_in
from app.rounds import prompt
from app.rounds.narrator import MemoryNote
from evals.lore.narration import prompt_text
from evals.memory.dataset import load_dataset
from evals.memory.narration import (
    BETRAYAL,
    CASES,
    CURRENT,
    HELPER,
    STORY,
    MemoryContext,
    MemoryMode,
    case_request,
    describe_context,
    histories_for,
    memory_context,
    recall_hits,
    request_for,
)
from scripts.try_memory import describe, run_trial, speech_count, tally

# 가짜 임베더에 맞춘 거리 기준(tests/conftest.py 의 테스트 설정과 같은 까닭)
LOOSE = MemoryThresholds(max_distance=0.6, keyword_max_distance=2.0)


@pytest.fixture
def dataset():
    return load_dataset()


def test_a_case_continues_the_game_after_its_last_round(dataset):
    request = case_request(dataset, BETRAYAL)

    # 20 라운드의 게임에 이어 21 라운드다. 지난 기록은 서버와 같이 최근 3 라운드다
    assert request.round_number == CURRENT == len(dataset.rounds) + 1
    assert [past.number for past in request.history] == [18, 19, 20]
    assert (request.scene, request.moves) == (BETRAYAL.scene, list(BETRAYAL.moves))
    assert (request.memories, request.histories) == ([], [])


def test_the_story_keeps_the_secret_out():
    # GM 메모에 배신의 낌새가 있으면 지난 일 없이도 떠올릴 수 있다
    assert STORY.gm_notes == ''


def test_the_recall_words_are_not_in_the_prompt_without_memories(dataset):
    for case in CASES.values():
        base = prompt_text(prompt.build_messages(case_request(dataset, case)))

        # 지난 기록과 이번 장면에 없는 낱말이라야 떠올린 것으로 셀 수 있다
        assert [word for word in case.recall_words if word in base] == [], case.name


async def test_the_context_is_chosen_by_the_server_rule(dataset):
    request = case_request(dataset, BETRAYAL)

    context = await memory_context(FakeEmbedder(), dataset, request, LOOSE)

    text = query_text(request)
    expected = choose_memories(
        eligible(dataset.memories, CURRENT), people_in(dataset.people, text), context.distances, LOOSE
    )
    assert [note.round_number for note in context.memories] == [memory.number for memory in expected]
    # 악역영애가 나온 기억 중 최근 것이 먼저다(배신한 12 라운드)
    assert context.memories[0].round_number == 12
    assert set(context.distances) == {memory.number for memory in eligible(dataset.memories, CURRENT)}


def test_histories_are_of_the_people_in_the_scene(dataset):
    (lady,) = histories_for(dataset, query_text(case_request(dataset, BETRAYAL)))
    (cook,) = histories_for(dataset, query_text(case_request(dataset, HELPER)))

    # 이름표는 서버처럼 장면의 호칭이다. 첫 측정에서 진짜 이름(비올레타)을 넣었더니 모델이 매번 그 이름을 썼다
    assert lady.name == '악역영애'
    assert [line.round_number for line in lady.lines] == [2, 3, 11, 12, 13]
    assert cook.name == '수프 아줌마'
    assert all(line.round_number < CURRENT - prompt.HISTORY_ROUNDS for line in [*lady.lines, *cook.lines])


async def test_on_puts_the_memories_and_histories_and_off_leaves_them_out(dataset):
    request = case_request(dataset, BETRAYAL)
    context = await memory_context(FakeEmbedder(), dataset, request, LOOSE)

    on = prompt_text(prompt.build_messages(request_for(MemoryMode.ON, request, context)))
    off = prompt_text(prompt.build_messages(request_for(MemoryMode.OFF, request, context)))

    assert prompt.MEMORY_TITLE in on and prompt.HISTORY_TITLE in on
    assert prompt.MEMORY_TITLE not in off and prompt.HISTORY_TITLE not in off


def test_recall_counts_only_words_the_plain_prompt_lacks(dataset):
    request = case_request(dataset, BETRAYAL)

    hits = recall_hits('악역영애가 배신한 날의 무전기를 떠올렸다. 결승선이 빛났다.', BETRAYAL, request)

    assert hits == ['배신', '무전기']


def test_a_recall_word_already_in_the_plain_prompt_is_not_counted(dataset):
    # 결승선은 지난 기록(19, 20 라운드)에 있다. 지난 일 없이도 쓸 수 있다
    case = replace(BETRAYAL, recall_words=('결승선', '배신'))

    assert recall_hits('결승선 앞에서 배신을 떠올렸다.', case, case_request(dataset, case)) == ['배신']


def test_a_person_without_lines_has_no_history(dataset):
    # 지난 기록보다 앞의 서술에 한 번도 나오지 않는 인물
    stranger = dataset.people[0].model_copy(update={'name': '낯선 기사', 'keywords': []})
    lonely = replace(dataset, people=[stranger])

    assert histories_for(lonely, '낯선 기사가 다가온다.') == []


def test_the_context_is_described_with_rounds_and_distances():
    context = MemoryContext([MemoryNote(12, '결과')], [], {12: 0.412})

    assert describe_context(BETRAYAL, context) == 'betrayal: 지난 일 12(0.41) / 이력 없음'


# --- 서술해 보기 ---


async def test_a_trial_sends_the_server_prompt_and_counts_what_was_recalled(dataset):
    request = case_request(dataset, BETRAYAL)
    context = await memory_context(FakeEmbedder(), dataset, request, LOOSE)
    provider = FakeProvider(reply='악역영애가 부채를 접었다. "배신자에게 할 말은 없어요." 무전기가 깜빡였다.')

    trial = await run_trial(provider, BETRAYAL, request, MemoryMode.ON, context, NarrationStyle.WEB_NOVEL)

    (call,) = provider.calls
    expected = prompt.build_messages(
        request_for(MemoryMode.ON, replace(request, style=NarrationStyle.WEB_NOVEL), context)
    )
    assert call.messages == expected
    assert trial.recalled == ('배신', '무전기')
    assert trial.speech == 1
    assert '지난 일 on / 문체 web_novel' in describe(trial)


async def test_a_refused_reply_is_a_problem_not_a_scene(dataset):
    request = case_request(dataset, HELPER)
    context = MemoryContext([], [])

    trial = await run_trial(FakeProvider(reply='  '), HELPER, request, MemoryMode.OFF, context, NarrationStyle.CLASSIC)

    assert trial.scene is None
    assert 'empty' in trial.problem


@pytest.mark.parametrize(('scene', 'count'), [('"윽!"', 0), ('"배신자에게 할 말은 없어요."', 1), ('말이 없다.', 0)])
def test_short_sounds_are_not_counted_as_speech(scene: str, count: int):
    assert speech_count(scene) == count


async def test_the_tally_groups_trials_by_case_mode_and_style(dataset):
    request = case_request(dataset, BETRAYAL)
    context = MemoryContext([], [])
    trials = [
        await run_trial(FakeProvider(reply=reply), BETRAYAL, request, mode, context, NarrationStyle.CLASSIC)
        for mode, reply in [
            (MemoryMode.OFF, '결승선이 빛났다.'),
            (MemoryMode.ON, '배신의 기억이 스쳤다.'),
            (MemoryMode.ON, '결승선이 빛났다.'),
        ]
    ]

    rows = tally(trials).splitlines()

    assert len(rows) == 4
    assert '| off | classic | 1 | 0 | 0/1 |' in rows[2]
    assert '| on | classic | 2 | 0 | 1/2 | 0.5 |' in rows[3]
