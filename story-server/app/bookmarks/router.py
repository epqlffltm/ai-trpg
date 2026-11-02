# story-server/app/bookmarks/router.py

"""
말의 책갈피 API(#982).

    GET    /api/v1/story/conversations/{id}/bookmarks               책갈피들(나중에 단 것부터)
    PUT    /api/v1/story/conversations/{id}/bookmarks/{message_id}  {note?}  달기. 이미 있으면 메모만 바꾼다
    DELETE /api/v1/story/conversations/{id}/bookmarks/{message_id}          떼기. 204(달지 않았어도)

남의 세션은 404(app/conversations/router.py 가 답한다), 그 세션의 말이 아니면 404 message_not_found,
가득 차면 409 bookmarks_full. 그 자리로 가는 것은 가지 고르기(PUT /conversations/{id}/branch)다.
"""

import uuid

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.bookmarks import service
from app.bookmarks.schemas import BookmarkOut, BookmarkWrite
from app.bookmarks.service import BookmarksFullError
from app.core.dependencies import CurrentViewer, Session
from app.limits.routing import WRITE_LIMIT

router = APIRouter(prefix='/conversations', tags=['bookmarks'])


@router.get('/{conversation_id}/bookmarks', response_model=list[BookmarkOut], status_code=status.HTTP_200_OK)
async def list_bookmarks(conversation_id: uuid.UUID, viewer: CurrentViewer, session: Session) -> list[BookmarkOut]:
    """세션의 책갈피들."""
    return await service.list_bookmarks(session, viewer, conversation_id)


@router.put(
    '/{conversation_id}/bookmarks/{message_id}',
    response_model=BookmarkOut,
    status_code=status.HTTP_200_OK,
    dependencies=[WRITE_LIMIT],
)
async def put_bookmark(
    conversation_id: uuid.UUID, message_id: uuid.UUID, data: BookmarkWrite, viewer: CurrentViewer, session: Session
) -> BookmarkOut:
    """그 말에 책갈피를 단다. 이미 있으면 메모만 바꾼다."""
    return await service.put_bookmark(session, viewer, conversation_id, message_id, data.note)


@router.delete(
    '/{conversation_id}/bookmarks/{message_id}', status_code=status.HTTP_204_NO_CONTENT, dependencies=[WRITE_LIMIT]
)
async def remove_bookmark(
    conversation_id: uuid.UUID, message_id: uuid.UUID, viewer: CurrentViewer, session: Session
) -> None:
    """그 말의 책갈피를 뗀다."""
    await service.remove_bookmark(session, viewer, conversation_id, message_id)


# --- 예외를 응답으로. 앱에 한 번 등록한다(app/main.py) ---


async def handle_bookmarks_full(request: Request, error: BookmarksFullError) -> JSONResponse:
    """책갈피가 가득 찼으면 409 다. 떼고 단다."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': '책갈피가 가득 찼습니다. 떼고 달아 주세요.', 'code': 'bookmarks_full'},
    )
