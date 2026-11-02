# story-server/app/bookmarks/service.py

"""
말의 책갈피를 달고, 떼고, 본다(#982). 세션의 주인만 한다(남의 세션은 ConversationNotFoundError, 404).
그 세션의 말이 아니면 MessageNotFoundError(404). 세션 하나에 BOOKMARKS_PER_CONVERSATION 개까지다.

모델을 부르지 않아 청구하지 않는다. 답을 쓰는 중에도 된다. 어느 가지의 말이든 달 수 있다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.bookmarks import repository
from app.bookmarks.models import BOOKMARKS_PER_CONVERSATION, Bookmark
from app.bookmarks.schemas import EXCERPT_CHARS, BookmarkOut
from app.conversations.models import Conversation, Message
from app.conversations.service import MessageNotFoundError, get_conversation
from app.core.dependencies import Viewer


class BookmarksFullError(Exception):
    """세션의 책갈피가 가득 찼다(409). 떼고 단다."""


def text_of(message: Message) -> str:
    """말의 읽는 글. 모델의 답은 말 조각의 글을 잇는다(표식 @이름: 은 뺀다). 아니면 본문이다."""
    if message.segments:
        return ' '.join(str(segment.get('text', '')) for segment in message.segments)
    return message.content


def excerpt_of(content: str) -> str:
    """목록에 보일 말의 앞부분. 줄바꿈은 띄어쓰기로 바꾼다. 길면 자르고 … 를 붙인다."""
    flat = ' '.join(content.split())
    return flat if len(flat) <= EXCERPT_CHARS else flat[: EXCERPT_CHARS - 1] + '…'


def to_out(bookmark: Bookmark, message: Message) -> BookmarkOut:
    """책갈피와 그 말을 응답의 모양으로."""
    return BookmarkOut(
        message_id=bookmark.message_id,
        note=bookmark.note,
        role=message.role,
        excerpt=excerpt_of(text_of(message)),
        created_at=bookmark.created_at,
    )


async def message_of(session: AsyncSession, conversation: Conversation, message_id: uuid.UUID) -> Message:
    """그 세션의 말. 다른 세션의 말이거나 없으면 MessageNotFoundError."""
    message = await session.get(Message, message_id)
    if message is None or message.conversation_id != conversation.id:
        raise MessageNotFoundError
    return message


async def list_bookmarks(session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID) -> list[BookmarkOut]:
    """세션의 책갈피들. 나중에 단 것부터."""
    conversation, _ = await get_conversation(session, viewer, conversation_id)
    return [
        to_out(bookmark, message) for bookmark, message in await repository.list_with_messages(session, conversation.id)
    ]


async def put_bookmark(
    session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID, message_id: uuid.UUID, note: str | None
) -> BookmarkOut:
    """
    그 말에 책갈피를 단다. 이미 있으면 메모만 바꾼다(수의 상한에 다시 세지 않는다).
    새로 달 때 가득 찼으면 BookmarksFullError. 세션을 잠그고 센다. 빈 메모는 메모가 없는 것이다.
    """
    conversation, _ = await get_conversation(session, viewer, conversation_id)
    message = await message_of(session, conversation, message_id)
    await repository.lock_conversation(session, conversation.id)
    is_new = await repository.find(session, message.id) is None
    if is_new and await repository.count(session, conversation.id) >= BOOKMARKS_PER_CONVERSATION:
        raise BookmarksFullError
    await repository.put(session, conversation.id, message.id, note or None)
    await session.commit()
    bookmark = await repository.find(session, message.id)
    return to_out(bookmark, message)


async def remove_bookmark(
    session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID, message_id: uuid.UUID
) -> None:
    """그 말의 책갈피를 뗀다. 달지 않았어도 그대로 끝난다(여러 번 불러도 같다)."""
    conversation, _ = await get_conversation(session, viewer, conversation_id)
    message = await message_of(session, conversation, message_id)
    await repository.remove(session, message.id)
    await session.commit()
