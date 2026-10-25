# board-server/app/posts/repository.py

"""
글과 글에 달린 댓글의 수를 DB 에서 읽고 쓴다. 커밋하지 않는다. 언제 커밋할지는 서비스가 안다.

  - 지운 글(deleted_at)은 읽는 쿼리가 모두 뺀다. 행은 남는다(신고가 그 글을 가리킨다)
  - 목록과 검색은 본문을 읽지 않는다. 한 쪽에 본문 스무 개를 읽을 까닭이 없다
  - 고정하고 푸는 것은 글을 고치는 것이 아니다. 고친 시각(updated_at)을 건드리지 않는다
  - 고치는 쿼리는 세션에 읽어 둔 객체를 건드리지 않는다(synchronize_session=False). 응답은 서비스가 아는 값으로 만든다
  - 댓글 수는 글에 적어 두지 않고 물을 때마다 센다. 실제 행을 세므로 틀릴 수 없다.
    목록은 그 쪽의 글 번호를 모아 한 번에 센다. 지운 댓글은 세지 않는다(답글이 남은 지운 댓글도)
  - 검색은 ILIKE '%낱말%' 로 본다. 색인을 타지 않는다. 글이 수만 개일 때까지는 이것으로 충분하다.
    검색 하나가 DB 를 오래 붙잡지 못하게 시간 제한(statement_timeout)을 건다
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Row, and_, func, insert, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.boards.models import Board
from app.comments.models import Comment
from app.posts.models import Post
from app.posts.terms import contains_pattern

# 목록과 검색이 읽는 칸. 본문은 빠진다
SUMMARY_COLUMNS = (
    Post.id,
    Post.board_id,
    Post.author_id,
    Post.title,
    Post.pinned_until,
    Post.created_at,
    Post.updated_at,
)

# 한 쪽의 글
SummaryRows = Sequence[Row]


def alive() -> ColumnElement[bool]:
    """지우지 않은 글."""
    return Post.deleted_at.is_(None)


def not_pinned_in(board_id: int, now: datetime) -> ColumnElement[bool]:
    """한 게시판의, 지금 고정되어 있지 않은 글. 고정한 적이 없거나 고정이 끝난 글이다."""
    return and_(
        Post.board_id == board_id,
        or_(Post.pinned_until.is_(None), Post.pinned_until <= now),
        alive(),
    )


def pinned_in(board_id: int, now: datetime) -> ColumnElement[bool]:
    """한 게시판의, 지금 고정되어 있는 글."""
    return and_(Post.board_id == board_id, Post.pinned_until > now, alive())


async def find_with_board(session: AsyncSession, post_id: int) -> tuple[Post, Board] | None:
    """글 하나와 그 게시판. 없거나 지운 글이면 None 이다."""
    query = select(Post, Board).join(Board, Board.id == Post.board_id).where(Post.id == post_id, alive())
    row = (await session.execute(query)).first()
    return None if row is None else (row[0], row[1])


async def list_unpinned(session: AsyncSession, board_id: int, now: datetime, offset: int, limit: int) -> SummaryRows:
    """한 게시판의 고정하지 않은 글 한 쪽. 번호가 큰 것(새 글)부터다."""
    query = (
        select(*SUMMARY_COLUMNS)
        .where(not_pinned_in(board_id, now))
        .order_by(Post.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return (await session.execute(query)).all()


async def count_unpinned(session: AsyncSession, board_id: int, now: datetime) -> int:
    """한 게시판의 고정하지 않은 글의 수."""
    query = select(func.count()).select_from(Post).where(not_pinned_in(board_id, now))
    return await session.scalar(query) or 0


async def list_pinned(session: AsyncSession, board_id: int, now: datetime) -> SummaryRows:
    """한 게시판에 지금 고정되어 있는 글들. 나중에 고정한 것부터다."""
    query = select(*SUMMARY_COLUMNS).where(pinned_in(board_id, now)).order_by(Post.pinned_at.desc(), Post.id.desc())
    return (await session.execute(query)).all()


async def count_others_pinned(session: AsyncSession, board_id: int, post_id: int, now: datetime) -> int:
    """같은 게시판에서 이 글 말고 지금 고정되어 있는 글의 수."""
    query = select(func.count()).select_from(Post).where(pinned_in(board_id, now), Post.id != post_id)
    return await session.scalar(query) or 0


async def insert_post(session: AsyncSession, board_id: int, author_id: uuid.UUID, title: str, content: str) -> Post:
    """글을 넣고 넣은 행을 돌려준다. 번호와 시각은 DB 가 정한다."""
    query = (
        insert(Post)
        .values(board_id=board_id, author_id=author_id, title=title, content=content, pinned_at=None, pinned_until=None)
        .returning(Post)
    )
    return (await session.scalars(query)).one()


async def update_text(session: AsyncSession, post_id: int, changes: dict[str, str]) -> datetime:
    """제목이나 본문을 고치고 고친 시각을 지금으로 적는다. 적힌 고친 시각을 돌려준다."""
    query = (
        update(Post)
        .where(Post.id == post_id)
        .values(**changes, updated_at=func.now())
        .returning(Post.updated_at)
        .execution_options(synchronize_session=False)
    )
    return (await session.execute(query)).scalar_one()


async def soft_delete(session: AsyncSession, post_id: int) -> None:
    """지운 시각을 적는다. 행은 남는다."""
    query = update(Post).where(Post.id == post_id).values(deleted_at=func.now(), updated_at=func.now())
    await session.execute(query.execution_options(synchronize_session=False))


async def write_pin(
    session: AsyncSession, post_id: int, pinned_at: datetime | None, pinned_until: datetime | None
) -> None:
    """고정한 시각과 끝나는 시각을 적는다. 둘 다 None 이면 고정을 푼다. 고친 시각은 그대로 둔다."""
    query = update(Post).where(Post.id == post_id).values(pinned_at=pinned_at, pinned_until=pinned_until)
    await session.execute(query.execution_options(synchronize_session=False))


async def count_comments(session: AsyncSession, post_id: int) -> int:
    """글 하나의 살아 있는 댓글과 답글의 수."""
    query = select(func.count()).select_from(Comment).where(Comment.post_id == post_id, Comment.deleted_at.is_(None))
    return await session.scalar(query) or 0


async def count_comments_of(session: AsyncSession, post_ids: Sequence[int]) -> dict[int, int]:
    """여러 글의 댓글 수를 한 번에 센다. 댓글이 없는 글은 빠진다. 글이 없으면 DB 에 묻지 않는다."""
    if not post_ids:
        return {}
    query = (
        select(Comment.post_id, func.count())
        .where(Comment.post_id.in_(set(post_ids)), Comment.deleted_at.is_(None))
        .group_by(Comment.post_id)
    )
    return {post_id: count for post_id, count in (await session.execute(query)).all()}


def matching(terms: Sequence[str], board_id: int | None) -> ColumnElement[bool]:
    """
    낱말이 모두 제목이나 본문에 들어 있는 글. board_id 가 있으면 그 게시판에서만이다.

    낱말은 값으로 넘긴다. SQL 의 글에 이어 붙이지 않는다. ESCAPE '\\' 는 낱말 안의 \\% 와 \\_ 를 글자로 읽게 한다.
    """
    conditions = [alive()]
    if board_id is not None:
        conditions.append(Post.board_id == board_id)
    for term in terms:
        pattern = contains_pattern(term)
        conditions.append(or_(Post.title.ilike(pattern, escape='\\'), Post.content.ilike(pattern, escape='\\')))
    return and_(*conditions)


async def limit_statement_time(session: AsyncSession, timeout_ms: int) -> None:
    """
    지금 트랜잭션의 쿼리에 시간 제한을 건다. 넘으면 DB 가 쿼리를 멈춘다.

    SET LOCAL 이라 트랜잭션이 끝나면 풀린다. 그냥 SET 으로 걸면 연결에 남아서, 풀에 돌아간 그 연결을 받은
    다른 요청에도 걸린다. SET 은 값을 따로 넘기지 못한다. 정수인 것을 확인하고 적는다.
    """
    await session.execute(text(f'SET LOCAL statement_timeout = {int(timeout_ms)}'))


async def search(
    session: AsyncSession, terms: Sequence[str], board_id: int | None, offset: int, limit: int
) -> tuple[SummaryRows, int]:
    """낱말이 모두 들어 있는 글 한 쪽과 전체 개수. 번호가 큰 것(새 글)부터다."""
    condition = matching(terms, board_id)
    rows = (
        await session.execute(
            select(*SUMMARY_COLUMNS).where(condition).order_by(Post.id.desc()).offset(offset).limit(limit)
        )
    ).all()
    total = await session.scalar(select(func.count()).select_from(Post).where(condition)) or 0
    return rows, total
