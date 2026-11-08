# trpg-server/app/free_rolls/router.py

"""
자유 굴림 API(#404). 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

주소는 테이블 아래에 둔다(/tables/{table_id}/dice). 굴린 것은 그 테이블의 이벤트로 남는다.
"""

import uuid

from fastapi import APIRouter, status
from server_core.auth.dependencies import CurrentUser

from app.assets.routing import Session
from app.core.dice import Rolling
from app.events.models import TableEvent
from app.free_rolls import service
from app.free_rolls.schemas import FreeRollCreate, FreeRollOut
from app.limits.routing import Limited

router = APIRouter(prefix='/tables/{table_id}/dice', tags=['free-rolls'])


def to_free_roll(event: TableEvent) -> FreeRollOut:
    """적은 이벤트를 응답의 모양으로."""
    return FreeRollOut(sequence=event.sequence, **event.payload)


@router.post('', response_model=FreeRollOut, status_code=status.HTTP_201_CREATED)
async def roll_dice(
    table_id: uuid.UUID, data: FreeRollCreate, user: CurrentUser, session: Session, dice: Rolling, limiting: Limited
) -> FreeRollOut:
    """
    앉은 사람이 주사위를 굴린다. 눈은 서버가 굴리고, 같은 내용이 이벤트(dice_rolled)로 모두에게 간다.

    게임의 상태와 무관하다. 판정도 피해도 아니고, 서술하는 AI 도 받지 않는다.
    주사위 설명이 받는 모양이 아니면 422, 굴리는 수를 넘으면 429 다.
    """
    event = await service.roll_dice(session, user.user_id, table_id, data, dice, limiting)
    return to_free_roll(event)
