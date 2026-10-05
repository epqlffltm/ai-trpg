# game-server/app/chat/router.py

"""
채팅 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

주소는 테이블 아래에 둔다(/tables/{table_id}/messages). 채팅은 테이블에 딸린 것이다.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.assets.routing import MAX_PAGE_SIZE, Session
from app.auth.dependencies import CurrentUser
from app.chat import service
from app.chat.models import ChatMessage
from app.chat.schemas import MessageCreate, MessageOut, MessagePage
from app.chat.typing import TypingThrottle

router = APIRouter(prefix='/tables/{table_id}/messages', tags=['chat'])

# 한 번에 읽는 채팅의 개수
DEFAULT_MESSAGE_LIMIT = 50


def get_typing_throttle(request: Request) -> TypingThrottle:
    """앱에 하나 둔 것을 꺼낸다(app/main.py). 모든 요청이 같은 기록을 본다."""
    return request.app.state.typing_throttle


# "입력 중"을 받는 API 가 인자의 형식으로 쓴다
Throttling = Annotated[TypingThrottle, Depends(get_typing_throttle)]


def to_message(message: ChatMessage) -> MessageOut:
    """채팅 한 줄을 응답으로 바꾼다. 칸을 하나씩 적어 옮긴다."""
    return MessageOut(
        sequence=message.sequence,
        user_id=message.user_id,
        character_name=message.character_name,
        content=message.content,
        created_at=message.created_at,
    )


@router.post('', response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def post_message(table_id: uuid.UUID, data: MessageCreate, user: CurrentUser, session: Session) -> MessageOut:
    """채팅을 쓴다. 모집 중과 진행 중에 쓸 수 있다. 끝난 테이블에는 쓸 수 없다."""
    message = await service.post_message(session, user.user_id, table_id, data)
    return to_message(message)


@router.post('/typing', status_code=status.HTTP_204_NO_CONTENT)
async def announce_typing(table_id: uuid.UUID, user: CurrentUser, session: Session, throttle: Throttling) -> None:
    """
    "입력 중"이라고 알린다. 저장하지 않는다. 다른 사람들의 스트림에 typing 메시지가 간다.

    화면은 사용자가 글자를 치는 동안 3초쯤에 한 번 부른다. 멈췄다는 것은 알리지 않는다.
    받는 쪽이 5초쯤 뒤에 스스로 지운다.
    """
    await service.announce_typing(session, user.user_id, table_id, throttle)


@router.get('', response_model=MessagePage, status_code=status.HTTP_200_OK)
async def list_messages(
    table_id: uuid.UUID,
    user: CurrentUser,
    session: Session,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_MESSAGE_LIMIT,
) -> MessagePage:
    """
    테이블의 채팅을 쓴 순서대로 돌려준다. after 를 주면 그 번호 뒤의 것만 온다.

    처음에는 after 없이 읽고, 그 뒤로는 마지막으로 받은 번호를 after 로 준다. 못 본 것만 받는다.
    """
    table, messages = await service.list_messages(session, user.user_id, table_id, after, limit)
    return MessagePage(items=[to_message(message) for message in messages], last_sequence=table.last_message_sequence)
