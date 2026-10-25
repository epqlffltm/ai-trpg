# story-server/tests/test_turn_segments.py

"""
말 조각 나누기(app/turns/segments.py)를 검증한다. 순수 함수라 DB 도 앱도 없다.

보는 것.
  - 표식의 이름: 인물의 id 와 이름, 서술(narration, 서술)을 받는다. 대소문자를 가리지 않는다
  - 장면에 없는 인물의 줄은 버리고 센다. 표식을 어긴 줄은 서술이다. 빈 줄은 버린다
  - 흘러오는 대로 자른다: 머리를 다 받기 전에는 내보내지 않고, 정해지면 받는 대로 내보낸다. 어디서 잘려 와도 같다
  - 끝나면 남은 줄을 마저 자른다. 표식을 붙인 줄로 다시 쓰면 같은 조각이 된다
"""

import pytest

from app.turns.segments import (
    Segment,
    SegmentStart,
    SegmentText,
    SpeakerSplitter,
    merge_events,
    render_segments,
    segment_dicts,
    speaker_labels,
    split_segments,
)

LABELS = speaker_labels([('mina', '미나'), ('jun', '준')])


def test_labels_take_ids_and_names_case_insensitively():
    assert LABELS == {'mina': 'mina', 'jun': 'jun', '미나': 'mina', '준': 'jun'}
    assert speaker_labels([('Mina', 'MINA')]) == {'mina': 'Mina'}


def test_a_name_that_clashes_is_not_a_label():
    # 서술의 표식과 같은 이름, 다른 인물의 id 와 같은 이름은 이름으로 받지 않는다
    labels = speaker_labels([('a', 'narration'), ('b', 'a'), ('c', '')])

    assert labels == {'a': 'a', 'b': 'b', 'c': 'c'}


def test_lines_become_segments():
    text = '@narration: 해가 진다.\n@mina: 늦었네.\n@준: 미안.\n@서술: 바람.'

    segments, dropped = split_segments(text, LABELS)

    assert segments == (
        Segment(None, '해가 진다.'),
        Segment('mina', '늦었네.'),
        Segment('jun', '미안.'),
        Segment(None, '바람.'),
    )
    assert dropped == 0


def test_a_speaker_outside_the_scene_is_dropped_and_counted():
    segments, dropped = split_segments('@mina: 안녕.\n@sora: 나도 있어.\n@sora: 정말로.\n@narration: 끝.', LABELS)

    assert [segment.speaker for segment in segments] == ['mina', None]
    assert dropped == 2


@pytest.mark.parametrize(
    'line',
    [
        '그냥 쓴 줄.',
        '@: 이름이 없다.',
        '@이름이 너무 길어서 표식이 아니라고 봐야 하는 줄은 서술로 돌린다 마침표.',
        '@mina 콜론이 없다',
    ],
)
def test_a_line_breaking_the_marker_is_narration(line: str):
    segments, dropped = split_segments(line, LABELS)

    assert segments == (Segment(None, line),)
    assert dropped == 0


def test_blank_lines_and_empty_markers_are_skipped():
    segments, _ = split_segments('\n\n@mina:   \n  @jun:  응.  \r\n\n', LABELS)

    assert segments == (Segment('jun', '응.'),)


def stream(pieces: list[str]) -> tuple[list, SpeakerSplitter]:
    splitter = SpeakerSplitter(LABELS)
    events = []
    for piece in pieces:
        events.extend(splitter.feed(piece))
    events.extend(splitter.finish())
    return merge_events(events), splitter


def test_text_waits_for_the_marker_then_flows():
    splitter = SpeakerSplitter(LABELS)

    assert splitter.feed('@mi') == []
    assert merge_events(splitter.feed('na: 안')) == [SegmentStart('mina'), SegmentText('안')]
    assert merge_events(splitter.feed('녕\n@narr')) == [SegmentText('녕')]
    assert merge_events(splitter.feed('ation: 바람')) == [SegmentStart(None), SegmentText('바람')]


def test_streaming_gives_the_same_segments_however_it_is_cut():
    text = '@narration: 문이 열린다.\n@mina: 왔구나!\n@sora: 숨은 사람.\n그리고 정적.'
    whole, _ = split_segments(text, LABELS)

    for size in (1, 2, 3, 7, len(text)):
        events, splitter = stream([text[i : i + size] for i in range(0, len(text), size)])
        assert splitter.segments() == whole
        assert splitter.dropped == 1
        assert events == [
            SegmentStart(None),
            SegmentText('문이 열린다.'),
            SegmentStart('mina'),
            SegmentText('왔구나!'),
            SegmentStart(None),
            SegmentText('그리고 정적.'),
        ]


def test_an_unfinished_last_line_is_kept_on_finish():
    events, splitter = stream(['@mina: 그러니까', ' 말이야'])

    assert splitter.segments() == (Segment('mina', '그러니까 말이야'),)
    assert events == [SegmentStart('mina'), SegmentText('그러니까 말이야')]


def test_a_cut_marker_at_the_end_is_narration():
    _, splitter = stream(['@mi'])

    assert splitter.segments() == (Segment(None, '@mi'),)


def test_rendering_round_trips():
    segments = (Segment(None, '해가 진다.'), Segment('mina', '늦었네.'))

    rendered = render_segments(segments)

    assert rendered == '@narration: 해가 진다.\n@mina: 늦었네.'
    assert split_segments(rendered, LABELS) == (segments, 0)
    assert segment_dicts(segments) == [{'speaker': None, 'text': '해가 진다.'}, {'speaker': 'mina', 'text': '늦었네.'}]
