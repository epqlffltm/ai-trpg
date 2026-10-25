# board-server/app/comments/service.py

"""
댓글과 답글을 읽고, 쓰고, 고치고, 지운다.

규칙은 여기에 없다(app/comments/policy.py). 여기서는 필요한 것을 DB 에서 읽어 그 규칙에 묻고,
안 되면 거절하고, 되면 저장한다. 댓글을 돌려줄 때는 글쓴이의 닉네임을 따로 읽어 함께 싣는다.

거절하는 차례
  - 쓰기: 없는 글(404), 답글을 달 수 없는 댓글(400 없는 댓글, 400 답글에 다는 답글, 409 답글이 다 참),
    너무 자주 쓴다(429)
  - 고치기, 지우기: 없는 댓글(404) 다음에 해도 되는가(403)다

새 댓글의 알림(글쓴이, 답글이면 그 댓글의 글쓴이에게)은 댓글과 같은 트랜잭션에 발송함에 적는다(#385).
"""

import uuid
from dataclasses import dataclass, replace
from datetime import datetime

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.authors.service import nicknames_of
from app.boards.models import Board
from app.comments import policy, repository
from app.comments.models import Comment
from app.comments.schemas import (
    CommentFields,
    CommentListResponse,
    CommentResponse,
    authors_of,
    threads_of,
    to_comment_response,
    to_thread_response,
)
from app.core.auth import Actor
from app.core.errors import ApiError
from app.core.ids import record_id
from app.core.write_limits import COMMENT_LIMIT, ensure_within
from app.notifications.outbox import CommentContext, queue_for_comment
from app.posts.models import Post
from app.posts.service import get_post


def comment_not_found() -> ApiError:
    """그런 댓글이 없다. 지운 댓글도 없는 댓글이다."""
    return ApiError(status.HTTP_404_NOT_FOUND, '댓글을 찾을 수 없습니다.')


def parent_not_found() -> ApiError:
    """답글을 달려는 댓글이 없다. 지웠거나, 다른 글의 댓글이다."""
    return ApiError(status.HTTP_400_BAD_REQUEST, '답글을 달 댓글을 찾을 수 없습니다.')


def cannot_reply_to_reply() -> ApiError:
    return ApiError(status.HTTP_400_BAD_REQUEST, '답글에는 답글을 달 수 없습니다.')


def too_many_replies() -> ApiError:
    """한 댓글에 달 수 있는 답글이 다 찼다."""
    return ApiError(status.HTTP_409_CONFLICT, '이 댓글에는 답글을 더 달 수 없습니다.')


def not_your_comment_to_edit() -> ApiError:
    return ApiError(status.HTTP_403_FORBIDDEN, '자신의 댓글만 고칠 수 있습니다.')


def not_your_comment_to_delete() -> ApiError:
    return ApiError(status.HTTP_403_FORBIDDEN, '자신의 댓글만 지울 수 있습니다.')


@dataclass(frozen=True)
class CommentView:
    """응답을 만드는 데 쓰는 댓글의 값. 세션에 읽어 둔 행은 고치지 않는다."""

    id: int
    post_id: int
    parent_id: int | None
    author_id: uuid.UUID | None
    content: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


def view_of(comment: Comment) -> CommentView:
    return CommentView(
        id=comment.id,
        post_id=comment.post_id,
        parent_id=comment.parent_id,
        author_id=comment.author_id,
        content=comment.content,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        deleted_at=comment.deleted_at,
    )


def context_of(post: Post, board: Board, parent: Comment | None, comment: Comment) -> CommentContext:
    """새 댓글이 달린 곳을 알림을 정하는 모양으로."""
    return CommentContext(
        board_slug=board.slug,
        post_id=post.id,
        post_title=post.title,
        post_author_id=post.author_id,
        comment_id=comment.id,
        comment_author_id=comment.author_id,
        parent_id=None if parent is None else parent.id,
        parent_author_id=None if parent is None else parent.author_id,
    )


async def comment_response(session: AsyncSession, comment: CommentFields) -> CommentResponse:
    """댓글 하나를 응답의 모양으로. 글쓴이의 이름을 따로 읽는다."""
    return to_comment_response(comment, await nicknames_of(session, [comment.author_id]))


