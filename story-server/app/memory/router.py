# story-server/app/memory/router.py

"""
기억 메모 API. 화면 명세 D2 의 창(chat 의 C5 와 같다).

    GET    /api/v1/story/conversations/{id}/notes            메모들(먼저 쓴 것부터)
    POST   /api/v1/story/conversations/{id}/notes            {text}  더하기. 201
    PATCH  /api/v1/story/conversations/{id}/notes/{note_id}  {text}  고치기
    DELETE /api/v1/story/conversations/{id}/notes/{note_id}          지우기. 204

남의 세션은 404(app/conversations/router.py 가 답한다), 그 세션에 없는 메모는 404 note_not_found,
가득 차면 409 notes_full. 모델을 부르지 않아 청구하지 않는다. 답을 쓰는 중에도 된다(다음 말부터 들어간다).
"""

import uuid

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.dependencies import CurrentViewer, Session
from app.limits.routing import WRITE_LIMIT
from app.memory import service
from app.memory.models import MemoryNote
from app.memory.schemas import NoteOut, NoteWrite
from app.memory.service import NoteNotFoundError, NotesFullError

router = APIRouter(prefix='/conversations', tags=['memory'])


def to_note(note: MemoryNote) -> NoteOut:
    """메모를 응답의 모양으로."""
    return NoteOut(id=note.id, text=note.text, created_at=note.created_at, updated_at=note.updated_at)


@router.get('/{conversation_id}/notes', response_model=list[NoteOut], status_code=status.HTTP_200_OK)
async def list_notes(conversation_id: uuid.UUID, viewer: CurrentViewer, session: Session) -> list[NoteOut]:
    """세션의 기억 메모들."""
    return [to_note(note) for note in await service.list_notes(session, viewer, conversation_id)]


@router.post(
    '/{conversation_id}/notes', response_model=NoteOut, status_code=status.HTTP_201_CREATED, dependencies=[WRITE_LIMIT]
)
async def add_note(conversation_id: uuid.UUID, data: NoteWrite, viewer: CurrentViewer, session: Session) -> NoteOut:
    """기억 메모를 더한다. 다음 말부터 모델에 간다."""
    return to_note(await service.add_note(session, viewer, conversation_id, data.text))


@router.patch(
    '/{conversation_id}/notes/{note_id}',
    response_model=NoteOut,
    status_code=status.HTTP_200_OK,
    dependencies=[WRITE_LIMIT],
)
async def edit_note(
    conversation_id: uuid.UUID, note_id: uuid.UUID, data: NoteWrite, viewer: CurrentViewer, session: Session
) -> NoteOut:
    """기억 메모를 고친다."""
    return to_note(await service.edit_note(session, viewer, conversation_id, note_id, data.text))


@router.delete('/{conversation_id}/notes/{note_id}', status_code=status.HTTP_204_NO_CONTENT, dependencies=[WRITE_LIMIT])
async def delete_note(conversation_id: uuid.UUID, note_id: uuid.UUID, viewer: CurrentViewer, session: Session) -> None:
    """기억 메모를 지운다."""
    await service.delete_note(session, viewer, conversation_id, note_id)


# --- 예외를 응답으로. 앱에 한 번 등록한다(app/main.py) ---


async def handle_note_not_found(request: Request, error: NoteNotFoundError) -> JSONResponse:
    """그런 메모가 없으면 404 다."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={'detail': '메모를 찾을 수 없습니다.', 'code': 'note_not_found'}
    )


async def handle_notes_full(request: Request, error: NotesFullError) -> JSONResponse:
    """메모가 가득 찼으면 409 다. 지우고 더한다."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': '기억 메모가 가득 찼습니다. 지우고 더해 주세요.', 'code': 'notes_full'},
    )
