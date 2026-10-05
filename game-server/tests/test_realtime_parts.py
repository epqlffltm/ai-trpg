# game-server/tests/test_realtime_parts.py

"""
스트림을 이루는 작은 부품들을 검증한다. DB 도 서버도 쓰지 않는다.

  - 신호를 글자로 바꾸고 되돌리기(signals)
  - 방송실: 기다리는 자리를 깨우기(hub)
  - SSE 의 글자 형식(sse)
  - 어디까지 받았는지를 요청에서 읽기(router.read_cursor)
"""

import asyncio
import uuid

import pytest
from fastapi import HTTPException, status

from app.realtime import signals, sse
from app.realtime.hub import Hub
from app.realtime.router import read_cursor
from app.realtime.service import Cursor
from app.realtime.signals import Kind, Signal
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