async def get_comment(session: AsyncSession, comment_id: int) -> Comment:
    """댓글 하나. 없거나 지운 댓글이면 404 다."""
    comment = await repository.find_comment(session, comment_id)
    if comment is None:
        raise comment_not_found()
    return comment


async def list_comments(session: AsyncSession, post_id: int, after: int | None, size: int) -> CommentListResponse:
    """
    한 글의 댓글 한 토막. 먼저 쓴 것부터고, 댓글마다 답글이 모두 붙어 있다. 없는 글이면 404 다.
    지운 댓글은 뺀다. 다만 답글이 달린 댓글은 지웠어도 자리를 남긴다. 지운 답글은 뺀다.
    """
    await get_post(session, post_id)
    fetched = await repository.list_top_level(session, post_id, after, policy.fetch_count(size))
    piece = policy.slice_of(fetched, size, lambda comment: comment.id)
    replies = await repository.list_replies(session, post_id, [comment.id for comment in piece.items])
    threads = threads_of(piece.items, replies)
    nicknames = await nicknames_of(session, authors_of(threads))
    return CommentListResponse(
        items=[to_thread_response(thread, nicknames) for thread in threads], next=record_id(piece.next)
    )


async def ensure_can_reply_to(session: AsyncSession, post_id: int, parent_id: int) -> Comment:
    """
    이 댓글에 답글을 달아도 되는지 확인하고 그 댓글을 돌려준다.

    답글의 수는 세어 보고 넣는다. 그사이에 다른 요청이 답글을 달면 끝을 한둘 넘을 수 있다.
    이 끝은 응답이 한없이 커지는 것을 막으려는 것이라 그 정도는 넘어도 된다.
    정확히 지키려면 댓글의 행을 잠그고 세야 한다.
    """
    parent = await repository.find_in_post(session, post_id, parent_id)
    if parent is None:
        raise parent_not_found()
    if not policy.can_have_replies(parent.parent_id):
        raise cannot_reply_to_reply()
    if not policy.has_room_for_reply(await repository.count_replies(session, post_id, parent_id)):
        raise too_many_replies()
    return parent


async def create_comment(
    session: AsyncSession, post_id: int, actor: Actor, content: str, parent_id: int | None
) -> CommentResponse:
    """글에 댓글을 단다. parent_id 가 있으면 그 댓글에 답글을 단다. 댓글과 알림을 함께 저장한다."""
    post, board = await get_post(session, post_id)
    parent = None if parent_id is None else await ensure_can_reply_to(session, post_id, parent_id)
    await ensure_within(session, COMMENT_LIMIT, actor)
    comment = await repository.insert_comment(
        session, post.id, None if parent is None else parent.id, actor.user_id, content
    )
    queue_for_comment(session, context_of(post, board, parent, comment))
    written = view_of(comment)
    await session.commit()
    return await comment_response(session, written)


async def update_comment(session: AsyncSession, comment_id: int, actor: Actor, content: str) -> CommentResponse:
    """
    댓글의 내용을 고친다. 없는 댓글이면 404, 글쓴이가 아니면 403 이다.
    내용이 같으면 고치지 않는다. 고친 시각도 그대로다(NestJS 로 쓰던 때와 같다).
    """
    comment = await get_comment(session, comment_id)
    if not policy.can_edit(comment.author_id, actor.user_id):
        raise not_your_comment_to_edit()
    result = view_of(comment)
    if content != comment.content:
        updated_at = await repository.update_content(session, comment.id, content)
        await session.commit()
        result = replace(result, content=content, updated_at=updated_at)
    return await comment_response(session, result)


async def delete_comment(session: AsyncSession, comment_id: int, actor: Actor) -> None:
    """
    댓글을 지운다. 없는 댓글이면 404, 글쓴이도 운영자도 아니면 403 이다. 행은 남기고 지운 시각을 적는다.
    답글이 달린 댓글을 지워도 답글은 남는다. 목록에는 그 댓글의 자리가 "지운 댓글"로 나온다.
    """
    comment = await get_comment(session, comment_id)
    if not policy.can_delete(comment.author_id, actor.user_id, actor.is_operator):
        raise not_your_comment_to_delete()
    await repository.soft_delete(session, comment.id)
    await session.commit()
