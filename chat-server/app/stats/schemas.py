# chat-server/app/stats/schemas.py

"""캐릭터마다 대화를 시작한 수의 답(#985). asset 서버의 app/stats/client.py 가 같은 모양을 읽는다."""

import uuid

from pydantic import BaseModel


class WorkStarts(BaseModel):
    """캐릭터 하나(asset 서버의 id)의 대화 시작 수. recent 는 최근 recent_days 일 동안의 수다."""

    work_id: uuid.UUID
    total: int
    recent: int


class WorkStartsList(BaseModel):
    """한 번이라도 대화을 시작한 캐릭터 모두. 시작한 적이 없는 것은 빠진다."""

    recent_days: int
    items: list[WorkStarts]
