# board-server/app/boards/router.py

"""
게시판 목록.

    GET /api/v1/board/boards   로그인 없이. 정해 둔 차례대로
"""

from fastapi import APIRouter, status

from app.boards import service
from app.boards.schemas import BoardResponse, to_board_response
from app.core.dependencies import Session

router = APIRouter(prefix='/boards', tags=['boards'])


@router.get('', response_model=list[BoardResponse], status_code=status.HTTP_200_OK)
async def list_boards(session: Session) -> list[BoardResponse]:
    """게시판들을 정해 둔 차례대로 돌려준다."""
    return [to_board_response(board) for board in await service.list_boards(session)]
