# shared/conversation-core/tests/test_window.py

"""
모델에 보낼 최근 대화의 창(conversation_core/window.py).
최근 말부터 글자의 상한 안에서, 마지막 말은 늘, 중간은 건너뛰지 않는다.
"""

from conversation_core.window import Turn, select_window


def test_the_window_keeps_the_latest_turns_within_the_budget():
    turns = [Turn('assistant', 'a' * 5), Turn('user', 'b' * 5), Turn('assistant', 'c' * 5), Turn('user', 'd' * 5)]

    assert select_window(turns, 15) == turns[1:]
    assert select_window(turns, 14) == turns[2:]
    assert select_window(turns, 100) == turns


def test_the_last_turn_is_always_sent():
    assert select_window([Turn('user', 'x' * 50)], 10) == [Turn('user', 'x' * 50)]


def test_the_window_does_not_skip_a_long_turn():
    turns = [Turn('user', 'a'), Turn('assistant', 'b' * 50), Turn('user', 'c')]

    # 긴 말을 건너뛰고 더 앞의 말을 넣지 않는다. 대화의 앞뒤가 끊긴다
    assert select_window(turns, 10) == [Turn('user', 'c')]


def test_an_empty_branch_is_an_empty_window():
    assert select_window([], 10) == []
