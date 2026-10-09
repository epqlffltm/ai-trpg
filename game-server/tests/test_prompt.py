# game-server/tests/test_prompt.py

"""
GM 의 서술을 부탁하는 메시지의 조립(app/rounds/prompt.py)을 검증한다. 순수 함수라 DB 도 모델도 쓰지 않는다.

보는 것은 넷이다.
  - 메시지의 순서와 역할. 시스템 → 사람 → (지난 라운드: 모델, 사람)… → 이번 장면(모델) → 이번 결과(사람).
  - 시스템 지시에 무엇이 들어가나. 지시, 수위, 진행 지침, 세계관의 설정과 GM 메모. 빈 것은 빠진다.
  - 이번 라운드의 결과는 엔진이 정한 그대로 들어간다.
  - 지난 기록은 정해 둔 라운드 수와 글자 수 안에서, 오래된 것부터 뺀다.
"""

import pytest

from app.ai.provider import Role
from app.rounds import prompt
from app.rounds.narrator import Move, NarrationRequest, PastRound, StoryContext, Verdict
from app.rounds.prompt import build_messages, fit_history, system_text

STORY = StoryContext(
    title='추격전',
    rating='all',
    guide='추격은 언제나 바이크로 한다.',
    setting='열일곱 개의 행성이 고속도로로 이어져 있다.',
    gm_notes='악역영애는 사실 경찰의 끄나풀이다.',
)

VERDICT = Verdict(ability='민첩', difficulty='보통', roll=12, modifier=3, total=15, target=15, success=True)


def make_request(history: list[PastRound] | None = None, story: StoryContext = STORY) -> NarrationRequest:
    return NarrationRequest(
        round_number=4,
        scene='사이렌이 가까워진다.',
        moves=[Move('폭주족 엘프', '바이크에서 뛰어내린다.', verdict=VERDICT), Move('악역영애', None)],
        story=story,
        history=history or [],
    )


def past(number: int, scene: str = '장면', lines: list[str] | None = None) -> PastRound:
    return PastRound(number=number, scene=scene, lines=['엘프: 달린다.'] if lines is None else lines)


# --- 순서와 역할 ---


def test_the_messages_alternate_after_the_system_instructions():
    messages = build_messages(make_request(history=[past(2, '두 번째 장면'), past(3, '세 번째 장면')]))

    assert [message.role for message in messages] == [
        Role.SYSTEM,
        Role.USER,
        Role.ASSISTANT,
        Role.USER,
        Role.ASSISTANT,
        Role.USER,
        Role.ASSISTANT,
        Role.USER,
    ]
    # 첫 메시지는 사람의 말이다. 대화가 모델의 말로 시작하면 받지 않는 API 가 있다
    assert messages[1].content == prompt.OPENING_LINE
    # 지난 장면은 모델이 했던 말로, 그때 플레이어들이 한 말은 사람의 말로 들어간다
    assert [messages[2].content, messages[3].content] == ['두 번째 장면', '엘프: 달린다.']
    assert messages[4].content == '세 번째 장면'
    # 이번 장면은 모델의 말, 이번 라운드의 결과와 부탁은 마지막 사람의 말이다
    assert messages[-2].content == '사이렌이 가까워진다.'
    assert messages[-1].role == Role.USER


def test_without_history_the_current_scene_follows_the_opening_line():
    messages = build_messages(make_request())

    assert [message.role for message in messages] == [Role.SYSTEM, Role.USER, Role.ASSISTANT, Role.USER]


def test_a_round_where_nobody_spoke_still_has_a_line_from_the_players():
    messages = build_messages(make_request(history=[past(3, lines=[])]))

    # 모델의 말이 연달아 나오지 않게 사람의 말 자리를 채운다
    assert messages[3].role == Role.USER
    assert messages[3].content == '(아무도 선언하지 않았다)'


# --- 시스템 지시 ---


def test_the_system_instructions_carry_the_rules_and_the_story():
    text = system_text(STORY)

    assert text.startswith(prompt.GM_RULES)
    for part in [prompt.RATING_RULES['all'], STORY.title, STORY.guide, STORY.setting, STORY.gm_notes]:
        assert part in text


def test_the_rating_picks_the_line_about_how_dark_it_may_get():
    adult = StoryContext(title='추격전', rating='adult', guide='')

    assert prompt.RATING_RULES['adult'] in system_text(adult)
    assert prompt.RATING_RULES['all'] not in system_text(adult)


def test_empty_parts_of_the_story_are_left_out():
    # 세계관이 없는 시나리오다. 진행 지침도 비어 있다
    text = system_text(StoryContext(title='추격전', rating='all', guide='  '))

    assert '## 진행 지침' not in text
    assert '## 세계관' not in text
    assert '## GM 메모' not in text
    assert '## 시나리오' in text


def test_the_instructions_tell_the_model_not_to_change_the_results():
    # 결과는 엔진이 정했다. 지시가 그것을 분명히 말해야 한다
    assert '결과를 바꾸지 마라' in prompt.GM_RULES
    assert '지어내지 마라' in prompt.GM_RULES


# --- 이번 라운드 ---


def test_the_round_carries_what_the_engine_decided():
    last = build_messages(make_request())[-1].content

    assert last.startswith('[4 라운드에 한 일과 결과]')
    # 판정은 엔진이 정한 숫자 그대로다
    assert '폭주족 엘프: 바이크에서 뛰어내린다. (민첩 판정 성공: 12 + 3 = 15, 목표 15)' in last
    assert '악역영애: 아무것도 하지 않았다.' in last
    assert last.endswith(prompt.CLOSING_REQUEST)


# --- 지난 기록 ---


def test_history_keeps_only_the_latest_rounds():
    history = [past(number) for number in range(1, 7)]

    kept = fit_history(history, max_rounds=3, max_chars=10_000)

    # 오래된 것부터 돌려준다. 이야기의 순서다
    assert [round_.number for round_ in kept] == [4, 5, 6]


def test_history_drops_the_oldest_rounds_when_it_is_too_long():
    history = [past(1, '가' * 40), past(2, '나' * 40), past(3, '다' * 40)]
    # 한 라운드는 장면 40자와 선언 한 줄(엘프: 달린다. 8자)이다. 두 라운드까지만 들어간다
    kept = fit_history(history, max_rounds=3, max_chars=100)

    assert [round_.number for round_ in kept] == [2, 3]


def test_a_latest_round_that_is_too_long_on_its_own_is_left_out():
    kept = fit_history([past(1), past(2, '가' * 200)], max_rounds=3, max_chars=100)

    # 최근 것이 넘치면 거기서 멈춘다. 그 앞의 것만 넣으면 이야기에 구멍이 난다
    assert kept == []


@pytest.mark.parametrize('max_rounds', [0, -1])
def test_no_history_when_no_rounds_are_allowed(max_rounds: int):
    assert fit_history([past(1)], max_rounds=max_rounds, max_chars=10_000) == []


def test_the_messages_use_the_limits_of_the_prompt(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(prompt, 'HISTORY_ROUNDS', 1)

    messages = build_messages(make_request(history=[past(2, '두 번째 장면'), past(3, '세 번째 장면')]))

    contents = [message.content for message in messages]
    assert '세 번째 장면' in contents
    assert '두 번째 장면' not in contents
