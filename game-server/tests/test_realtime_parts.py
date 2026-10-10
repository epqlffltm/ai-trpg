# game-server/tests/test_realtime_parts.py

"""
스트림을 이루는 작은 부품들을 검증한다. DB 도 서버도 쓰지 않는다.

  - 신호와 서술의 조각을 글자로 바꾸고 되돌리기(signals)
  - 방송실: 기다리는 자리를 깨우기(hub)
  - 저장하지 않는 것(입력 중, 서술의 조각)을 메시지로 바꾸기(service)
  - SSE 의 글자 형식(sse)
  - 어디까지 받았는지를 요청에서 읽기(router.read_cursor)
"""

import asyncio
import json
import uuid

import pytest
from fastapi import HTTPException, status

from app.realtime import signals, sse
from app.realtime.hub import Hub
from app.realtime.router import read_cursor
from app.realtime.service import (
    NARRATION_FRAME,
    Cursor,
    live_frames,
    narration_frames,
    typing_frames,
    wake_interval,
)
from app.realtime.signals import MAX_PIECE_CHARS, Kind, NarrationPiece, Signal, narration_pieces
from app.realtime.sse import Comment, Frame

TABLE = uuid.UUID('aaaaaaaa-2222-4333-8444-555555555555')
OTHER_TABLE = uuid.UUID('bbbbbbbb-2222-4333-8444-555555555555')
SOMEONE = uuid.UUID('22222222-2222-4333-8444-555555555555')

# 기다려도 오지 않는 것을 확인할 때 주는 시간(초)
SHORT = 0.05


# --- 신호 ---


@pytest.mark.parametrize(
    'signal',
    [
        Signal(table_id=TABLE, kind=Kind.EVENTS),
        Signal(table_id=TABLE, kind=Kind.MESSAGES),
        # 입력 중 신호에는 누구인지가 실린다
        Signal(table_id=TABLE, kind=Kind.TYPING, user_id=SOMEONE),
    ],
)
def test_a_signal_survives_the_channel(signal: Signal):
    assert signals.decode(signals.encode(signal)) == signal


@pytest.mark.parametrize(
    'payload',
    [
        '',
        'hello',
        f'{TABLE}',
        f'{TABLE}:',
        f'{TABLE}:dancing',
        f'not-a-uuid:{Kind.EVENTS}',
        # 입력 중인데 누구인지 없다
        f'{TABLE}:{Kind.TYPING}',
        f'{TABLE}:{Kind.TYPING}:not-a-uuid',
    ],
)
def test_an_unknown_signal_is_dropped(payload: str):
    # 모르는 종류나 깨진 글자가 와도 듣는 쪽이 죽지 않는다
    assert signals.decode(payload) is None


def piece(seq: int, text: str = '엔진 소리가', attempt: int = 1, round_number: int = 3) -> NarrationPiece:
    """이 테이블의 서술의 조각 하나."""
    return NarrationPiece(TABLE, round_number, attempt, seq, text)


@pytest.mark.parametrize(
    'text',
    [
        '엔진 소리가 골목을 메운다.',
        # 글에 나누는 글자(:)가 있어도, 줄이 바뀌어도 그대로다
        '사이렌: 멈춰라!\n\n드워프: 싫다.',
        '',
    ],
)
def test_a_narration_piece_survives_the_channel(text: str):
    sent = piece(seq=7, text=text)

    assert signals.decode(signals.encode(sent)) == sent


@pytest.mark.parametrize(
    'payload',
    [
        f'{TABLE}:{Kind.NARRATION}',
        f'{TABLE}:{Kind.NARRATION}:3:1',
        f'{TABLE}:{Kind.NARRATION}:3:1:0',
        f'{TABLE}:{Kind.NARRATION}:three:1:0:글',
        f'not-a-uuid:{Kind.NARRATION}:3:1:0:글',
    ],
)
def test_a_broken_narration_piece_is_dropped(payload: str):
    assert signals.decode(payload) is None


def test_the_largest_piece_fits_in_a_notify():
    # 한 글자에 4 바이트인 글자로 꽉 채운 조각. 번호들도 크게 잡는다
    largest = NarrationPiece(TABLE, 99999, 99, 99999, '🏍' * MAX_PIECE_CHARS)

    assert len(signals.encode(largest).encode()) < 8000


