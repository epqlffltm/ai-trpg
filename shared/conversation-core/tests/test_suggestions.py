# shared/conversation-core/tests/test_suggestions.py

"""
다음 답 추천의 나누기와 거르기(conversation_core/suggestions.py).
DB 도 모델도 쓰지 않는다.

보는 것.
  - 흘려 받을 때 표식이 어느 조각의 경계에 걸려도 본문만 내보내고, 표식 뒤는 모은다
  - 표식이 없으면 붙잡은 글자도 끝에 내보낸다. 표식의 앞부분처럼 보이던 글도 본문이다
  - 선택지: 번호, 글머리표, 따옴표를 떼고, 빈 것, 긴 것, 같은 것을 빼고, 셋까지. 닫는 태그 뒤는 버린다
"""

import pytest

from conversation_core.suggestions import (
    MARKER,
    SUGGESTION_MAX_CHARS,
    MarkerHold,
    held_length,
    instruction,
    parse_suggestions,
    split_answer,
)

ANSWER = f'어서 와요.\n책을 찾으세요?\n{MARKER}\n1. 응, 소설을 찾아\n2. 그냥 구경 중이야\n'


def stream(pieces: list[str]) -> tuple[str, MarkerHold]:
    """조각들을 차례로 흘리고 끝낸다. 내보낸 글 전체와 MarkerHold."""
    hold = MarkerHold()
    sent = ''.join(hold.feed(piece) for piece in pieces)
    return sent + hold.release(), hold


def splits(text: str) -> list[list[str]]:
    """text 를 두 조각으로 나누는 모든 방법과, 한 글자씩 나눈 것."""
    return [[text[:index], text[index:]] for index in range(len(text) + 1)] + [list(text)]


# --- 흘려 받기 ---


@pytest.mark.parametrize('pieces', splits(ANSWER))
def test_only_the_body_is_streamed_wherever_the_marker_is_split(pieces: list[str]):
    sent, hold = stream(pieces)

    assert sent == '어서 와요.\n책을 찾으세요?\n'
    assert hold.body() == '어서 와요.\n책을 찾으세요?'
    assert hold.tail == '\n1. 응, 소설을 찾아\n2. 그냥 구경 중이야\n'


def test_without_a_marker_the_held_text_is_sent_at_the_end():
    hold = MarkerHold()

    # "<sugg" 는 표식의 앞부분일 수 있어 붙잡는다. 다음 조각에서 아닌 것이 드러난다
    assert hold.feed('부등호 <sugg') == '부등호 '
    assert hold.feed('ar> 는 표식이 아니다') == '<suggar> 는 표식이 아니다'
    assert hold.feed(' <') == ' '
    assert hold.release() == '<'
    assert (hold.body(), hold.tail) == ('부등호 <suggar> 는 표식이 아니다 <', None)


def test_text_after_the_marker_is_never_sent():
    hold = MarkerHold()

    assert hold.feed(f'안녕{MARKER}가') == '안녕'
    assert hold.feed('나다') == ''
    assert hold.release() == ''
    assert hold.tail == '가나다'


def test_a_cut_stream_keeps_what_was_sent():
    hold = MarkerHold()
    hold.feed('어서 ')
    hold.feed('와 <sugges')

    # 끊겼다. 붙잡은 것(표식인지 모르는 글)도 받은 본문이다
    assert hold.release() == '<sugges'
    assert hold.body() == '어서 와 <sugges'


@pytest.mark.parametrize(('text', 'length'), [('abc<', 1), ('abc<sug', 4), ('<suggestions', 12), ('abc', 0), ('', 0)])
def test_the_held_length_is_the_longest_marker_prefix(text: str, length: int):
    assert held_length(text) == length


# --- 다 받은 글 ---


def test_a_finished_answer_is_split_into_body_and_tail():
    assert split_answer(ANSWER) == ('어서 와요.\n책을 찾으세요?', '\n1. 응, 소설을 찾아\n2. 그냥 구경 중이야\n')
    assert split_answer('어서 와요.  \n') == ('어서 와요.', None)


# --- 선택지 거르기 ---


def test_numbers_bullets_and_quotes_are_removed():
    tail = '\n1. 응\n2) "같이 가자"\n- “싫어”\n'

    assert parse_suggestions(tail) == ['응', '같이 가자', '싫어']


def test_empty_long_and_repeated_ones_are_dropped_and_three_are_kept():
    tail = '\n'.join(['', '가', '  ', 'x' * (SUGGESTION_MAX_CHARS + 1), '가', '나', 'x' * SUGGESTION_MAX_CHARS, '라'])

    assert parse_suggestions(tail) == ['가', '나', 'x' * SUGGESTION_MAX_CHARS]


def test_text_after_the_closing_tag_is_ignored():
    assert parse_suggestions('\n가\n</suggestions>\n덧붙인 말') == ['가']


@pytest.mark.parametrize('tail', [None, '', '\n\n', '\n-\n1.\n""'])
def test_nothing_usable_is_no_suggestions(tail: str | None):
    assert parse_suggestions(tail) == []


def test_the_instruction_names_the_marker():
    assert MARKER in instruction()
