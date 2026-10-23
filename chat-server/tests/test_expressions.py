# chat-server/tests/test_expressions.py

"""
표정의 표식을 떼고 고르는 것(app/conversation/expressions.py)을 검증한다. DB 도 모델도 쓰지 않는다.

보는 것.
  - 답의 맨 앞의 표식에서 표정을 떼고 나머지를 본문으로 둔다. 앞의 빈칸과 표식 뒤의 줄바꿈은 뗀다
  - 흘려 받을 때 표식이 조각의 경계에 걸려도 같다. 표식으로 시작하지 않으면 바로 내보낸다
  - 표식이 닫히지 않은 채 길어지거나 끝나면 받은 그대로 둔다
  - 표정은 고를 수 있는 이름 가운데 하나다(대소문자는 가리지 않는다). 기본이나 모르는 이름은 None 이다
  - 지시에는 기본과 고를 수 있는 표정이 나온다
"""

import pytest

from app.conversation.expressions import HEAD_MAX, ExpressionHead, instruction, match_expression, split_expression


def stream(pieces: list[str]) -> tuple[str, str | None]:
    head = ExpressionHead()
    text = ''.join(head.feed(piece) for piece in pieces) + head.release()
    return text, head.raw


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('<expression>웃음</expression>\n안녕', ('웃음', '안녕')),
        ('  \n<expression>화남</expression>그만해', ('화남', '그만해')),
        ('안녕하세요', (None, '안녕하세요')),
        ('<em>강조</em>', (None, '<em>강조</em>')),
        ('<expr', (None, '<expr')),
        ('<expression>웃음', (None, '<expression>웃음')),
    ],
)
def test_the_marker_is_split_from_the_front(text: str, expected: tuple):
    assert split_expression(text) == expected


def test_streaming_gives_the_same_result_across_piece_borders():
    pieces = ['<ex', 'pression>화', '남</expre', 'ssion>', '\n', '그만', '해']

    assert stream(pieces) == ('그만해', '화남')


def test_a_body_without_the_marker_is_sent_at_once():
    head = ExpressionHead()

    assert head.feed('안') == '안'
    assert head.decided and head.raw is None


def test_the_front_is_held_while_it_may_still_be_the_marker():
    head = ExpressionHead()

    assert (head.feed('<expres'), head.decided) == ('', False)


def test_a_marker_that_does_not_close_in_time_is_given_up():
    long = '<expression>' + 'x' * HEAD_MAX

    assert stream([long, '뒤']) == (long + '뒤', None)


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('웃음', '웃음'),
        (' Smile ', 'Smile'),
        ('smile', 'Smile'),
        ('기본', None),
        ('', None),
        (None, None),
        ('슬픔', None),
    ],
)
def test_only_known_expressions_are_kept(raw, expected):
    assert match_expression(raw, ['웃음', 'Smile']) == expected


def test_the_instruction_lists_the_choices():
    text = instruction(['웃음', '화남'])

    assert '<expression>표정</expression>' in text
    assert '기본, 웃음, 화남' in text
