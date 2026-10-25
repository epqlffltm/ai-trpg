# board-server/app/comments/repository.py

"""
댓글과 답글을 DB 에서 읽고 쓴다. 커밋하지 않는다. 언제 커밋할지는 서비스가 안다.

  - 지운 댓글(deleted_at)은 읽는 쿼리가 모두 뺀다. 행은 남는다(신고와 답글이 그 댓글을 가리킨다).
    다만 목록은 지운 댓글도 살아 있는 답글이 달려 있으면 읽는다. 그 자리를 "지운 댓글"로 보여 준다
  - 목록은 쿼리 둘로 읽는다. 글에 단 댓글을 한 토막 읽고, 그 댓글들의 답글을 한 번에 읽는다.
    댓글마다 답글을 따로 읽으면 댓글 스무 개에 쿼리가 스물한 번 나간다
  - 고치는 쿼리는 세션에 읽어 둔 객체를 건드리지 않는다(synchronize_session=False). 응답은 서비스가 아는 값으로 만든다
  - 글 번호를 함께 적는 조건이 많다. 색인(post_id, parent_id, id)이 글 번호로 시작한다
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import and_, exists, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from app.comments.models import Comment


def alive() -> ColumnElement[bool]:
    """지우지 않은 댓글."""
    return Comment.deleted_at.is_(None)


def has_live_reply() -> ColumnElement[bool]:
    """살아 있는 답글이 달려 있는 댓글이라는 조건."""
    reply = aliased(Comment, name='reply')
    return exists().where(
        reply.post_id == Comment.post_id,
        reply.parent_id == Comment.id,
        reply.deleted_at.is_(None),
    )


async def find_comment(session: AsyncSession, comment_id: int) -> Comment | None:
    """댓글 하나. 없거나 지운 댓글이면 None 이다."""
    return (await session.scalars(select(Comment).where(Comment.id == comment_id, alive()))).one_or_none()


async def find_in_post(session: AsyncSession, post_id: int, comment_id: int) -> Comment | None:
    """그 글의 댓글 하나. 없거나, 지웠거나, 다른 글의 댓글이면 None 이다."""
    query = select(Comment).where(Comment.id == comment_id, Comment.post_id == post_id, alive())
    return (await session.scalars(query)).one_or_none()


async def count_replies(session: AsyncSession, post_id: int, parent_id: int) -> int:
    """한 댓글에 달린 살아 있는 답글의 수."""
    query = select(func.count()).where(Comment.post_id == post_id, Comment.parent_id == parent_id, alive())
    return (await session.execute(query)).scalar_one()


async def insert_comment(
    session: AsyncSession, post_id: int, parent_id: int | None, author_id: uuid.UUID, content: str
) -> Comment:
    """댓글을 넣고 넣은 행을 돌려준다. 번호와 시각은 DB 가 정한다."""
    query = (
        insert(Comment)
        .values(post_id=post_id, parent_id=parent_id, author_id=author_id, content=content)
        .returning(Comment)
    )
    return (await session.scalars(query)).one()


async def update_content(session: AsyncSession, comment_id: int, content: str) -> datetime:
    """내용을 고치고 고친 시각을 지금으로 적는다. 적힌 고친 시각을 돌려준다."""
    query = (
        update(Comment)
        .where(Comment.id == comment_id)
        .values(content=content, updated_at=func.now())
        .returning(Comment.updated_at)
        .execution_options(synchronize_session=False)
    )
    return (await session.execute(query)).scalar_one()


async def soft_delete(session: AsyncSession, comment_id: int) -> None:
    """지운 시각을 적는다. 행은 남는다. 고친 시각도 지금으로 적는다(NestJS 로 쓰던 때의 softDelete 와 같다)."""
    query = update(Comment).where(Comment.id == comment_id).values(deleted_at=func.now(), updated_at=func.now())
    await session.execute(query.execution_options(synchronize_session=False))


async def list_top_level(session: AsyncSession, post_id: int, after: int | None, limit: int) -> Sequence[Comment]:
    """
    글에 단 댓글을 번호 순으로 limit 개까지. after 가 있으면 그 번호보다 큰 것만이다.
    지운 댓글은 살아 있는 답글이 달려 있을 때만 읽는다.
    """
    conditions = [
        Comment.post_id == post_id,
        Comment.parent_id.is_(None),
        or_(alive(), has_live_reply()),
    ]
    if after is not None:
        conditions.append(Comment.id > after)
    query = select(Comment).where(and_(*conditions)).order_by(Comment.id).limit(limit)
    return (await session.scalars(query)).all()


async def list_replies(session: AsyncSession, post_id: int, parent_ids: Sequence[int]) -> Sequence[Comment]:
    """댓글들에 달린 살아 있는 답글을 한 번에. 댓글별로, 번호 순이다. 댓글이 없으면 DB 에 묻지 않는다."""
    if not parent_ids:
        return []
    query = (
        select(Comment)
        .where(Comment.post_id == post_id, Comment.parent_id.in_(parent_ids), alive())
        .order_by(Comment.parent_id, Comment.id)
    )
    return (await session.scalars(query)).all()
