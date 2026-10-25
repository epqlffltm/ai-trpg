# board-server/app/posts/service.py

"""
글을 읽고, 쓰고, 고치고, 지우고, 고정한다.

권한의 규칙은 여기에 없다(app/posts/policy.py). 여기서는 필요한 것을 DB 에서 읽어 그 규칙에 묻고,
안 되면 거절하고, 되면 저장한다. 글을 돌려줄 때는 댓글 수와 글쓴이의 닉네임을 따로 읽어 함께 싣는다.

거절하는 차례
  - 글: "없는 글인가(404)" 다음에 "해도 되는가(403)"다. 글은 누구나 읽을 수 있어서, 있는 글인지를 숨길 까닭이 없다
  - 쓰기: 운영자만 쓰는 게시판인가(403) 다음에 너무 자주 쓰는가(429)다
  - 고치기: 고칠 칸이 없으면(400) 글을 읽기도 전에 거절한다
  - 고정: 없는 글(404), 운영자가 아니다(403), 자리가 없다(409)

목록의 첫 쪽에는 고정한 글(pinned)을 따로 싣는다. 고정한 글은 items 와 total 에 들지 않는다.
고정하고 풀어도 다른 글의 쪽이 밀리지 않는다.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.authors.service import nicknames_of
from app.boards import service as boards
from app.boards.models import Board
from app.core.auth import Actor
from app.core.errors import ApiError
from app.core.write_limits import POST_LIMIT, ensure_within
from app.posts import policy, repository
from app.posts.models import Post
from app.posts.schemas import (
    CreatePostDto,
    PostContext,
    PostListResponse,
    PostResponse,
    PostSummary,
    PostSummaryResponse,
    UpdatePostDto,
    to_post_response,
    to_post_summary_response,
)

# 고칠 수 있는 칸
EDITABLE_FIELDS = ('title', 'content')


def post_not_found() -> ApiError:
    """그런 글이 없다. 지운 글도 없는 글이다."""
    return ApiError(status.HTTP_404_NOT_FOUND, '글을 찾을 수 없습니다.')


def operator_only_board() -> ApiError:
    return ApiError(status.HTTP_403_FORBIDDEN, '이 게시판에는 운영자만 글을 쓸 수 있습니다.')


def not_your_post_to_edit() -> ApiError:
    return ApiError(status.HTTP_403_FORBIDDEN, '자신의 글만 고칠 수 있습니다.')


def operator_only_edit() -> ApiError:
    """운영자만 쓰는 게시판의 제 글을, 운영자에서 내려온 뒤에 고치려 했다."""
    return ApiError(status.HTTP_403_FORBIDDEN, '이 게시판의 글은 지금 운영자인 글쓴이만 고칠 수 있습니다.')


def not_your_post_to_delete() -> ApiError:
    return ApiError(status.HTTP_403_FORBIDDEN, '자신의 글만 지울 수 있습니다.')


def nothing_to_update() -> ApiError:
    return ApiError(status.HTTP_400_BAD_REQUEST, '고칠 내용을 적어야 합니다.')


def operator_only_delete() -> ApiError:
    return ApiError(status.HTTP_403_FORBIDDEN, '이 게시판의 글은 운영자만 지울 수 있습니다.')


def operator_only_pin() -> ApiError:
    return ApiError(status.HTTP_403_FORBIDDEN, '운영자만 글을 고정할 수 있습니다.')


def pin_limit_reached() -> ApiError:
    """이 게시판에 고정한 글이 이미 다 찼다. 같은 요청을 다시 보내도 되지 않는다. 하나를 풀어야 한다."""
    return ApiError(status.HTTP_409_CONFLICT, '이 게시판에는 글을 더 고정할 수 없습니다.')


@dataclass(frozen=True)
class EditedPost:
    """고친 뒤의 글. 응답을 만드는 데 쓴다. 세션에 읽어 둔 행은 고치지 않는다."""

    id: int
    board_id: int
    author_id: uuid.UUID | None
    title: str
    content: str
    pinned_until: datetime | None
    created_at: datetime
    updated_at: datetime


async def board_by_slug(session: AsyncSession, slug: str) -> Board:
    """주소의 이름으로 게시판. 이름의 모양이 아니면 DB 에 묻지 않고 404 다."""
    return await boards.get_by_slug(session, slug)


async def get_post(session: AsyncSession, post_id: int) -> tuple[Post, Board]:
    """글 하나와 그 게시판. 없거나 지운 글이면 404 다."""
    found = await repository.find_with_board(session, post_id)
    if found is None:
        raise post_not_found()
    return found


async def nickname_of(session: AsyncSession, user_id: uuid.UUID | None) -> str | None:
    """한 사람의 닉네임. 모르는 사람이거나 탈퇴한 사람이면 None 이다."""
    return (await nicknames_of(session, [user_id])).get(user_id) if user_id is not None else None


async def full_response(session: AsyncSession, post: PostSummary, content: str, board_slug: str) -> PostResponse:
    """글 하나를 본문까지 응답의 모양으로. 댓글 수와 글쓴이의 이름을 따로 읽는다."""
    comment_count = await repository.count_comments(session, post.id)
    author_nickname = await nickname_of(session, post.author_id)
    context = PostContext(board_slug, comment_count, author_nickname, policy.current_time())
    return to_post_response(post, content, context)


async def summary_responses(
    session: AsyncSession, posts: Sequence[PostSummary], slugs: dict[int, str], now: datetime
) -> list[PostSummaryResponse]:
    """
    목록의 글들을 응답의 모양으로. 댓글 수와 닉네임은 글들을 모아 한 번에 읽는다.
    slugs 는 게시판의 번호로 이름을 찾는 표다.
    """
    counts = await repository.count_comments_of(session, [post.id for post in posts])
    nicknames = await nicknames_of(session, [post.author_id for post in posts])
    return [
        to_post_summary_response(
            post,
            PostContext(
                # 글이 있는 게시판은 지울 수 없다(posts 의 외래 키). 표에 없을 수 없다
                slugs.get(post.board_id, ''),
                counts.get(post.id, 0),
                None if post.author_id is None else nicknames.get(post.author_id),
                now,
            ),
        )
        for post in posts
    ]


async def list_posts(session: AsyncSession, slug: str, page: int, size: int) -> PostListResponse:
    """
    한 게시판의 글 한 쪽. 새 글부터다. 본문은 싣지 않는다. 첫 쪽에는 고정한 글을 따로 싣는다.
    지운 글은 목록에도 전체 개수에도 들지 않는다. 고정이 끝난 글은 제 번호의 자리로 돌아온다.
    """
    now = policy.current_time()
    board = await board_by_slug(session, slug)
    items = await repository.list_unpinned(session, board.id, now, policy.offset_of(page, size), size)
    total = await repository.count_unpinned(session, board.id, now)
    pinned = await repository.list_pinned(session, board.id, now) if page == policy.DEFAULT_PAGE else []
    shown = await summary_responses(session, [*pinned, *items], {board.id: board.slug}, now)
    return PostListResponse(pinned=shown[: len(pinned)], items=shown[len(pinned) :], page=page, size=size, total=total)


def ensure_can_write(board: Board, actor: Actor) -> None:
    """이 게시판에 써도 되는지 확인한다. 안 되면 403 이다."""
    if not policy.can_write(board, actor.is_operator):
        raise operator_only_board()


async def create_post(session: AsyncSession, slug: str, actor: Actor, data: CreatePostDto) -> PostResponse:
    """게시판에 글을 쓴다. 방금 쓴 글이라 댓글을 세지 않는다(0)."""
    board = await board_by_slug(session, slug)
    ensure_can_write(board, actor)
    await ensure_within(session, POST_LIMIT, actor)
    post = await repository.insert_post(session, board.id, actor.user_id, data.title, data.content)
    await session.commit()
    context = PostContext(board.slug, 0, await nickname_of(session, post.author_id), policy.current_time())
    return to_post_response(post, post.content, context)


async def read_post(session: AsyncSession, post_id: int) -> PostResponse:
    """글 하나를 본문까지."""
    post, board = await get_post(session, post_id)
    return await full_response(session, post, post.content, board.slug)


def ensure_can_edit(post: Post, board: Board, actor: Actor) -> None:
    """고쳐도 되는지 확인한다. 글쓴이인데 안 되면 운영자만 쓰는 게시판의 글이다."""
    if not policy.can_edit(post.author_id, board, actor.user_id, actor.is_operator):
        raise operator_only_edit() if policy.is_author(post.author_id, actor.user_id) else not_your_post_to_edit()


def text_changes(post: Post, data: UpdatePostDto) -> dict[str, str]:
    """실제로 바뀌는 칸들. null 을 보낸 칸과 같은 값은 빠진다. 바뀌는 것이 없으면 고친 시각도 그대로다."""
    changes: dict[str, str] = {}
    for name in EDITABLE_FIELDS:
        value = getattr(data, name)
        if value is not None and value != getattr(post, name):
            changes[name] = value
    return changes


def edited(post: Post, changes: dict[str, str], updated_at: datetime) -> EditedPost:
    return EditedPost(
        id=post.id,
        board_id=post.board_id,
        author_id=post.author_id,
        title=changes.get('title', post.title),
        content=changes.get('content', post.content),
        pinned_until=post.pinned_until,
        created_at=post.created_at,
        updated_at=updated_at,
    )


async def update_post(session: AsyncSession, post_id: int, actor: Actor, data: UpdatePostDto) -> PostResponse:
    """글을 고친다. 보낸 칸만 고친다. 고칠 칸이 없으면 400, 없는 글이면 404, 고칠 수 없는 사람이면 403 이다."""
    if not data.model_fields_set:
        raise nothing_to_update()
    post, board = await get_post(session, post_id)
    ensure_can_edit(post, board, actor)
    changes = text_changes(post, data)
    updated_at = post.updated_at
    if changes:
        updated_at = await repository.update_text(session, post.id, changes)
        await session.commit()
    result = edited(post, changes, updated_at)
    return await full_response(session, result, result.content, board.slug)


async def delete_post(session: AsyncSession, post_id: int, actor: Actor) -> None:
    """
    글을 지운다. 행은 남기고 지운 시각을 적는다. 없는 글이면 404, 지울 수 없는 사람이면 403 이다.
    고정한 글을 지우면 고정한 글의 목록에서도 빠진다.
    """
    post, board = await get_post(session, post_id)
    if not policy.can_delete(post.author_id, board, actor.user_id, actor.is_operator):
        raise operator_only_delete() if policy.is_operator_only(board) else not_your_post_to_delete()
    await repository.soft_delete(session, post.id)
    await session.commit()


def ensure_can_pin(actor: Actor) -> None:
    """고정해도 되는 사람인지 확인한다. 아니면 403 이다."""
    if not policy.can_pin(actor.is_operator):
        raise operator_only_pin()


async def pin_post(session: AsyncSession, post_id: int, actor: Actor, days: int) -> None:
    """
    글을 days 일 동안 고정한다. 이미 고정한 글이면 기간을 새로 잡는다. 맨 위로 올라온다.
    없는 글이면 404, 운영자가 아니면 403, 그 게시판에 고정한 글이 이미 다 찼으면 409 다.
    """
    now = policy.current_time()
    post, _ = await get_post(session, post_id)
    ensure_can_pin(actor)
    if not policy.has_room_to_pin(await repository.count_others_pinned(session, post.board_id, post.id, now)):
        raise pin_limit_reached()
    await repository.write_pin(session, post.id, now, policy.pin_ends_at(now, days))
    await session.commit()


async def unpin_post(session: AsyncSession, post_id: int, actor: Actor) -> None:
    """글의 고정을 푼다. 고정하지 않은 글이어도 오류가 아니다. 없는 글이면 404, 운영자가 아니면 403 이다."""
    post, _ = await get_post(session, post_id)
    ensure_can_pin(actor)
    await repository.write_pin(session, post.id, None, None)
    await session.commit()
