# game-server/app/assets/scenarios/router.py

"""
시나리오 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

규칙은 여기 없다. 누가 보낸 요청인지(토큰)와 입력의 모양만 확인하고 서비스에 맡긴다.
모든 주소가 로그인을 요구한다. 자기 시나리오만 다룰 수 있다.

/scenarios/{id}/versions 는 그 시나리오의 판이다. 판은 만들고 읽기만 한다. 고치거나 지우는 주소가 없다.
"""

import uuid

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.assets.models import Scenario, ScenarioVersion
from app.assets.routing import Paging, Session, to_summary
from app.assets.scenarios import publishing, service
from app.assets.scenarios.publishing import ScenarioNotReadyError
from app.assets.scenarios.schemas import (
    ScenarioCreate,
    ScenarioDetail,
    ScenarioPage,
    ScenarioSummary,
    ScenarioUpdate,
    VersionCreate,
    VersionDetail,
    VersionSummary,
)
from app.assets.scenarios.snapshot import read_snapshot
from app.auth.dependencies import CurrentUser

router = APIRouter(prefix='/scenarios', tags=['scenarios'])


def to_scenario_summary(scenario: Scenario) -> ScenarioSummary:
    """시나리오를 목록용 응답으로 바꾼다. 공통 값에 등급을 더한다."""
    return ScenarioSummary(**to_summary(scenario.asset).model_dump(), rating=scenario.asset.rating)


def to_detail(scenario: Scenario) -> ScenarioDetail:
    """시나리오를 만든 사람에게 보여 주는 응답으로 바꾼다."""
    return ScenarioDetail(
        **to_scenario_summary(scenario).model_dump(),
        rulebook_id=scenario.rulebook_id,
        world_id=scenario.world_id,
        lorebook_ids=scenario.lorebook_ids,
        openings=scenario.openings,
        recommended_players=scenario.recommended_players,
        pregens=scenario.pregens,
        character_modes=scenario.character_modes,
        default_sheet=scenario.default_sheet,
        player_made_hp=scenario.player_made_hp,
    )


def to_version_summary(version: ScenarioVersion) -> VersionSummary:
    """판을 목록용 응답으로 바꾼다. 굳힌 내용은 싣지 않는다."""
    return VersionSummary(id=version.id, number=version.number, note=version.note, created_at=version.created_at)


def to_version_detail(version: ScenarioVersion) -> VersionDetail:
    """판을 만든 사람에게 보여 주는 응답으로 바꾼다. 굳힌 내용을 계약의 모양으로 다시 읽어 싣는다."""
    return VersionDetail(**to_version_summary(version).model_dump(), snapshot=read_snapshot(version.snapshot))


async def handle_scenario_not_ready(request: Request, error: ScenarioNotReadyError) -> JSONResponse:
    """
    서비스가 "게시할 조건을 갖추지 못했다"고 하면 409 로 답한다. 앱에 한 번 등록한다(app/main.py).

    problems 에 갖추지 못한 조건을 전부 싣는다. 화면이 어느 칸을 채워야 하는지 알려 줄 수 있다.
    """
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={'detail': '게시할 조건을 갖추지 못했습니다.', 'problems': list(error.problems)},
    )


@router.post('', response_model=ScenarioDetail, status_code=status.HTTP_201_CREATED)
async def create_scenario(data: ScenarioCreate, user: CurrentUser, session: Session) -> ScenarioDetail:
    """시나리오를 만든다. 룰북, 세계관, 로어북은 자기 것만 가리킬 수 있다."""
    scenario = await service.create_scenario(session, user.user_id, data)
    return to_detail(scenario)


@router.get('', response_model=ScenarioPage, status_code=status.HTTP_200_OK)
async def list_scenarios(user: CurrentUser, session: Session, paging: Paging) -> ScenarioPage:
    """자기 시나리오의 목록을 최근에 만든 것부터 돌려준다. 등급을 함께 싣는다."""
    scenarios, total = await service.list_scenarios(session, user.user_id, paging.limit, paging.offset)
    return ScenarioPage(items=[to_scenario_summary(scenario) for scenario in scenarios], total=total)


@router.get('/{scenario_id}', response_model=ScenarioDetail, status_code=status.HTTP_200_OK)
async def read_scenario(scenario_id: uuid.UUID, user: CurrentUser, session: Session) -> ScenarioDetail:
    """자기 시나리오 하나를 돌려준다."""
    scenario = await service.get_scenario(session, user.user_id, scenario_id)
    return to_detail(scenario)


@router.patch('/{scenario_id}', response_model=ScenarioDetail, status_code=status.HTTP_200_OK)
async def update_scenario(
    scenario_id: uuid.UUID, data: ScenarioUpdate, user: CurrentUser, session: Session
) -> ScenarioDetail:
    """자기 시나리오를 고친다. 보낸 칸만 바뀐다. 룰북과 세계관은 null 로 떼고, 로어북은 목록을 통째로 바꾼다."""
    scenario = await service.update_scenario(session, user.user_id, scenario_id, data)
    return to_detail(scenario)


@router.delete('/{scenario_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_scenario(scenario_id: uuid.UUID, user: CurrentUser, session: Session) -> None:
    """자기 시나리오를 지운다."""
    await service.delete_scenario(session, user.user_id, scenario_id)


# --- 판 ---


@router.post('/{scenario_id}/versions', response_model=VersionDetail, status_code=status.HTTP_201_CREATED)
async def publish_scenario(
    scenario_id: uuid.UUID, data: VersionCreate, user: CurrentUser, session: Session
) -> VersionDetail:
    """자기 시나리오를 게시한다. 지금의 내용이 새 판으로 굳는다."""
    version = await publishing.publish(session, user.user_id, scenario_id, data)
    return to_version_detail(version)


@router.get('/{scenario_id}/versions', response_model=list[VersionSummary], status_code=status.HTTP_200_OK)
async def list_versions(scenario_id: uuid.UUID, user: CurrentUser, session: Session) -> list[VersionSummary]:
    """자기 시나리오의 판을 최근 것부터 돌려준다. 굳힌 내용은 싣지 않는다."""
    versions = await publishing.list_versions(session, user.user_id, scenario_id)
    return [to_version_summary(version) for version in versions]


@router.get('/{scenario_id}/versions/{number}', response_model=VersionDetail, status_code=status.HTTP_200_OK)
async def read_version(scenario_id: uuid.UUID, number: int, user: CurrentUser, session: Session) -> VersionDetail:
    """자기 시나리오의 판 하나를 굳힌 내용과 함께 돌려준다."""
    version = await publishing.get_version(session, user.user_id, scenario_id, number)
    return to_version_detail(version)
