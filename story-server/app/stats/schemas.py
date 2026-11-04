# story-server/app/stats/schemas.py

"""세계관마다 세션을 시작한 수의 답(#985). asset 서버의 app/stats/client.py 가 같은 모양을 읽는다."""

import uuid

from pydantic import BaseModel


class WorkStarts(BaseModel):
    """세계관 하나(asset 서버의 id)의 세션 시작 수. recent 는 최근 recent_days 일 동안의 수다."""

    work_id: uuid.UUID
    total: int
    recent: int


class WorkStartsList(BaseModel):
    """한 번이라도 세션을 시작한 세계관 모두. 시작한 적이 없는 것은 빠진다."""

    recent_days: int
    items: list[WorkStarts]
