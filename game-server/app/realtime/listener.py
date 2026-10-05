# game-server/app/realtime/listener.py

"""
신호를 받는 쪽. PostgreSQL 의 LISTEN 으로 신호를 듣고 방송실(hub)에 넘긴다.

듣는 데는 연결 하나를 계속 붙잡고 있어야 한다. 요청마다 빌려 쓰는 풀의 연결과 따로, 전용 연결을 하나 연다.
서버 프로세스마다 하나다. 스트림이 몇 개든 늘지 않는다.

다른 것(Redis Pub/Sub 등)으로 바꿀 때는 SignalSource 의 모양을 지키는 클래스를 새로 쓰고 app/main.py 에서 바꿔 끼운다.
"""

import asyncio
from typing import Protocol

import asyncpg
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.realtime import signals
from app.realtime.hub import Hub

# 듣는 연결을 맺을 때 기다리는 최대 시간(초)
CONNECT_TIMEOUT_SECONDS = 5


class SignalSource(Protocol):
    """신호를 받아 방송실에 넘기는 것의 모양."""

    async def ensure_listening(self) -> None:
        """듣고 있지 않으면 듣기 시작한다. 이미 듣고 있으면 아무 일도 하지 않는다."""
        ...

    async def stop(self) -> None:
        """듣기를 멈추고 연결을 닫는다."""
        ...


def listen_dsn(settings: Settings) -> str:
    """
    듣는 연결의 주소. 설정의 DB 주소에서 SQLAlchemy 용 표시(+asyncpg)를 뗀 것이다.

    이 연결은 SQLAlchemy 를 거치지 않고 asyncpg 로 직접 맺는다. LISTEN 은 asyncpg 의 기능이다.
    """
    return make_url(settings.database_url).set(drivername='postgresql').render_as_string(hide_password=False)


class PostgresListener:
    """
    PostgreSQL 의 LISTEN 으로 신호를 듣는다.

    만드는 것만으로는 연결하지 않는다. 처음 스트림이 열릴 때 연결한다(ensure_listening).
    연결이 끊기면 다음 ensure_listening 이 다시 맺는다. 스트림은 주기적으로 이것을 부른다.
    끊긴 사이의 신호는 잃지만, 스트림이 주기적으로 DB 를 직접 읽으므로 내용은 잃지 않는다.
    """

    def __init__(self, settings: Settings, hub: Hub) -> None:
        self._dsn = listen_dsn(settings)
        self._channel = signals.channel_name(settings.db_schema)
        self._hub = hub
        self._connection: asyncpg.Connection | None = None
        # 여러 스트림이 동시에 처음 열려도 연결은 하나만 맺는다
        self._connecting = asyncio.Lock()

    def is_listening(self) -> bool:
        """듣는 연결이 살아 있는가."""
        return self._connection is not None and not self._connection.is_closed()

    async def ensure_listening(self) -> None:
        """듣고 있지 않으면 연결을 맺고 듣기 시작한다."""
        if self.is_listening():
            return
        async with self._connecting:
            # 잠금을 기다리는 사이에 다른 쪽이 이미 맺었을 수 있다
            if self.is_listening():
                return
            connection = await asyncpg.connect(self._dsn, timeout=CONNECT_TIMEOUT_SECONDS)
            await connection.add_listener(self._channel, self._on_notify)
            self._connection = connection

    def _on_notify(self, connection: asyncpg.Connection, pid: int, channel: str, payload: str) -> None:
        """신호가 왔을 때 asyncpg 가 부른다. 알아볼 수 있는 신호면 방송실에 넘긴다."""
        signal = signals.decode(payload)
        if signal is not None:
            self._hub.wake(signal)

    async def stop(self) -> None:
        """연결을 닫는다. 서버가 꺼질 때 부른다."""
        connection, self._connection = self._connection, None
        if connection is not None and not connection.is_closed():
            await connection.close()