def test_a_long_text_is_split_into_numbered_pieces():
    text = '가' * (MAX_PIECE_CHARS * 2 + 1)

    pieces = narration_pieces(TABLE, 3, 2, 5, text)

    assert [(each.seq, len(each.text)) for each in pieces] == [(5, MAX_PIECE_CHARS), (6, MAX_PIECE_CHARS), (7, 1)]
    assert {(each.round_number, each.attempt) for each in pieces} == {(3, 2)}
    assert ''.join(each.text for each in pieces) == text


def test_an_empty_text_makes_no_pieces():
    assert narration_pieces(TABLE, 3, 1, 0, '') == []


def test_each_schema_has_its_own_channel():
    assert signals.channel_name('game') != signals.channel_name('game_test')


# --- 방송실 ---


async def test_a_signal_wakes_everyone_waiting_for_that_table():
    hub = Hub()

    with hub.subscribe(TABLE) as first, hub.subscribe(TABLE) as second, hub.subscribe(OTHER_TABLE) as other:
        signal = Signal(table_id=TABLE, kind=Kind.MESSAGES)
        hub.wake(signal)

        assert await first.wait(SHORT) == {signal}
        assert await second.wait(SHORT) == {signal}
        # 다른 테이블을 기다리는 사람은 깨지 않는다
        assert await other.wait(SHORT) is None


async def test_waiting_gives_up_after_the_timeout():
    hub = Hub()

    with hub.subscribe(TABLE) as subscription:
        assert await subscription.wait(SHORT) is None


async def test_a_signal_that_comes_while_not_waiting_is_kept():
    hub = Hub()

    with hub.subscribe(TABLE) as subscription:
        # 기다리지 않는 동안(DB 를 읽는 중이라고 치자) 신호가 둘 온다
        events, messages = Signal(table_id=TABLE, kind=Kind.EVENTS), Signal(table_id=TABLE, kind=Kind.MESSAGES)
        hub.wake(events)
        hub.wake(messages)
        # 같은 신호가 또 와도 하나로 친다
        hub.wake(events)

        # 다음에 기다리면 바로 돌아오고, 둘 다 들어 있다
        assert await subscription.wait(SHORT) == {events, messages}
        # 꺼내 간 것은 비워진다
        assert await subscription.wait(SHORT) is None


async def test_a_waiting_subscriber_wakes_as_soon_as_the_signal_comes():
    hub = Hub()

    with hub.subscribe(TABLE) as subscription:
        waiting = asyncio.create_task(subscription.wait(5))
        await asyncio.sleep(SHORT)
        signal = Signal(table_id=TABLE, kind=Kind.EVENTS)
        hub.wake(signal)

        assert await asyncio.wait_for(waiting, 1) == {signal}


def test_the_seat_is_removed_when_the_stream_ends():
    hub = Hub()

    with hub.subscribe(TABLE), hub.subscribe(TABLE):
        assert hub.count(TABLE) == 2

    assert hub.count(TABLE) == 0


def test_the_seat_is_removed_even_when_the_stream_fails():
    hub = Hub()

    with pytest.raises(RuntimeError), hub.subscribe(TABLE):
        raise RuntimeError('연결이 끊겼다')

    assert hub.count(TABLE) == 0


def test_waking_a_table_nobody_waits_for_does_nothing():
    Hub().wake(Signal(table_id=TABLE, kind=Kind.EVENTS))


async def test_pieces_with_the_same_text_are_all_kept():
    hub = Hub()

    with hub.subscribe(TABLE) as subscription:
        # 같은 글이라도 번호가 다르면 다른 조각이다. 하나로 합쳐지면 글이 빠진다
        hub.wake(piece(0, '하'))
        hub.wake(piece(1, '하'))

        assert await subscription.wait(SHORT) == {piece(0, '하'), piece(1, '하')}


async def test_closing_wakes_the_waiting_at_once():
    hub = Hub()

    with hub.subscribe(TABLE) as subscription:
        waiting = asyncio.create_task(subscription.wait(5))
        await asyncio.sleep(SHORT)
        hub.close_all()

        # 신호가 없어도 바로 깨어나고, 닫혔다는 것을 안다
        assert await asyncio.wait_for(waiting, 1) == set()
        assert subscription.is_closed()


async def test_a_closed_seat_never_waits_again():
    hub = Hub()

    with hub.subscribe(TABLE) as subscription:
        hub.close_all()

        assert await asyncio.wait_for(subscription.wait(5), 1) == set()
        assert await asyncio.wait_for(subscription.wait(5), 1) == set()


async def test_closing_reaches_every_table():
    hub = Hub()

    with hub.subscribe(TABLE) as first, hub.subscribe(OTHER_TABLE) as second:
        hub.close_all()

        assert first.is_closed() and second.is_closed()


