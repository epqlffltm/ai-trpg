# chat-server/tests/test_changes.py

"""
모델이 답 끝에 쓰는 상태 바꾸기의 제안을 읽는 규칙(app/conversation/changes.py, markers.py, #676).
DB 도 모델도 쓰지 않는다.

보는 것.
  - 줄의 모양 셋(affection, give, move)을 읽는다. 글머리표와 대소문자는 가리지 않는다. 모양이 틀린 줄은 버린다
  - 같은 종류가 여럿이면 처음 것이다. 읽는 줄의 수에 상한이 있다
  - 블록은 닫는 태그나 선택지의 표식 앞까지다. 선택지의 블록도 이 표식 앞에서 끊긴다
  - 본문은 어느 표식이든 처음 나온 것 앞까지다. 흘릴 때도 이 표식에서 멈추고, 조각에 걸친 표식을 붙잡는다
  - 지시에는 할 수 있는 것만 들어간다. 할 수 있는 것이 없으면 지시가 없다
"""

import pytest

from app.conversation.changes import MAX_LINES, Choice, Proposed, instruction, parse_changes
from app.conversation.markers import CHANGES_MARKER
from app.conversation.suggestions import MarkerHold, held_length, parse_suggestions, split_answer


def test_the_three_kinds_are_read():
    text = '좋아요.\n<changes>\n- affection +2\n* GIVE rose\n1. move park\n</changes>'

    assert parse_changes(text) == Proposed(affection=2, gift='rose', move='park')


@pytest.mark.parametrize(('line', 'expected'), [('affection -3', -3), ('affection 4', 4), ('affection+1', 1)])
def test_affection_takes_a_signed_number(line: str, expected: int):
    assert parse_changes(f'<changes>\n{line}').affection == expected


@pytest.mark.parametrize(
    'line',
    ['affection 많이', 'affection +1234', 'give', 'give 장미', 'give rose please', 'move', 'smile', '호감도 +2'],
)
def test_badly_shaped_lines_are_dropped(line: str):
    assert parse_changes(f'<changes>\n{line}\n') == Proposed()


def test_the_first_of_each_kind_wins():
    text = '<changes>\naffection +1\naffection +3\ngive rose\ngive cake\nmove park\nmove home'

    assert parse_changes(text) == Proposed(affection=1, gift='rose', move='park')


def test_only_the_first_lines_are_read():
    filler = '\n'.join(['smile'] * MAX_LINES)

    assert parse_changes(f'<changes>\n{filler}\ngive rose') == Proposed()


def test_without_the_marker_nothing_is_proposed():
    assert parse_changes('affection +3 이라고 말했다.') == Proposed()


def test_the_block_stops_at_the_suggestions():
    text = '좋아요.\n<changes>\naffection +2\n<suggestions>\ngive rose\n'

    assert parse_changes(text) == Proposed(affection=2)


# --- 본문과 선택지 ---


def test_the_body_ends_at_whichever_marker_comes_first():
    text = '좋아요.\n<changes>\naffection +2\n</changes>\n<suggestions>\n가자\n'

    body, tail = split_answer(text)

    assert body == '좋아요.'
    assert parse_suggestions(tail) == ['가자']


def test_the_suggestions_stop_at_the_changes():
    body, tail = split_answer('좋아요.\n<suggestions>\n가자\n<changes>\nmove park\n')

    assert (body, parse_suggestions(tail)) == ('좋아요.', ['가자'])


def test_without_suggestions_the_tail_is_none():
    assert split_answer('좋아요.\n<changes>\nmove park') == ('좋아요.', None)


def test_streaming_stops_at_the_changes_marker_split_across_pieces():
    hold = MarkerHold()

    sent = hold.feed('좋아요.\n<cha') + hold.feed('nges>\nmove park') + hold.release()

    assert sent == '좋아요.\n'
    assert hold.body() == '좋아요.'


@pytest.mark.parametrize(('text', 'length'), [('abc<cha', 4), ('abc<changes', 8), ('abc<s', 2)])
def test_a_prefix_of_either_marker_is_held(text: str, length: int):
    assert held_length(text) == length


# --- 지시 ---


def test_the_instruction_lists_only_what_can_be_done():
    text = instruction(3, [Choice('rose', '장미')], [Choice('park', '공원')])

    assert CHANGES_MARKER in text
    assert '-3 에서 +3 까지' in text
    assert 'rose(장미)' in text
    assert 'park(공원)' in text


def test_without_affection_the_affection_line_is_left_out():
    text = instruction(0, [Choice('rose', '장미')], [])

    assert 'affection' not in text
    assert 'move' not in text


def test_with_nothing_to_offer_there_is_no_instruction():
    assert instruction(0, [], []) is None
