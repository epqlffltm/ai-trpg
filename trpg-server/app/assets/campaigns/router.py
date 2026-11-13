# trpg-server/app/assets/campaigns/router.py

"""
캠페인 API(#481 B). 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

모든 주소가 로그인을 요구한다. 자기 캠페인만 다룰 수 있다(남의 것은 404).
/campaigns/{id}/versions 는 그 캠페인의 판이다. 만들고 읽기만 한다. 고치거나 지우는 주소가 없다.
게시가 막히면 시나리오의 게시와 같은 409(problems)다(app/assets/scenarios/router.py 의 handle_scenario_not_ready).
"""

import uuid

from fastapi import APIRouter, status
from server_core.auth.dependencies import CurrentUser

from app.assets.campaigns import publishing, service
from app.assets.campaigns.models import Campaign, CampaignVersion
from app.assets.campaigns.schemas import (
    CampaignCreate,
    CampaignDetail,
    CampaignPage,
    CampaignPublishCheck,
    CampaignSnapshot,
    CampaignSummary,
    CampaignUpdate,
    CampaignVersionCreate,
    CampaignVersionDetail,
    CampaignVersionSummary,
)
from app.assets.models import Rating
from app.assets.ratings import allowed_ratings
from app.assets.routing import Paging, Session, to_summary

router = APIRouter(prefix='/campaigns', tags=['campaigns'])


def to_campaign_summary(campaign: Campaign) -> CampaignSummary:
    """캠페인을 목록의 한 줄로."""
    return CampaignSummary(
        **to_summary(campaign.asset).model_dump(),
        rating=Rating(campaign.asset.rating),
        episode_count=len(campaign.episodes),
    )


async def to_detail(session: Session, campaign: Campaign) -> CampaignDetail:
    """캠페인 하나를 응답으로. 편마다 시나리오의 지금 제목과 마지막 판 번호를 붙인다."""
    return CampaignDetail(
        **to_campaign_summary(campaign).model_dump(), episodes=await service.describe_episodes(session, campaign)
    )


def to_version_summary(version: CampaignVersion) -> CampaignVersionSummary:
    """판을 목록용 응답으로. 굳힌 내용은 싣지 않는다."""
    return CampaignVersionSummary(
        id=version.id, number=version.number, note=version.note, created_at=version.created_at
    )


def to_version_detail(version: CampaignVersion) -> CampaignVersionDetail:
    """판을 굳힌 내용과 함께."""
    return CampaignVersionDetail(
        **to_version_summary(version).model_dump(), snapshot=CampaignSnapshot.model_validate(version.snapshot)
    )


@router.post('', response_model=CampaignDetail, status_code=status.HTTP_201_CREATED)
async def create_campaign(data: CampaignCreate, user: CurrentUser, session: Session) -> CampaignDetail:
    """캠페인을 만든다. 편은 자기 시나리오만 가리킨다. 비워도 된다."""
    campaign = await service.create_campaign(session, user.user_id, data)
    return await to_detail(session, campaign)


@router.get('', response_model=CampaignPage, status_code=status.HTTP_200_OK)
async def list_campaigns(user: CurrentUser, session: Session, paging: Paging) -> CampaignPage:
    """자기 캠페인의 목록을 최근에 만든 것부터."""
    campaigns, total = await service.list_campaigns(session, user.user_id, paging.limit, paging.offset)
    return CampaignPage(items=[to_campaign_summary(campaign) for campaign in campaigns], total=total)


@router.get('/{campaign_id}', response_model=CampaignDetail, status_code=status.HTTP_200_OK)
async def read_campaign(campaign_id: uuid.UUID, user: CurrentUser, session: Session) -> CampaignDetail:
    """자기 캠페인 하나."""
    return await to_detail(session, await service.get_campaign(session, user.user_id, campaign_id))


@router.patch('/{campaign_id}', response_model=CampaignDetail, status_code=status.HTTP_200_OK)
async def update_campaign(
    campaign_id: uuid.UUID, data: CampaignUpdate, user: CurrentUser, session: Session
) -> CampaignDetail:
    """자기 캠페인을 고친다. 보낸 칸만 바뀐다. 편은 목록을 통째로 바꾼다."""
    campaign = await service.update_campaign(session, user.user_id, campaign_id, data)
    return await to_detail(session, campaign)


@router.delete('/{campaign_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(campaign_id: uuid.UUID, user: CurrentUser, session: Session) -> None:
    """자기 캠페인을 지운다."""
    await service.delete_campaign(session, user.user_id, campaign_id)


# --- 판 ---


@router.post('/{campaign_id}/versions', response_model=CampaignVersionDetail, status_code=status.HTTP_201_CREATED)
async def publish_campaign(
    campaign_id: uuid.UUID, data: CampaignVersionCreate, user: CurrentUser, session: Session
) -> CampaignVersionDetail:
    """자기 캠페인을 게시한다. 편마다 시나리오의 마지막 판 번호가 새 판으로 굳는다."""
    version = await publishing.publish(session, user.user_id, campaign_id, data, allowed_ratings(user))
    return to_version_detail(version)


@router.get('/{campaign_id}/publish-check', response_model=CampaignPublishCheck, status_code=status.HTTP_200_OK)
async def check_publishable(campaign_id: uuid.UUID, user: CurrentUser, session: Session) -> CampaignPublishCheck:
    """지금 게시하면 막히는 이유와 알릴 것을 미리 본다. 게시(POST /versions)와 같은 검사다."""
    problems, warnings = await publishing.check_publishable(session, user.user_id, campaign_id)
    return CampaignPublishCheck(ready=not problems, problems=problems, warnings=warnings)


@router.get('/{campaign_id}/versions', response_model=list[CampaignVersionSummary], status_code=status.HTTP_200_OK)
async def list_versions(campaign_id: uuid.UUID, user: CurrentUser, session: Session) -> list[CampaignVersionSummary]:
    """자기 캠페인의 판을 최근 것부터. 굳힌 내용은 싣지 않는다."""
    return [
        to_version_summary(version) for version in await publishing.list_versions(session, user.user_id, campaign_id)
    ]


@router.get('/{campaign_id}/versions/{number}', response_model=CampaignVersionDetail, status_code=status.HTTP_200_OK)
async def read_version(
    campaign_id: uuid.UUID, number: int, user: CurrentUser, session: Session
) -> CampaignVersionDetail:
    """자기 캠페인의 판 하나를 굳힌 내용과 함께."""
    return to_version_detail(await publishing.get_version(session, user.user_id, campaign_id, number))
