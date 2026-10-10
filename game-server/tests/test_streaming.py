# game-server/tests/test_streaming.py

"""
흘려 받는 답을 읽는 도구(app/ai/streaming.py)와 가짜 provider 의 조각을 검증한다.

네트워크를 쓰지 않는다. 줄들을 직접 넣는다.
생각 글 걸러 내기는 조각이 어디서 잘리든 같은 글이 나와야 한다. 자를 수 있는 모든 자리에서 잘라 본다.
"""

from collections.abc import AsyncIterator

import pytest

from app.ai.fake import FakeProvider, split_text
from app.ai.provider import GenerationParams, ProviderError
from app.ai.streaming import (
    Chunk,
    StreamState,
    ThinkingFilter,
    data_of,
    drop_thinking,
    parse_chunk,
    partial_open_tag,
    read_stream,
)

MODEL = 'gemma4:26b'
SCENE = '엔진 소리가 골목을 메운다.'
# 생각 글에 들어 있을 수 있는 것. 넘기는 조각에 섞이면 안 된다
SECRET = '악역영애는 사실 경찰의 끄나풀이다.'

# 생각 글이 섞인 여러 모양. 다 받은 뒤에 떼어 낸 글이 기준이다
MIXED = [
    f'<think>{SECRET}</think>{SCENE}',
    f'{SCENE}<think>{SECRET}</think>',
    f'앞<think>{SECRET}</think>뒤<think>또</think>끝',
    f'{SCENE}<think>{SECRET}',
    '부등호 a<b 와 <생각> 과 <thinker> 는 글이다',
    '끝에 걸친 태그의 앞부분 <thi',
    SCENE,
]


def chunk_line(content: str, finish: str | None = None) -> str:
    """글 조각 하나의 SSE 줄."""
    finish_field = 'null' if finish is None else f'"{finish}"'
    return f'data: {{"choices":[{{"delta":{{"content":"{content}"}},"finish_reason":{finish_field}}}]}}'


async def lines(*items: str) -> AsyncIterator[str]:
    """줄들을 흘려 준다."""
    for item in items:
        yield item


def filtered(pieces: list[str]) -> list[str]:
    """조각들을 차례로 걸러 넘긴 것들. 마지막에 붙잡아 둔 것까지."""
    thinking = ThinkingFilter()
    passed = [thinking.feed(piece) for piece in pieces]
    passed.append(thinking.finish())
    return passed


# --- 생각 글 걸러 내기 ---


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        (f'<think>범인을 따져 보자.</think>{SCENE}', SCENE),
        (f'<think>\n여러 줄의\n생각\n</think>\n{SCENE}', f'\n{SCENE}'),
        (f'{SCENE}<think>뒤에 붙은 생각</think>', SCENE),
        ('<think>끝나지 않은 생각', ''),
        (SCENE, SCENE),
    ],
)
def test_thinking_mixed_into_the_content_is_dropped(text: str, expected: str):
    assert drop_thinking(text) == expected


@pytest.mark.parametrize(
    ('text', 'size'),
    [('장면<', 1), ('장면<t', 2), ('장면<thi', 4), ('장면<think', 6), ('장면<think>', 0), ('a<b', 0), ('', 0)],
)
def test_the_start_of_a_tag_at_the_end_is_measured(text: str, size: int):
    assert partial_open_tag(text) == size


@pytest.mark.parametrize('text', MIXED)
def test_cut_anywhere_in_two_the_pieces_join_to_the_finished_text(text: str):
    for cut in range(len(text) + 1):
        passed = filtered([text[:cut], text[cut:]])

        assert ''.join(passed) == drop_thinking(text), cut


@pytest.mark.parametrize('text', MIXED)
def test_fed_one_letter_at_a_time_the_pieces_join_to_the_finished_text(text: str):
    passed = filtered(list(text))

    assert ''.join(passed) == drop_thinking(text)


@pytest.mark.parametrize('text', MIXED)
def test_no_piece_ever_carries_the_thinking(text: str):
    for cut in range(len(text) + 1):
        for piece in filtered([text[:cut], text[cut:]]):
            assert SECRET not in piece
            assert '<think>' not in piece


def test_the_start_of_a_tag_is_held_until_the_next_piece():
    thinking = ThinkingFilter()

    assert thinking.feed('장면<thi') == '장면'
    assert thinking.feed(f'nk>{SECRET}') == ''
    assert thinking.feed('</think>끝') == '끝'


def test_what_never_became_a_tag_is_handed_on_at_the_end():
    thinking = ThinkingFilter()

    assert thinking.feed('장면<thi') == '장면'
    assert thinking.finish() == '<thi'


# --- 줄과 조각 ---


@pytest.mark.parametrize(
    ('line', 'data'),
    [('data: {"a":1}', '{"a":1}'), ('data:{"a":1}', '{"a":1}'), ('data: [DONE]', '[DONE]'), ('', None)],
)
def test_the_data_is_taken_from_data_lines(line: str, data: str | None):
    assert data_of(line) == data


