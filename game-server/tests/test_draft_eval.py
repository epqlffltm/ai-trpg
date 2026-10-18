# game-server/tests/test_draft_eval.py

"""
초안 평가 도구(evals/drafts, scripts/try_drafts.py)를 검증한다. 실제 모델은 부르지 않는다.

정답을 그대로 적은 답을 가짜 provider 에 넣으면 모든 장면이 정답으로 세어져야 한다.
정답이 틀렸거나(목록에 없는 이름) 세는 법이 틀렸으면 여기서 드러난다.
어려운 장면(애매함, 말로 쓴 숫자, 여럿, 대신 받기)이 빠지지 않았는지, 대신 받기의 정답이 마지막에 가진 사람인지도 본다.
"""

import json

import pytest

from app.ai.calls import Outcome
from app.ai.fake import FakeCallLog, FakeProvider
from app.drafts.writer import DraftWriter
from evals.drafts.cases import CASES, CONTEXT, DraftCase
from evals.drafts.scoring import summarize
from scripts.try_drafts import try_case


def label(names: dict, name: str) -> str:
    """이름으로 이름표를 찾는다. 정답의 이름이 목록에 없으면 여기서 실패한다."""
    return next(choice.label for choice in names.values() if choice.name == name)


def perfect_reply(case: DraftCase) -> str:
    """정답을 그대로 적은 모델의 답."""
    found = [
        {'character': label(CONTEXT.characters, who), 'item': label(CONTEXT.items, what), 'count': count}
        for who, what, count in sorted(case.items)
    ]
    changes = [{'quest': label(CONTEXT.quests, quest), 'status': status} for quest, status in sorted(case.quests)]
    return json.dumps({'found_items': found, 'quest_changes': changes}, ensure_ascii=False)


def test_the_cases_cover_the_hard_kinds_too():
    names = [case.name for case in CASES]

    assert len(names) == len(set(names))
    # 애매함, 말로 쓴 숫자, 여럿, 대신 받기
    hard = {'put_back', 'lost_trail', 'counted_in_words', 'some_broken', 'many', 'picked_for_other', 'passed_between'}
    assert hard <= set(names)


def test_the_hand_over_cases_credit_only_the_last_holder():
    by_name = {case.name: case for case in CASES}

    # 주운 사람이 아니라 마지막에 가진 사람이다
    assert by_name['picked_for_other'].items == frozenset({('기사', '은열쇠', 1)})
    # 이미 가진 물건을 캐릭터끼리 건넨 것은 장부 초안의 일이 아니다(건네기는 엔진의 행동이 고친다)
    assert (by_name['passed_between'].items, by_name['passed_between'].quests) == (frozenset(), frozenset())


@pytest.mark.parametrize('case', CASES, ids=[case.name for case in CASES])
async def test_a_perfect_answer_scores_as_exact(case: DraftCase):
    log = FakeCallLog()
    writer = DraftWriter(FakeProvider(reply=perfect_reply(case)), log)

    trial = await try_case(writer, log, 'fake', case)

    assert (trial.read, trial.exact, trial.extra, trial.missed, trial.rejected) == (True, True, 0, 0, 0)


async def test_extra_missed_and_unreadable_are_counted():
    log = FakeCallLog()
    lost = next(case for case in CASES if case.name == 'lost')
    found = next(case for case in CASES if case.name == 'found')
    # 놓친 장면에 물건을 더하고(더한 것 1) 퀘스트를 빠뜨렸다(놓친 것 1). 없는 이름표 하나(지어낸 것 1)
    wrong = json.dumps(
        {'found_items': [{'character': 'p1', 'item': 'i2', 'count': 1}, {'character': 'p9', 'item': 'i1', 'count': 1}]}
    )

    first = await try_case(DraftWriter(FakeProvider(reply=wrong), log), log, 'fake', lost)
    second = await try_case(DraftWriter(FakeProvider(reply='물약을 찾았다'), log), log, 'fake', found)

    assert (first.read, first.exact, first.extra, first.missed, first.rejected) == (True, False, 1, 1, 1)
    assert (second.read, second.outcome, second.error, second.missed) == (False, Outcome.REJECTED, 'not_json', 1)
    [summary] = summarize([first, second])
    assert (summary.trials, summary.read, summary.exact, summary.extra, summary.missed, summary.rejected) == (
        2,
        1,
        0,
        1,
        2,
        1,
    )
