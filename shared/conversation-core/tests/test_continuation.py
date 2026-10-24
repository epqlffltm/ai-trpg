# shared/conversation-core/tests/test_continuation.py

"""
이어서 출력의 글 다루기(conversation_core/continuation.py). DB 도 모델도 쓰지 않는다.

보는 것.
  - 모델이 앞 글의 끝을 되풀이하면 겹친 만큼 뗀다. 짧게 겹친 것(우연)은 둔다
  - 흘려 받을 때 어느 경계에서 조각나도 다 받은 글과 같은 결과다
  - 되풀이하지 않는 글은 어긋나는 순간 내보낸다
  - 문장 끝에서 끊겼고 새 글이 빈칸 없이 시작하면 빈칸 하나를 끼운다
"""

import pytest

from conversation_core.continuation import (
    MIN_OVERLAP,
    OverlapTrim,
    continued_text,
    instruction,
    joiner,
    repeated_length,
)

PREVIOUS = '그녀는 문을 열고 안으로 천천히 걸어'
REPEATED = '안으로 천천히 걸어 들어갔다.'


def stream(previous: str, pieces: list[str]) -> str:
    trim = OverlapTrim(previous)
    return ''.join(trim.feed(piece) for piece in pieces) + trim.release()


def test_the_repeated_end_is_cut():
    assert continued_text(PREVIOUS, REPEATED) == ' 들어갔다.'


@pytest.mark.parametrize('index', range(len(REPEATED) + 1))
def test_streaming_gives_the_same_text_wherever_it_is_split(index: int):
    assert stream(PREVIOUS, [REPEATED[:index], REPEATED[index:]]) == ' 들어갔다.'
    assert stream(PREVIOUS, list(REPEATED)) == ' 들어갔다.'


def test_a_short_overlap_is_kept():
    previous = '아무 말 없이 고개를 끄덕'
    short = '끄덕'[: MIN_OVERLAP - 1]

    assert repeated_length(previous, short + '였다') == 0
    assert continued_text(previous, '끄덕였다') == '끄덕였다'


def test_text_that_does_not_repeat_is_sent_as_soon_as_it_differs():
    trim = OverlapTrim('천천히 걸어')

    # "걸" 은 앞 글에 있어 아직 모른다. "걸음" 은 앞 글의 어느 끝과도 다르다
    assert trim.feed('걸') == ''
    assert trim.feed('음을') == '걸음을'
    assert trim.feed(' 옮겼다') == ' 옮겼다'
    assert trim.release() == ''


def test_once_decided_later_text_passes_through_even_if_it_looks_repeated():
    trim = OverlapTrim(PREVIOUS)
    trim.feed('그리고 ')

    assert trim.feed('안으로 천천히 걸어') == '안으로 천천히 걸어'
    assert trim.release() == ''


def test_a_stream_that_ends_while_still_matching_is_decided_at_the_end():
    trim = OverlapTrim(PREVIOUS)

    assert trim.feed('걸어') == ''
    assert trim.release() == '걸어'


@pytest.mark.parametrize(
    ('previous', 'text', 'expected'),
    [
        ('문을 열었다.', '그리고', ' '),
        ('"어서 와요!"', '그녀가', ' '),
        ('천천히 걸어', '갔다', ''),
        ('문을 열었다.', ' 그리고', ''),
        ('문을 열었다.', '\n그리고', ''),
        ('', '그리고', ''),
        ('문을 열었다.', '', ''),
    ],
)
def test_a_space_is_put_only_after_a_finished_sentence(previous: str, text: str, expected: str):
    assert joiner(previous, text) == expected


def test_everything_repeated_is_nothing_new():
    assert continued_text(PREVIOUS, '안으로 천천히 걸어') == ''


def test_the_instruction_says_it_is_not_the_user():
    assert '사용자의 말이 아니다' in instruction()