@pytest.mark.parametrize('line', [': keep-alive', 'event: message', 'id: 3', '{"choices":[]}'])
def test_other_lines_carry_no_data(line: str):
    assert data_of(line) is None


def test_a_text_piece_is_read():
    data = '{"model":"m","choices":[{"delta":{"content":"글"},"finish_reason":null}]}'

    assert parse_chunk(data) == Chunk(text='글', model='m')


def test_the_last_pieces_carry_the_finish_and_the_counts():
    finish = parse_chunk('{"choices":[{"delta":{},"finish_reason":"stop"}]}')
    usage = parse_chunk('{"choices":[],"usage":{"prompt_tokens":21,"completion_tokens":53}}')

    assert finish == Chunk(finish_reason='stop')
    assert usage == Chunk(input_tokens=21, output_tokens=53)


def test_the_thinking_field_is_not_read():
    data = '{"choices":[{"delta":{"reasoning":"' + SECRET + '"},"finish_reason":null}]}'

    assert parse_chunk(data) == Chunk()


def test_an_error_piece_is_a_stream_error_without_its_content():
    with pytest.raises(ProviderError) as caught:
        parse_chunk('{"error":{"message":"' + SECRET + '"}}')

    assert str(caught.value) == 'stream_error'


@pytest.mark.parametrize(
    'data',
    [
        'not json',
        '{}',
        '[]',
        '"text"',
        '{"choices":"text"}',
        '{"choices":[{"delta":"text"}]}',
        '{"choices":[{"delta":{"content":3}}]}',
        '{"choices":[],"usage":"many"}',
    ],
)
def test_a_piece_of_the_wrong_shape_is_malformed(data: str):
    with pytest.raises(ProviderError) as caught:
        parse_chunk(data)

    assert str(caught.value) == 'malformed'


def test_the_state_keeps_the_model_that_answered():
    state = StreamState(MODEL)

    state.add(Chunk(text='가', model='gemma4:26b-a4b'))
    state.add(Chunk(text='나'))

    assert state.to_completion().model == 'gemma4:26b-a4b'


# --- 끝까지 읽기 ---


async def test_reading_hands_on_pieces_and_returns_the_answer():
    received: list[str] = []

    completion = await read_stream(
        lines(chunk_line('엔진 소리가 '), '', chunk_line('메운다.'), chunk_line('', 'stop'), 'data: [DONE]'),
        MODEL,
        received.append,
    )

    assert received == ['엔진 소리가 ', '메운다.']
    assert completion.text == '엔진 소리가 메운다.'
    assert completion.model == MODEL
    assert completion.finish_reason == 'stop'


async def test_reading_stops_at_done():
    completion = await read_stream(lines(chunk_line('가'), 'data: [DONE]', chunk_line('나')), MODEL, lambda text: None)

    assert completion.text == '가'


@pytest.mark.parametrize('ending', [[chunk_line('', 'stop')], ['data: [DONE]']])
async def test_either_the_finish_or_done_means_the_answer_is_whole(ending: list[str]):
    completion = await read_stream(lines(chunk_line('가'), *ending), MODEL, lambda text: None)

    assert completion.text == '가'


async def test_lines_that_end_before_the_answer_is_whole_are_interrupted():
    received: list[str] = []

    with pytest.raises(ProviderError) as caught:
        await read_stream(lines(chunk_line('가'), chunk_line('나<thi')), MODEL, received.append)

    assert str(caught.value) == 'interrupted'
    # 붙잡아 둔 것은 끝까지 받은 것을 확인한 뒤에야 넘긴다
    assert received == ['가', '나']


async def test_what_was_held_is_handed_on_once_the_answer_is_whole():
    received: list[str] = []

    completion = await read_stream(lines(chunk_line('장면<thi'), chunk_line('', 'stop')), MODEL, received.append)

    assert received == ['장면', '<thi']
    assert ''.join(received) == completion.text


async def test_a_length_finish_marks_the_answer_truncated():
    completion = await read_stream(lines(chunk_line('가', 'length')), MODEL, lambda text: None)

    assert completion.truncated is True


# --- 가짜 provider ---


@pytest.mark.parametrize(('text', 'size'), [(SCENE, 4), (SCENE, 1), (SCENE, 100), ('', 4)])
def test_split_pieces_join_to_the_text(text: str, size: int):
    pieces = split_text(text, size)

    assert ''.join(pieces) == text
    assert all(0 < len(piece) <= size for piece in pieces)


async def test_the_fake_provider_hands_on_pieces_that_join_to_its_reply():
    received: list[str] = []
    provider = FakeProvider(reply=SCENE, piece_size=3)

    completion = await provider.complete([], GenerationParams(max_tokens=10, temperature=0.0), received.append)

    assert len(received) > 1
    assert ''.join(received) == completion.text == SCENE
