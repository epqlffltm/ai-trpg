# board-server/app/boards/schemas.py

"""게시판의 응답. 화면의 타입이 이 이름(BoardResponse)을 쓴다(web/apps/web/src/api/types.ts)."""

from typing import Literal

from pydantic import BaseModel

from app.boards.models import Board


class BoardResponse(BaseModel):
    """게시판 하나."""

    slug: str
    name: str
    description: str
    write_policy: Literal['member', 'operator']


def to_board_response(board: Board) -> BoardResponse:
    return BoardResponse(
        slug=board.slug,
        name=board.name,
        description=board.description,
        write_policy=board.write_policy,  # type: ignore[arg-type]
    )
