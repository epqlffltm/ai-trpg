# shared/server-core/src/server_core/stop_signals.py

"""
서버 사이로 "이 생성을 멈춰라"를 알리는 것(#674). chat 과 story 가 쓴다.

멈추는 스위치는 그 생성을 돌리는 서버의 메모리에 있다(서버의 app.state.stops). 서버가 여럿이면 멈추기 요청이
다른 서버에 닿는다. 그 서버는 PostgreSQL 의 NOTIFY 로 알리고(announce), 모든 서버가 LISTEN 으로 듣다가
(StopListener) 그 생성을 돌리는 서버만 멈춘다.

  - 채널은 스키마마다 따로다(channel_name). 서버들이 DB 하나를 함께 쓰고 채널은 DB 전체에 하나라서,
    chat 과 story, 테스트 스키마의 알림이 섞이지 않게 한다
  - 알림에는 생성의 id 만 싣는다. 주인인지는 알리는 서버가 DB 로 맞춰 본 뒤에 알린다.
    NOTIFY 에는 권한 검사가 없지만 id 는 맞힐 수 없는 UUID 이고,
    거짓 알림이 할 수 있는 것은 멈추기(받은 만큼 저장하고 청구)뿐이라 서명(trpg 의 실시간 신호)은 하지 않는다
  - 듣는 데는 연결 하나를 계속 쥔다. 요청이 빌리는 풀과 따로 맺는다(서버 프로세스마다 하나).
    끊기면 몇 초 뒤 다시 맺는다. 끊긴 사이의 알림은 잃는다(사람이 다시 누르면 된다)
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

import asyncpg
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 채널 이름의 끝. 스키마의 이름(영문 소문자, 숫자, _)과 붙여 식별자가 된다
CHANNEL_SUFFIX = '_stops'
# 듣는 연결을 맺을 때 기다리는 최대 시간(초)
CONNECT_TIMEOUT_SECONDS = 5
# 듣고 있는지 보고 끊겼으면 다시 맺는 간격(초)
CHECK_EVERY_SECONDS = 5.0
# 듣는 연결을 맺다가 날 수 있는 실패. 연결이 안 됨, 시간 초과, DB 가 거절함
LISTEN_ERRORS = (OSError, TimeoutError, asyncpg.PostgresError)

Connect = Callable[[str], Awaitable[asyncpg.Connection]]
OnStop = Callable[[uuid.UUID], object]


def channel_name(schema: str) -> str:
    """스키마의 멈추기 채널."""
    return f'{schema}{CHANNEL_SUFFIX}'


def listen_dsn(database_url: str) -> str:
    """듣는 연결의 주소. SQLAlchemy 용 표시(+asyncpg)를 뗀 것이다. LISTEN 은 asyncpg 로 직접 맺는다."""
    return make_url(database_url).set(drivername='postgresql').render_as_string(hide_password=False)


def decode(payload: str) -> uuid.UUID | None:
    """알림의 글에서 생성의 id. 알아볼 수 없으면 None."""
    try:
        return uuid.UUID(payload)
    except ValueError:
        return None


async def announce(session: AsyncSession, channel: str, generation_id: uuid.UUID) -> None:
    """멈추라고 알린다. NOTIFY 는 트랜잭션이 끝날 때 나가므로 여기서 커밋한다."""
    await session.execute(
        text('SELECT pg_notify(:channel, :payload)'), {'channel': channel, 'payload': str(generation_id)}
    )
    await session.commit()


async def connect_listener(dsn: str) -> asyncpg.Connection:
    """듣는 연결을 맺는다."""
    return await asyncpg.connect(dsn, timeout=CONNECT_TIMEOUT_SECONDS)


class StopListener:
    """
    멈추기 채널을 듣다가 알림마다 on_stop(생성의 id)을 부른다.
    on_stop 은 이 서버에 그 생성이 없으면 아무것도 하지 않는다.

    몇 초마다 도는 작업의 모양(server_core/loops.py 의 Loop)이다. 서버가 뜰 때 띄우고 꺼질 때 멈춘다.
    연결을 맺지 못해도 예외를 올리지 않는다. 이 서버로 온 멈추기는 알림 없이도 된다.
    """

    def __init__(
        self,
        dsn: str,
        channel: str,
        on_stop: OnStop,
        connect: Connect = connect_listener,
        every: float = CHECK_EVERY_SECONDS,
    ) -> None:
        self._dsn = dsn
        self._channel = channel
        self._on_stop = on_stop
        self._connect = connect
        self._every = every
        self._connection: asyncpg.Connection | None = None

    def is_listening(self) -> bool:
        """듣는 연결이 살아 있는가."""
        return self._connection is not None and not self._connection.is_closed()

    async def ensure_listening(self) -> bool:
        """듣고 있지 않으면 연결을 맺고 듣기 시작한다. 실패는 종류만 남긴다(글에 접속 주소가 들 수 있다)."""
        if self.is_listening():
            return True
        try:
            self._connection = await self._listen()
        except LISTEN_ERRORS as error:
            logger.warning(
                '멈추기 알림을 듣는 연결을 맺지 못했다(%s). 다른 서버의 멈추기는 닿지 않는다', type(error).__name__
            )
            return False
        return True

    async def _listen(self) -> asyncpg.Connection:
        """연결을 맺고 채널을 듣기 시작한다. 듣기를 걸다 실패하면 맺은 연결을 닫는다."""
        connection = await self._connect(self._dsn)
        try:
            await connection.add_listener(self._channel, self._on_notify)
        except BaseException:
            await connection.close()
            raise
        return connection

    def _on_notify(self, connection: asyncpg.Connection, pid: int, channel: str, payload: str) -> None:
        """알림이 왔을 때 asyncpg 가 부른다. 알아볼 수 있는 id 면 넘긴다."""
        generation_id = decode(payload)
        if generation_id is not None:
            self._on_stop(generation_id)

    async def run(self, stop: asyncio.Event) -> None:
        """stop 이 켜질 때까지 듣는다. 끊기면 다음 바퀴에 다시 맺는다. 끝날 때 연결을 닫는다."""
        try:
            while not stop.is_set():
                await self.ensure_listening()
                try:
                    await asyncio.wait_for(stop.wait(), timeout=self._every)
                except TimeoutError:
                    continue
        finally:
            await self.close()

    async def close(self) -> None:
        """연결을 닫는다."""
        connection, self._connection = self._connection, None
        if connection is not None and not connection.is_closed():
            await connection.close()
