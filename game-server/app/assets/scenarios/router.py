# game-server/app/assets/scenarios/router.py

"""
시나리오 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

규칙은 여기 없다. 누가 보낸 요청인지(토큰)와 입력의 모양만 확인하고 서비스에 맡긴다.
모든 주소가 로그인을 요구한다. 자기 시나리오만 다룰 수 있다.
"""

import uuid

from fastapi import APIRouter, status

from app.assets.models import Scenario
from app.assets.routing import Paging, Session, to_page, to_summary
from app.assets.scenarios import service
from app.assets.scenarios.schemas import ScenarioCreate, ScenarioDetail, ScenarioUpdate
from app.assets.schemas import AssetPage
from app.auth.dependencies import CurrentUser

router = APIRouter(prefix='/scenarios', tags=['scenarios'])


def to_detail(scenario: Scenario) -> ScenarioDetail:
    """시나리오를 만든 사람에게 보여 주는 응답으로 바꾼다."""
    return ScenarioDetail(
        **to_summary(scenario.asset).model_dump(),
        rulebook_id=scenario.rulebook_id,
        world_id=scenario.world_id,
        opening=scenario.opening,
    )


@router.post('', response_model=ScenarioDetail, status_code=status.HTTP_201_CREATED)
async def create_scenario(data: ScenarioCreate, user: CurrentUser, session: Session) -> ScenarioDetail:
    """시나리오를 만든다. 룰북과 세계관은 자기 것만 가리킬 수 있다."""
    scenario = await service.create_scenario(session, user.user_id, data)
    return to_detail(scenario)


@router.get('', response_model=AssetPage, status_code=status.HTTP_200_OK)
async def list_scenarios(user: CurrentUser, session: Session, paging: Paging) -> AssetPage:
    """자기 시나리오의 목록을 최근에 만든 것부터 돌려준다."""
    scenarios, total = await service.list_scenarios(session, user.user_id, paging.limit, paging.offset)
    return to_page(scenarios, total)


@router.get('/{scenario_id}', response_model=ScenarioDetail, status_code=status.HTTP_200_OK)
async def read_scenario(scenario_id: uuid.UUID, user: CurrentUser, session: Session) -> ScenarioDetail:
    """자기 시나리오 하나를 돌려준다."""
    scenario = await service.get_scenario(session, user.user_id, scenario_id)
    return to_detail(scenario)


@router.patch('/{scenario_id}', response_model=ScenarioDetail, status_code=status.HTTP_200_OK)
async def update_scenario(
    scenario_id: uuid.UUID, data: ScenarioUpdate, user: CurrentUser, session: Session
) -> ScenarioDetail:
    """자기 시나리오를 고친다. 보낸 칸만 바뀐다. 룰북과 세계관은 null 을 보내면 떼어 낸다."""
    scenario = await service.update_scenario(session, user.user_id, scenario_id, data)
    return to_detail(scenario)


@router.delete('/{scenario_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_scenario(scenario_id: uuid.UUID, user: CurrentUser, session: Session) -> None:
    """자기 시나리오를 지운다."""
    await service.delete_scenario(session, user.user_id, scenario_id)
