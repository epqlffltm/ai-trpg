# shared/server-core/tests/test_stop_signals.py

"""
서버 사이의 멈추기 알림(server_core/stop_signals.py)을 DB 없이 검증한다. 연결은 가짜다.
실제 NOTIFY 와 LISTEN 은 쓰는 서버(chat, story)의 테스트가 실제 DB 로 본다.

보는 것.
  - 채널은 스키마마다 따로고, 듣는 주소는 SQLAlchemy 의 표시를 뗀다
  - 알림의 글이 UUID 면 넘기고 아니면 버린다
  - 연결을 맺지 못하면 예외 없이 False 이고 다음 바퀴에 다시 맺는다. 듣기를 걸다 실패하면 맺은 연결을 닫는다
  - 멈추면 연결을 닫는다
"""

import asyncio
import logging
import uuid

import pytest

from server_core import loops
from server_core.stop_signals import StopListener, channel_name, decode, listen_dsn

DSN = 'postgresql://chat:pw@127.0.0.1:5432/trpg'


class FakeConnection:
    """asyncpg 의 연결 흉내. 듣기를 건 채널과 부를 것을 적는다."""

    def __init__(self, refuse_listen: bool = False) -> None:
        self.refuse_listen = refuse_listen
        self.listeners: dict[str, object] = {}
        self.closed = False

    async def add_listener(self, channel: str, callback) -> None:
        if self.refuse_listen:
            raise OSError('listen refused')
        self.listeners[channel] = callback

    def is_closed(self) -> bool:
        return self.closed

    async def close(self) -> None:
        self.closed = True


class FakeConnect:
    """맺을 때마다 차례로 실패나 연결을 돌려준다."""

    def __init__(self, *results: object) -> None:
        self.results = list(results)
        self.dsns: list[str] = []

    async def __call__(self, dsn: str) -> FakeConnection:
        self.dsns.append(dsn)
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def test_each_schema_has_its_own_channel_and_the_dsn_drops_the_driver():
    assert (channel_name('chat'), channel_name('story_test')) == ('chat_stops', 'story_test_stops')
    assert listen_dsn('postgresql+asyncpg://chat:pw@127.0.0.1:5432/trpg') == DSN


def test_only_a_uuid_is_a_stop():
    generation_id = uuid.uuid4()

    assert decode(str(generation_id)) == generation_id
    assert decode('not-a-uuid') is None


async def test_a_notice_reaches_on_stop_and_junk_is_dropped():
    connection = FakeConnection()
    stopped: list[uuid.UUID] = []
    listener = StopListener(DSN, 'chat_stops', stopped.append, connect=FakeConnect(connection))
    generation_id = uuid.uuid4()

    assert await listener.ensure_listening()
    callback = connection.listeners['chat_stops']
    callback(connection, 1, 'chat_stops', str(generation_id))
    callback(connection, 1, 'chat_stops', 'junk')

    assert stopped == [generation_id]


async def test_a_failed_connect_is_quiet_and_retried(caplog: pytest.LogCaptureFixture):
    connection = FakeConnection()
    connect = FakeConnect(OSError('refused with a secret dsn'), connection)
    listener = StopListener(DSN, 'chat_stops', lambda _: None, connect=connect)

    with caplog.at_level(logging.WARNING):
        assert not await listener.ensure_listening()
    assert await listener.ensure_listening()

    assert listener.is_listening()
    # 실패의 글(접속 주소가 들 수 있다)은 남기지 않는다
    assert 'secret' not in caplog.text and 'OSError' in caplog.text


async def test_a_failed_listen_closes_the_connection():
    connection = FakeConnection(refuse_listen=True)
    listener = StopListener(DSN, 'chat_stops', lambda _: None, connect=FakeConnect(connection))

    assert not await listener.ensure_listening()
    assert connection.closed


async def test_the_loop_reconnects_and_closes_when_halted():
    first, second = FakeConnection(), FakeConnection()
    connect = FakeConnect(first, second)
    listener = StopListener(DSN, 'chat_stops', lambda _: None, connect=connect, every=0.01)
    running = loops.start(listener, 'stop-listener')
    while not listener.is_listening():
        await asyncio.sleep(0.01)

    # 연결이 끊기면 다음 바퀴에 다시 맺는다
    first.closed = True
    while connect.results:
        await asyncio.sleep(0.01)
    await running.halt()

    assert connect.dsns == [DSN, DSN]
    assert second.closed
