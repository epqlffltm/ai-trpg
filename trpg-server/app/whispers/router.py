# trpg-server/app/whispers/router.py

"""
쪽지 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

주소는 테이블 아래에 둔다(/tables/{table_id}/whispers). 쪽지는 테이블에 딸린 것이다.
읽기는 자기 쪽지함만이다. 다른 사람의 쪽지함을 읽는 주소는 없다.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from server_core.auth.dependencies import CurrentUser

from app.assets.routing import MAX_PAGE_SIZE, Session
from app.limits.routing import Limited
from app.whispers import service
from app.whispers.responses import to_whisper
from app.whispers.schemas import WhisperCreate, WhisperOut, WhisperPage

router = APIRouter(prefix='/tables/{table_id}/whispers', tags=['whispers'])

# 한 번에 읽는 쪽지의 수
DEFAULT_WHISPER_LIMIT = 50


@router.post('', response_model=WhisperOut, status_code=status.HTTP_201_CREATED)
async def post_whisper(
    table_id: uuid.UUID, data: WhisperCreate, user: CurrentUser, session: Session, limiting: Limited
) -> WhisperOut:
    """
    같은 테이블에 앉은 한 사람에게 쪽지를 보낸다. 보낸 사람과 받은 사람만 본다. 방장도 보지 못한다.

    gm_visible 이면 GM(AI)도 그 라운드의 서술에서 숨은 정보로 본다. 서술은 모두에게 나가므로 내용이 새어 나갈 수 있다.
    테이블이 알리기로 했으면(whisper_notice) 보냈다는 사실만 이벤트(whisper_sent)로 모두에게 간다.
    """
    whisper = await service.post_whisper(session, user.user_id, table_id, data, limiting)
    return to_whisper(whisper)


@router.get('', response_model=WhisperPage, status_code=status.HTTP_200_OK)
async def list_whispers(
    table_id: uuid.UUID,
    user: CurrentUser,
    session: Session,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_WHISPER_LIMIT,
) -> WhisperPage:
    """
    자기 쪽지함의 쪽지를 순서대로 돌려준다. 보낸 것과 받은 것이 함께 온다. after 를 주면 그 번호 뒤의 것만 온다.

    번호는 쪽지함마다 센다. 채팅의 번호와 따로다.
    """
    last_sequence, whispers = await service.list_whispers(session, user.user_id, table_id, after, limit)
    return WhisperPage(items=[to_whisper(whisper) for whisper in whispers], last_sequence=last_sequence)
