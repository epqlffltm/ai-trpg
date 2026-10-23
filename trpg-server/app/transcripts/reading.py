# trpg-server/app/transcripts/reading.py

"""
기록을 받을 수 있는지 보고, 받을 이벤트와 채팅과 쪽지를 쪽마다 읽어 일어난 차례로 합친다(#403, #617).

받는 사람은 둘이다.
  - 앉은 사람: 받기 시작한 때까지다. 이벤트, 채팅, 쪽지의 그때의 마지막 번호로 자른다.
    받는 동안 테이블이 이어져도 파일의 끝은 그대로다.
  - 떠난 사람: 떠났다는 이벤트까지다(app/tables/past.py 와 같다). 채팅과 쪽지는 떠난 시각까지 적힌 것이다.
    떠난 뒤의 일은 받지 않는다.
둘 다 아니면 TableNotFoundError(404)다. 테이블이 있다는 것도 드러내지 않는다.

쪽지는 받는 사람의 쪽지함(보냈거나 받은 것)에서만 읽는다. 남의 쪽지함은 읽는 길이 없다(app/whispers/repository.py).
셋 다 쪽마다 새 세션으로 읽는다. 큰 판도 메모리에 다 올리지 않고, 보내는 동안 DB 연결을 붙잡지 않는다.
"""

import heapq
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.assets.scenarios.snapshot import read_snapshot
from app.chat import repository as chats
from app.chat.models import ChatMessage
from app.events import repository as events
from app.events.models import TableEvent
from app.tables import past, repository
from app.tables import service as tables
from app.tables.errors import TableNotFoundError
from app.transcripts.labels import Labels, labels_of
from app.transcripts.story import Item
from app.whispers import repository as whispers
from app.whispers.models import Whisper

# 한 번에 읽는 이벤트(채팅, 쪽지)의 수
PAGE_SIZE = 200


@dataclass(frozen=True)
class Cut:
    """
    받을 기록의 범위. until 번까지의 이벤트, chat_until 번까지의 채팅, owner_id 의 쪽지함의 whisper_until 번까지다.

    departed 면 떠난 사람이 받는 것이다. labels 는 판의 이름들이다.
    """

    table_id: uuid.UUID
    title: str
    until: int
    departed: bool
    labels: Labels
    owner_id: uuid.UUID | None = None
    chat_until: int = 0
    whisper_until: int = 0


async def seated_cut(session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID) -> Cut:
    """앉은 사람이 받을 범위. 지금의 마지막 이벤트, 채팅, 쪽지까지다. 앉지 않았으면 TableNotFoundError."""
    table = await tables.get_table(session, user_id, table_id)
    return Cut(
        table_id=table.id,
        title=table.title,
        until=table.last_sequence,
        departed=False,
        labels=labels_of(read_snapshot(table.content)),
        owner_id=user_id,
        chat_until=await chats.last_sequence(session, table.id),
        whisper_until=await whispers.last_sequence(session, table.id, user_id),
    )


async def departed_cut(session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID) -> Cut:
    """
    떠난 사람이 받을 범위. 떠났다는 이벤트까지, 채팅과 쪽지는 떠난 시각까지다. 떠난 적이 없으면 TableNotFoundError.
    """
    departure = await past.get_departure(session, user_id, table_id)
    heading = await repository.find_heading(session, table_id)
    if heading is None:
        raise TableNotFoundError
    title, content = heading
    return Cut(
        table_id=table_id,
        title=title,
        until=departure.last_sequence,
        departed=True,
        labels=labels_of(read_snapshot(content)),
        owner_id=user_id,
        chat_until=await chats.last_sequence(session, table_id, before=departure.left_at),
        whisper_until=await whispers.last_sequence(session, table_id, user_id, before=departure.left_at),
    )


PageReader = Callable[[AsyncSession, int], Awaitable[list[Item]]]


async def iter_pages(
    session_factory: async_sessionmaker[AsyncSession], read_page: PageReader, page_size: int
) -> AsyncIterator[Item]:
    """번호 차례의 것을 쪽마다 읽어 하나씩 내놓는다. 쪽마다 세션을 열고 바로 닫는다."""
    after = 0
    while True:
        async with session_factory() as session:
            page = await read_page(session, after)
        for item in page:
            yield item
        if len(page) < page_size:
            return
        after = page[-1].sequence


async def iter_events(
    session_factory: async_sessionmaker[AsyncSession], cut: Cut, page_size: int = PAGE_SIZE
) -> AsyncIterator[TableEvent]:
    """범위 안의 이벤트를 일어난 차례대로 하나씩 내놓는다."""

    async def read_page(session: AsyncSession, after: int) -> list[TableEvent]:
        return await events.list_after(session, cut.table_id, after, page_size, until=cut.until)

    async for event in iter_pages(session_factory, read_page, page_size):
        yield event


async def iter_chats(
    session_factory: async_sessionmaker[AsyncSession], cut: Cut, page_size: int = PAGE_SIZE
) -> AsyncIterator[ChatMessage]:
    """범위 안의 채팅을 쓴 차례대로 하나씩 내놓는다. 범위가 0 이면 읽지 않는다."""
    if cut.chat_until == 0:
        return

    async def read_page(session: AsyncSession, after: int) -> list[ChatMessage]:
        return await chats.list_after(session, cut.table_id, after, page_size, until=cut.chat_until)

    async for message in iter_pages(session_factory, read_page, page_size):
        yield message


async def iter_whispers(
    session_factory: async_sessionmaker[AsyncSession], cut: Cut, page_size: int = PAGE_SIZE
) -> AsyncIterator[Whisper]:
    """받는 사람의 쪽지함에서 범위 안의 쪽지를 적힌 차례대로 하나씩 내놓는다. 범위가 0 이면 읽지 않는다."""
    if cut.owner_id is None or cut.whisper_until == 0:
        return

    async def read_page(session: AsyncSession, after: int) -> list[Whisper]:
        return await whispers.list_after(session, cut.table_id, cut.owner_id, after, page_size, until=cut.whisper_until)

    async for whisper in iter_pages(session_factory, read_page, page_size):
        yield whisper


async def merged(*streams: AsyncIterator[Item]) -> AsyncIterator[Item]:
    """
    차례대로인 흐름들을 적힌 시각(created_at)의 차례로 합친다. 같은 시각이면 앞의 흐름(이벤트, 채팅, 쪽지)이 먼저다.

    흐름마다 하나씩만 잡아 둔다. 다 모으지 않는다.
    """
    heap: list[tuple] = []
    for order, stream in enumerate(streams):
        first = await anext(stream, None)
        if first is not None:
            heap.append((first.created_at, order, first))
    heapq.heapify(heap)
    while heap:
        _, order, item = heapq.heappop(heap)
        yield item
        following = await anext(streams[order], None)
        if following is not None:
            heapq.heappush(heap, (following.created_at, order, following))


def iter_items(
    session_factory: async_sessionmaker[AsyncSession], cut: Cut, page_size: int = PAGE_SIZE
) -> AsyncIterator[Item]:
    """범위 안의 이벤트, 채팅, 쪽지를 적힌 차례로 합쳐 내놓는다."""
    return merged(
        iter_events(session_factory, cut, page_size),
        iter_chats(session_factory, cut, page_size),
        iter_whispers(session_factory, cut, page_size),
    )
