# story-server/app/stats/router.py

"""
asset 서버가 세계관마다 세션을 시작한 수를 받아 가는 주소(#985).

    GET /api/v1/story/service/stats/world-starts
    서명: asset 서버의 비밀(ASSET_SECRET, app/core/service_auth.py). 이 서버가 asset 서버를 부를 때와 같은 비밀이다

  - 서명이 틀리면 401 이다. 사용자의 토큰은 없다(사람이 부르는 주소가 아니다)
  - 답은 시작한 적이 있는 세계관 모두의 수다. asset 서버가 통째로 받아 바꿔 넣으므로 다시 불러도 같다
  - 프록시는 /api/v1/story/service/ 를 밖에서 받지 않는다(404). asset 서버는 compose 의 안쪽 주소로 부른다
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, status

from app.core.dependencies import Session
from app.core.service_auth import AssetServerBody
from app.stats.repository import count_starts
from app.stats.schemas import WorkStarts, WorkStartsList

router = APIRouter(prefix='/service/stats', tags=['service'])

# "최근"의 날 수. 랭킹은 최근 7일이다(asset 서버의 app/stats 와 같다)
RECENT_DAYS = 7


@router.get('/world-starts', response_model=WorkStartsList, status_code=status.HTTP_200_OK)
async def list_starts(_signed: AssetServerBody, session: Session) -> WorkStartsList:
    """세계관마다 모든 세션의 수와 최근 RECENT_DAYS 일의 수."""
    since = datetime.now(UTC) - timedelta(days=RECENT_DAYS)
    rows = await count_starts(session, since)
    return WorkStartsList(
        recent_days=RECENT_DAYS,
        items=[WorkStarts(work_id=work_id, total=total, recent=recent) for work_id, total, recent in rows],
    )
