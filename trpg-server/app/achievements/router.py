# trpg-server/app/achievements/router.py

"""
시나리오 업적 API. 공개된 시나리오의 업적 목록과 달성률을 누구나 본다(로그인하지 않아도, #530).

    GET /listings/{scenario_id}/achievements
    GET /achievements/mine         내가 받은 업적 전부(모든 시나리오, 받은 때가 늦은 것부터). 로그인해야 한다

로그인했으면 내가 받은 때가 함께 실리고, 받은 숨긴 업적은 이름과 그림이 보인다.
업적을 주는 것은 엔진뿐이다(docs/architecture/achievements.md). 주는 주소는 없다.
"""

import uuid

from fastapi import APIRouter, status
from server_core.auth.dependencies import CurrentUser, OptionalUser

from app.achievements import service
from app.achievements.schemas import MyAchievementPage, ScenarioAchievements
from app.assets.routing import Paging, Session

router = APIRouter(prefix='/listings', tags=['achievements'])
# 내 업적. 시나리오 하나에 매이지 않아 공개 목록과 다른 머리 주소다
mine_router = APIRouter(prefix='/achievements', tags=['achievements'])


@router.get('/{scenario_id}/achievements', response_model=ScenarioAchievements, status_code=status.HTTP_200_OK)
async def read_achievements(scenario_id: uuid.UUID, user: OptionalUser, session: Session) -> ScenarioAchievements:
    """
    공개된 시나리오의 업적들. 판의 차례다. 업적마다 받은 사람의 수와, 로그인했으면 내가 받은 때가 있다.

    숨긴 업적은 내가 받기 전에는 이름, 설명, 그림이 null 이다. 조건은 싣지 않는다.
    볼 수 없는 시나리오(공개하지 않음, 볼 수 없는 등급)면 404 다. 토큰을 보냈는데 틀렸으면 401 이다.
    """
    return await service.scenario_achievements(session, user, scenario_id)


@mine_router.get('/mine', response_model=MyAchievementPage, status_code=status.HTTP_200_OK)
async def read_mine(user: CurrentUser, session: Session, page: Paging) -> MyAchievementPage:
    """
    내가 받은 시나리오의 업적들. 모든 시나리오의 것이고 받은 때가 늦은 것부터다(?limit=&offset=).

    받았으므로 숨긴 업적도 이름과 그림이 있다. 시나리오를 공개하지 않게 됐어도 받은 기록은 보인다(listed 가 거짓).
    """
    return await service.my_achievements(session, user, page.limit, page.offset)