async def test_a_seat_taken_after_closing_is_closed_from_the_start():
    hub = Hub()
    hub.close_all()

    # 서버가 꺼지는 중에 붙은 스트림도 바로 끝난다
    with hub.subscribe(TABLE) as subscription:
        assert subscription.is_closed()


def test_an_open_hub_does_not_close_anyone():
    hub = Hub()

    with hub.subscribe(TABLE) as subscription:
        hub.wake(Signal(table_id=TABLE, kind=Kind.EVENTS))

        assert not subscription.is_closed()


@pytest.mark.parametrize(
    ('listening', 'heartbeat', 'expected'),
    [(True, 15.0, 15.0), (False, 15.0, 5.0), (False, 0.2, 0.2)],
)
def test_a_stream_that_cannot_hear_signals_wakes_more_often(listening: bool, heartbeat: float, expected: float):
    assert wake_interval(heartbeat, 5.0, listening) == expected


# --- 저장하지 않는 것 ---


def test_pieces_received_out_of_order_are_sent_in_order():
    received = {piece(2, '메운다.'), piece(0, '엔진 소리가 '), piece(1, '골목을 '), piece(0, '다시', attempt=2)}

    frames = narration_frames(received)

    assert {frame.event for frame in frames} == {NARRATION_FRAME}
    assert [frame.id for frame in frames] == [None] * 4
    assert [json.loads(frame.data) for frame in frames] == [
        {'round': 3, 'attempt': 1, 'seq': 0, 'text': '엔진 소리가 '},
        {'round': 3, 'attempt': 1, 'seq': 1, 'text': '골목을 '},
        {'round': 3, 'attempt': 1, 'seq': 2, 'text': '메운다.'},
        {'round': 3, 'attempt': 2, 'seq': 0, 'text': '다시'},
    ]


def test_typing_ignores_pieces_and_pieces_ignore_typing():
    typing = Signal(table_id=TABLE, kind=Kind.TYPING, user_id=SOMEONE)
    received = {typing, piece(0)}

    assert len(typing_frames(received, viewer_id=TABLE)) == 1
    assert len(narration_frames(received)) == 1


def test_typing_comes_before_the_pieces():
    received = {piece(0), Signal(table_id=TABLE, kind=Kind.TYPING, user_id=SOMEONE)}

    assert [frame.event for frame in live_frames(received, viewer_id=TABLE)] == ['typing', NARRATION_FRAME]


# --- SSE 의 글자 형식 ---


def test_a_frame_is_written_as_id_event_data_and_a_blank_line():
    frame = Frame(event='chat_message', data='{"content": "안녕"}', id='17-5')

    assert sse.encode(frame) == 'id: 17-5\nevent: chat_message\ndata: {"content": "안녕"}\n\n'


def test_a_frame_without_an_id_has_no_id_line():
    # 저장하지 않는 메시지에는 id 가 없다. 받는 쪽의 "여기까지 받았다"가 움직이지 않는다
    assert sse.encode(Frame(event='closed', data='{}')) == 'event: closed\ndata: {}\n\n'


def test_every_line_of_the_data_gets_its_own_data_line():
    assert sse.encode(Frame(event='note', data='첫 줄\n둘째 줄')) == 'event: note\ndata: 첫 줄\ndata: 둘째 줄\n\n'


def test_a_comment_starts_with_a_colon():
    assert sse.encode(Comment('ping')) == ': ping\n\n'


# --- 어디까지 받았는가 ---


def test_the_cursor_marks_both_numbers():
    assert Cursor(events=17, messages=5).mark() == '17-5'


def test_reads_the_cursor_from_the_address_when_there_is_no_header():
    assert read_cursor(None, events_after=17, messages_after=5) == Cursor(events=17, messages=5)


def test_the_header_wins_over_the_address():
    # 다시 붙는 쪽은 처음 붙을 때의 주소를 그대로 쓴다. 머리말이 더 새로운 값이다
    assert read_cursor('20-9', events_after=17, messages_after=5) == Cursor(events=20, messages=9)


@pytest.mark.parametrize('mark', ['', '17', '17-', '-5', '17-5-1', 'a-b', '17 - 5', '-1-5', '99999999999-1'])
def test_rejects_a_header_that_is_not_a_mark(mark: str):
    with pytest.raises(HTTPException) as raised:
        read_cursor(mark, events_after=0, messages_after=0)

    assert raised.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
