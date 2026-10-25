# board-server/app/withdrawal/repository.py

"""
탈퇴한 사람의 것을 정리하는 쿼리. 저장(commit)은 부른 쪽(service.py)이 한 번에 한다.

  - 글쓴이와 신고한 사람만 비운다. 고친 시각(updated_at)은 그대로다. 글쓴이를 비운 것은 글을 고친 것이 아니다
  - 지운 글과 댓글(deleted_at)도 비운다
  - 바꾸거나 지운 줄의 수를 돌려준다. 로그에 남긴다
"""

import uuid

from sqlalchemy import CursorResult, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.authors.models import Author
from app.comments.models import Comment
from app.posts.models import Post
from app.reports.models import Report


def changed_rows(result: object) -> int:
    """문장 하나가 바꾸거나 지운 줄의 수."""
    assert isinstance(result, CursorResult)
    return result.rowcount


async def blank_post_authors(session: AsyncSession, user_id: uuid.UUID) -> int:
    """그 사람의 글(지운 글 포함)의 글쓴이를 비운다."""
    query = update(Post).where(Post.author_id == user_id).values(author_id=None)
    return changed_rows(await session.execute(query, execution_options={'synchronize_session': False}))


async def blank_comment_authors(session: AsyncSession, user_id: uuid.UUID) -> int:
    """그 사람의 댓글(지운 댓글 포함)의 글쓴이를 비운다."""
    query = update(Comment).where(Comment.author_id == user_id).values(author_id=None)
    return changed_rows(await session.execute(query, execution_options={'synchronize_session': False}))


async def blank_reporter(session: AsyncSession, user_id: uuid.UUID) -> int:
    """그 사람이 한 신고의 신고한 사람을 비운다. 처리한 운영자(handled_by)는 남긴다."""
    query = update(Report).where(Report.reporter_id == user_id).values(reporter_id=None)
    return changed_rows(await session.execute(query, execution_options={'synchronize_session': False}))


async def delete_author(session: AsyncSession, user_id: uuid.UUID) -> int:
    """적어 둔 그 사람의 닉네임을 지운다(0 이나 1)."""
    query = delete(Author).where(Author.user_id == user_id)
    return changed_rows(await session.execute(query, execution_options={'synchronize_session': False}))
