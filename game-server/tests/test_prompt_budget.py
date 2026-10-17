# game-server/tests/test_prompt_budget.py

"""
서술 요청의 입력 토큰 예산(app/rounds/budget.py)을 검증한다.

글자 수로 어림하는 것, 판매가의 70% 만 보내는 것, 넘치면 지난 기록 → 로어북 → 기억 순서로 빼는 것,
빼지 않는 것(작가의 글, 바로 앞 장면, 이번 라운드)은 그대로 두는 것, 작가의 글이 판매가의 예산을 넘으면
시작하지 못하는 판이라고 보는 것을 본다.
"""

import uuid
from dataclasses import replace

from app.ai.provider import ChatMessage, Role
from app.assets.models import NarrationStyle
from app.catalog.rules import ROUND_INPUT_TOKENS
from app.rounds import budget
from app.rounds.budget import (
    INPUT_BUDGET,
    STORY_MAX_TOKENS,
    estimate_messages,
    estimate_tokens,
    fit_request,
    story_fits,
    story_tokens,
    trimmed,
)
from app.rounds.narrator import LoreNote, MemoryNote, Move, NarrationRequest, PastRound, StoryContext
from app.rounds.prompt import HISTORY_ROUNDS, build_messages, system_text

STORY = StoryContext(title='추격전', rating='all', guide='추격은 언제나 바이크로 한다.')
SCENE = '사이렌이 울린다.'
MOVE = Move('엘프', '달린다.')


def past(number: int) -> PastRound:
    return PastRound(
        number=number, scene=f'{number} 라운드의 장면. ' + '고속도로가 길다. ' * 20, lines=['엘프: 달린다.']
    )


def lore(name: str) -> LoreNote:
    return LoreNote(entry_id=uuid.uuid4(), name=name, content=f'{name}의 설정. ' + '오래된 이야기. ' * 20)


def memory(number: int) -> MemoryNote:
    return MemoryNote(round_number=number, text=f'결과: {number} 라운드에 차단기가 부서졌다. ' + '먼지. ' * 30)


def full_request() -> NarrationRequest:
    """지난 기록 셋, 로어북 항목 둘, 기억 둘이 든 요청."""
    return NarrationRequest(
        round_number=9,
        scene=SCENE,
        moves=[MOVE],
        story=STORY,
        history=[past(6), past(7), past(8)],
        lore=[lore('드워프'), lore('엘프')],
        memories=[memory(2), memory(1)],
    )


def size(request: NarrationRequest) -> int:
    return estimate_messages(build_messages(request))


# --- 세기 ---


def test_tokens_are_estimated_from_the_characters_rounding_up(monkeypatch):
    assert estimate_tokens(0) == 0
    assert estimate_tokens(1000) == 1000
    monkeypatch.setattr(budget, 'TOKENS_PER_CHAR', 0.75)
    assert estimate_tokens(3) == 3  # 2.25 를 올린다


def test_the_messages_are_counted_by_their_text_only():
    messages = [ChatMessage(Role.SYSTEM, '가나다'), ChatMessage(Role.USER, '라마')]

    assert estimate_messages(messages) == 5


def test_only_seventy_percent_of_the_priced_input_is_sent():
    # 판매가는 입력 12,000 토큰으로 매겼다. 어림이 30% 틀려도 판매가 안이다
    assert ROUND_INPUT_TOKENS == 12_000
    assert INPUT_BUDGET == 8_400


# --- 줄이기 ---


def test_a_request_within_the_budget_is_sent_as_it_is():
    request = full_request()

    assert fit_request(request, budget=size(request)) == request


def test_the_oldest_past_round_goes_first():
    request = full_request()

    fitted = fit_request(request, budget=size(request) - 1)

    assert [round_.number for round_ in fitted.history] == [7, 8]
    assert (fitted.lore, fitted.memories) == (request.lore, request.memories)


def test_the_lore_goes_after_all_the_past_rounds_from_the_least_close():
    request = full_request()
    no_history = replace(request, history=[])

    fitted = fit_request(request, budget=size(no_history) - 1)

    # 검색이 고른 순서의 뒤가 덜 가깝다
    assert fitted.history == []
    assert [note.name for note in fitted.lore] == ['드워프']
    assert fitted.memories == request.memories


def test_the_memories_go_last_from_the_least_close():
    request = full_request()
    no_lore = replace(request, history=[], lore=[])

    fitted = fit_request(request, budget=size(no_lore) - 1)

    assert (fitted.history, fitted.lore) == ([], [])
    assert [note.round_number for note in fitted.memories] == [2]


def test_what_cannot_be_cut_stays_even_over_the_budget():
    request = full_request()

    fitted = fit_request(request, budget=1)

    # 다 빼도 넘치면 다 뺀 요청이다. 작가의 글, 바로 앞 장면, 이번 라운드는 남는다
    assert (fitted.history, fitted.lore, fitted.memories) == ([], [], [])
    messages = build_messages(fitted)
    assert messages[0].content == system_text(STORY, request.style)
    assert SCENE in [message.content for message in messages]
    assert '엘프: 달린다.' in messages[-1].content


def test_each_step_removes_one_thing():
    steps = list(trimmed(full_request()))

    # 줄이지 않은 것 하나 + 지난 기록 셋 + 로어북 둘 + 기억 둘
    assert len(steps) == 1 + 3 + 2 + 2
    sizes = [size(step) for step in steps]
    assert sizes == sorted(sizes, reverse=True)
    assert len(set(sizes)) == len(sizes)


def test_the_history_limit_of_the_prompt_is_kept():
    request = replace(full_request(), history=[past(number) for number in range(1, 9)])

    first = next(trimmed(request))

    # 줄이기 전에도 지난 기록은 최근 HISTORY_ROUNDS 라운드까지다(app/rounds/prompt.py)
    assert [round_.number for round_ in first.history] == list(range(9 - HISTORY_ROUNDS, 9))


# --- 작가의 글 ---


def test_the_story_counts_the_rules_and_the_writing():
    assert story_tokens(STORY, NarrationStyle.CLASSIC) == len(system_text(STORY, NarrationStyle.CLASSIC))


def test_a_story_over_the_priced_input_does_not_fit():
    rules = story_tokens(replace(STORY, guide=''), NarrationStyle.CLASSIC)
    # 진행 지침의 절 머리("[진행 지침]"과 줄바꿈)도 글자다. 그만큼을 빼고 채운다
    head = story_tokens(replace(STORY, guide='가'), NarrationStyle.CLASSIC) - rules - 1
    room = STORY_MAX_TOKENS - rules - head

    assert story_fits(replace(STORY, guide='가' * room), NarrationStyle.CLASSIC)
    assert not story_fits(replace(STORY, guide='가' * (room + 1)), NarrationStyle.CLASSIC)


def test_the_story_limit_is_the_priced_input():
    assert STORY_MAX_TOKENS == ROUND_INPUT_TOKENS
