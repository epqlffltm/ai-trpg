# game-server/app/realtime/router.py

"""
스트림 API. 테이블의 새 이벤트와 새 채팅을 SSE 로 흘려보낸다.

주소는 테이블 아래에 둔다(/tables/{table_id}/stream).
다른 API 와 달리 응답이 끝나지 않는다. 받는 쪽이 끊거나 서버가 닫을 때까지 열려 있다.

인증은 다른 API 와 같다(Authorization 머리말). 브라우저의 EventSource 는 머리말을 붙이지 못하므로,
화면은 fetch 로 이 주소를 읽는다.
"""

import re
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.auth.dependencies import CurrentUser
from app.realtime import service, sse
from app.realtime.service import Cursor
from app.realtime.sse import Comment, Frame
from app.tables import service as tables

router = APIRouter(prefix='/tables/{table_id}/stream', tags=['realtime'])

# Last-Event-ID 의 모양. "이벤트 번호-채팅 번호"다(service.Cursor.mark)
MARK_PATTERN = re.compile(r'(\d{1,10})-(\d{1,10})')

# 스트림 응답의 머리말.
# no-cache: 중간에서 이 응답을 저장해 두었다가 다른 사람에게 주지 않게 한다.
# X-Accel-Buffering: nginx 가 응답을 모았다가 한꺼번에 보내지 않게 한다. 모으면 실시간이 아니다
STREAM_HEADERS = {'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}


def read_cursor(last_event_id: str | None, events_after: int, messages_after: int) -> Cursor:
    """
    어디까지 받았는지를 요청에서 읽는다. 모양이 틀리면 422.

    Last-Event-ID 머리말이 있으면 그것을 쓴다. 끊겼다 다시 붙는 쪽이 보내는 값이다.
    없으면 주소의 events_after, messages_after 를 쓴다. 처음 붙는 쪽이 REST 로 읽은 마지막 번호를 적는다.
    """
    if last_event_id is None:
        return Cursor(events=events_after, messages=messages_after)

    matched = MARK_PATTERN.fullmatch(last_event_id)
    if matched is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail='Last-Event-ID 의 모양이 틀렸습니다.'
        )
    return Cursor(events=int(matched[1]), messages=int(matched[2]))


async def encode_all(items: AsyncIterator[Frame | Comment]) -> AsyncIterator[str]:
    """서비스가 내놓는 메시지를 하나씩 SSE 의 글자로 바꾼다."""
    async for item in items:
        yield sse.encode(item)


@router.get('', status_code=status.HTTP_200_OK, response_class=StreamingResponse)
async def open_stream(
    table_id: uuid.UUID,
    user: CurrentUser,
    request: Request,
    last_event_id: Annotated[str | None, Header()] = None,
    events_after: Annotated[int, Query(ge=0)] = 0,
    messages_after: Annotated[int, Query(ge=0)] = 0,
) -> StreamingResponse:
    """
    테이블의 스트림을 연다. 새 이벤트(table_event)와 새 채팅(chat_message)이 생기는 대로 온다.

    처음에는 REST 로 지금까지의 것을 읽고, 그 마지막 번호를 events_after, messages_after 에 적어 붙는다.
    끊겼다 다시 붙을 때는 마지막으로 받은 메시지의 id 를 Last-Event-ID 머리말로 보낸다.

    서버가 닫을 때는 이유를 담은 closed 메시지를 보내고 끝낸다(not_seated, table_ended, token_expired).
    """
    cursor = read_cursor(last_event_id, events_after, messages_after)
    state = request.app.state

    # 응답을 시작하기 전에 앉은 사람인지 본다. 시작한 뒤에는 404 를 줄 수 없다.
    # 요청의 세션(Session)을 쓰지 않는다. 그 세션은 응답이 끝날 때까지 열려 있어서, 스트림 내내 연결을 붙잡는다
    async with state.session_factory() as session:
        await tables.get_table(session, user.user_id, table_id)

    frames = service.stream(state.session_factory, state.hub, state.signal_source, user, table_id, cursor)
    return StreamingResponse(encode_all(frames), media_type='text/event-stream', headers=STREAM_HEADERS)
