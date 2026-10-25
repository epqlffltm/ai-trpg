# board-server/app/notifications/outbox.py

"""
무엇을 누구에게 알리는가(#385). 발송함에 적기만 하고 저장(commit)은 부른 쪽이 댓글과 함께 한다.

| 종류 | 언제, 누구에게 | 내용 |
| --- | --- | --- |
| post.commented | 남의 글에 댓글이 달렸다. 글쓴이에게 | board_slug, post_id, post_title, comment_id |
| comment.replied | 남의 댓글에 답글이 달렸다. 댓글의 글쓴이에게 | 위와 같고 parent_id 가 더 있다 |

  - 자기 글과 자기 댓글에는 알리지 않는다. 글쓴이가 탈퇴해 비었으면 알리지 않는다
  - 열쇠(source_key)는 "<kind>:<댓글 번호>" 다. 알림 서버가 같은 알림을 알아본다

보내는 일(5초마다, 실패하면 간격을 늘려 다시)은 공용 코드가 한다(server_core/notifications/dispatcher.py).
"""

import uuid
from dataclasses import dataclass

from server_core.notifications import repository
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import OutgoingNotification

# 알림 서버에 넣는 이 서버의 이름. 알림 서버의 주소와 비밀(BOARD_SERVER_SECRET)이 이 이름으로 정해진다
SOURCE = 'board'

POST_COMMENTED = 'post.commented'
COMMENT_REPLIED = 'comment.replied'


@dataclass(frozen=True)
class CommentContext:
    """알림을 정하는 데 필요한 것. 댓글이 달린 글, 답글이면 그 댓글, 새 댓글."""

    board_slug: str
    post_id: int
    post_title: str
    post_author_id: uuid.UUID | None
    comment_id: int
    comment_author_id: uuid.UUID | None
    parent_id: int | None = None
    parent_author_id: uuid.UUID | None = None


def recipient_of(context: CommentContext) -> tuple[uuid.UUID, str] | None:
    """알릴 사람과 종류. 알릴 사람이 없으면 None 이다."""
    if context.parent_id is None:
        target, kind = context.post_author_id, POST_COMMENTED
    else:
        target, kind = context.parent_author_id, COMMENT_REPLIED
    if target is None or target == context.comment_author_id:
        return None
    return target, kind


def payload_of(context: CommentContext) -> dict:
    """알림의 내용. 번호는 글자로 싣는다."""
    payload = {
        'board_slug': context.board_slug,
        'post_id': str(context.post_id),
        'post_title': context.post_title,
        'comment_id': str(context.comment_id),
    }
    if context.parent_id is not None:
        payload['parent_id'] = str(context.parent_id)
    return payload


def queue_for_comment(session: AsyncSession, context: CommentContext) -> OutgoingNotification | None:
    """새 댓글의 알림을 발송함에 적는다. 저장하지 않는다. 알릴 사람이 없으면 아무것도 하지 않는다."""
    recipient = recipient_of(context)
    if recipient is None:
        return None
    user_id, kind = recipient
    source_key = f'{kind}:{context.comment_id}'
    return repository.put(session, OutgoingNotification, user_id, kind, source_key, payload_of(context))


async def drop_for_user(session: AsyncSession, user_id: uuid.UUID) -> int:
    """
    그 사람에게 아직 보내지 않은 알림을 지운다(탈퇴). 지운 수를 돌려준다(탈퇴의 로그). 저장하지 않는다.

    공용 코드의 drop_for_user 는 지운 수를 돌려주지 않아서 여기서 직접 지운다.
    """
    result = await session.execute(delete(OutgoingNotification).where(OutgoingNotification.user_id == user_id))
    return result.rowcount  # type: ignore[attr-defined]
