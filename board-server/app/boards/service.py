# board-server/app/boards/service.py

"""
게시판을 읽는다. 게시판은 마이그레이션이 넣은 것이고 API 로 바꾸지 않는다.
"""

import re
from collections.abc import Sequence

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.boards.models import Board, WritePolicy
from app.core.errors import ApiError

BOARD_NOT_FOUND = '게시판을 찾을 수 없습니다.'

# 게시판 이름의 모양. 소문자, 숫자, 붙임표로 30자까지
BOARD_SLUG = re.compile(r'\A[a-z0-9-]{1,30}\Z')


def board_not_found() -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, BOARD_NOT_FOUND)


def is_board_slug(value: str) -> bool:
    """게시판 이름의 모양인가. 아니면 그런 게시판이 없는 것이다."""
    return BOARD_SLUG.search(value) is not None


def ensure_board_slug(slug: str) -> None:
    """게시판 이름의 모양인지 확인한다. 아니면 그런 게시판이 없는 것이다(404). DB 에 NUL 같은 글자를 묻지 않는다."""
    if not is_board_slug(slug):
        raise board_not_found()


async def list_boards(session: AsyncSession) -> Sequence[Board]:
    """게시판들을 정해 둔 차례대로."""
    rows = await session.scalars(select(Board).order_by(Board.position, Board.id))
    return rows.all()


async def get_by_slug(session: AsyncSession, slug: str) -> Board:
    """주소의 이름으로 게시판 하나. 이름의 모양이 아니거나 없으면 404 를 던진다."""
    ensure_board_slug(slug)
    board = await session.scalar(select(Board).where(Board.slug == slug))
    if board is None:
        raise board_not_found()
    return board


def is_operator_only(board: Board) -> bool:
    """운영자만 글을 쓰는 게시판인가(공지사항, 이벤트)."""
    return board.write_policy == WritePolicy.OPERATOR
