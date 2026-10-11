# game-server/app/rounds/preview.py

"""
쓰이는 중인 서술을 앉은 사람들에게 흘려보낸다(미리 보기). app/rounds/narrator.py 의 Preview 모양을 따른다.

서술자가 넘기는 조각을 모아 두었다가 일정한 간격(PREVIEW_INTERVAL_SECONDS)마다 신호로 보낸다.
  조각마다 보내지 않는 이유: 모델은 1초에 수십 조각을 쓴다. 조각마다 DB 에 들르면 서술 하나에 수백 번이다.
  0.3초씩 모아 보내도 사람 눈에는 흘러가는 글로 보인다.
  모으는 쪽(text)과 보내는 쪽(뒤에서 도는 작업)을 나눈다. 보내기가 느려도 모델의 답을 읽는 일은 기다리지 않는다.

저장하지 않는다. 미리 보기는 버려질 수 있는 글이다. 남는 것은 서술이 끝난 뒤의 gm_narration 이벤트다.
  - 늦게 붙은 사람은 앞부분을 못 본다. 서술이 끝나면 이벤트로 전부를 본다.
  - 신호를 놓쳐도(듣는 연결을 다시 맺는 사이) 그만이다. 조각의 번호(seq)가 비면 받는 쪽이 안다.
  - 보내기가 실패해도(DB 가 잠깐 안 됨) 서술은 계속한다. 미리 보기 때문에 서술이 실패하면 안 된다.
  - 보내기가 멈춰도(DB 가 응답하지 않음) 서술의 마무리를 붙잡지 않는다. 닫을 때 남은 글을 보낼 시간을 잠깐만 주고
    (PREVIEW_CLOSE_SECONDS), 넘으면 보내던 것을 그만둔다. 그 조각들은 잃는다.

조각에는 시도의 번호(attempt)와 시도 안의 번호(seq)를 붙인다.
  - 시도가 바뀌면(다시 시도, 다음 모델) 받는 쪽은 보던 글을 지우고 새로 받는다.
  - 받는 쪽(스트림)은 한 번에 받은 신호들을 순서 없이 들고 있다. 번호로 다시 줄 세운다.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.realtime.signals import NarrationPiece, narration_pieces, publish

logger = logging.getLogger(__name__)

# 모아 둔 조각을 보내는 간격(초)
PREVIEW_INTERVAL_SECONDS = 0.3
# 미리 보기를 닫을 때 남은 글을 보내도록 기다려 주는 시간(초). 넘으면 보내기를 그만둔다
PREVIEW_CLOSE_SECONDS = 2.0

# 조각들을 보내는 함수. 테스트가 DB 대신 목록에 쌓는 것을 꽂는다
Send = Callable[[list[NarrationPiece]], Awaitable[None]]


def notifier(session_factory: async_sessionmaker[AsyncSession]) -> Send:
    """조각들을 신호(NOTIFY)로 보내는 함수를 만든다. 보낼 때마다 세션을 잠깐 연다."""

    async def send(pieces: list[NarrationPiece]) -> None:
        async with session_factory() as session:
            for piece in pieces:
                await publish(session, piece)
            await session.commit()

    return send


@dataclass
class SignalPreview:
    """
    한 라운드의 서술을 흘려보내는 미리 보기. 라운드를 서술할 때마다 하나 만든다(open_preview).

    attempt 는 지금 시도의 번호(처음은 1), seq 는 이 시도에서 다음에 보낼 조각의 번호다.
    buffer 는 아직 보내지 않은 글이다.
    """

    send: Send
    table_id: uuid.UUID
    round_number: int
    attempt: int = 0
    seq: int = 0
    buffer: list[str] = field(default_factory=list)

    def begin(self) -> None:
        """새 시도가 시작됐다. 앞의 시도에서 아직 보내지 않은 글은 버린다."""
        self.attempt += 1
        self.seq = 0
        self.buffer.clear()

    def text(self, piece: str) -> None:
        """새로 쓴 글을 모아 둔다. 보내는 것은 뒤에서 도는 작업이 한다."""
        self.buffer.append(piece)

    def take_pieces(self) -> list[NarrationPiece]:
        """모아 둔 글을 보낼 조각들로 바꾸고 비운다. 번호를 그만큼 센다."""
        pieces = narration_pieces(self.table_id, self.round_number, self.attempt, self.seq, ''.join(self.buffer))
        self.buffer.clear()
        self.seq += len(pieces)
        return pieces

    async def flush(self) -> None:
        """모아 둔 글을 보낸다. 실패해도 예외를 올리지 않는다. 그 조각들은 잃는다."""
        pieces = self.take_pieces()
        if not pieces:
            return
        try:
            await self.send(pieces)
        except (SQLAlchemyError, OSError):
            logger.warning('서술의 미리 보기를 보내지 못했다', exc_info=True)

    async def keep_flushing(self, stop: asyncio.Event, interval: float) -> None:
        """
        stop 이 켜질 때까지 interval 초마다 보낸다. 켜지면 남은 것을 보내고 끝난다.

        보내는 도중에 stop 이 켜질 수 있다. 그사이에 모인 글이 있으므로 끝나기 전에 한 번 더 보낸다.
        """
        while not stop.is_set():
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), interval)
            await self.flush()
        await self.flush()


async def finish_flushing(flusher: asyncio.Task[None], timeout: float) -> None:
    """
    보내는 작업이 남은 글을 보내고 끝나기를 timeout 초까지 기다린다. 넘으면 그 작업을 취소하고 돌아온다.

    보내기가 멈춰 있으면(응답 없는 DB) 끝나지 않는다. 미리 보기는 잃어도 되는 글이라 기다리지 않고 버린다.
    기다리는 쪽이 취소되면 보내는 작업도 함께 취소된다.
    """
    try:
        await asyncio.wait_for(flusher, timeout)
    except TimeoutError:
        logger.warning('서술의 미리 보기를 닫지 못했다. 남은 조각은 버린다')


@asynccontextmanager
async def open_preview(
    send: Send,
    table_id: uuid.UUID,
    round_number: int,
    interval: float = PREVIEW_INTERVAL_SECONDS,
    close_timeout: float = PREVIEW_CLOSE_SECONDS,
) -> AsyncIterator[SignalPreview]:
    """
    한 라운드의 미리 보기를 연다. with 안에서 서술하고, 나가면 남은 글을 보내고 닫는다.

    서술이 성공했든 실패했든 남은 글을 보낸 뒤에 나간다. 그 뒤에 적는 이벤트(gm_narration, narration_failed)가
    미리 보기의 마지막 조각보다 늦게 나간다. 받는 쪽은 이벤트를 보고 미리 보기를 지운다.
    남은 글을 보내는 데 close_timeout 초까지만 쓴다. 미리 보기가 서술의 마무리를 붙잡지 않는다.
    """
    preview = SignalPreview(send, table_id, round_number)
    stop = asyncio.Event()
    flusher = asyncio.create_task(preview.keep_flushing(stop, interval))
    try:
        yield preview
    finally:
        stop.set()
        await finish_flushing(flusher, close_timeout)
