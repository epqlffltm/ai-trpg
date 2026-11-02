# trpg-server/app/assets/campaigns/service.py

"""
캠페인의 초안을 만들고 읽고 고치고 지운다(#481 B, docs/architecture/campaigns.md). 게시는 publishing.py 다.

  - 편은 자기 시나리오만 가리킨다. 지운 것이나 남의 것이면 AssetReferenceError('episodes'), 422 다.
    가리키는 동안 시나리오가 지워지지 않게 저장이 끝날 때까지 붙잡는다(hold_reference).
  - 편을 고치면 목록을 통째로 바꾼다. 차례는 목록의 차례다.
  - 초안의 등급은 처음에 전체 이용가이고, 게시할 때 편들의 등급으로 정한다.

HTTP 를 모른다. 안 되는 일은 예외로 알린다.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import service as assets
from app.assets.campaigns import repository
from app.assets.campaigns.models import Campaign, CampaignEpisode
from app.assets.campaigns.schemas import CampaignCreate, CampaignUpdate, EpisodeIn, EpisodeOut
from app.assets.models import Asset, AssetType, Scenario

# 입력에서 편이 틀렸을 때 알리는 칸의 이름
EPISODES_FIELD = 'episodes'


async def hold_scenarios(session: AsyncSession, owner_id: uuid.UUID, episodes: list[EpisodeIn]) -> None:
    """편들이 가리키는 시나리오가 모두 자기 것으로 있는지 보고, 저장이 끝날 때까지 지워지지 않게 붙잡는다."""
    for episode in episodes:
        await assets.hold_reference(session, Scenario, owner_id, episode.scenario_id, EPISODES_FIELD)


def build_episodes(episodes: list[EpisodeIn]) -> list[CampaignEpisode]:
    """입력의 편들을 행으로. 차례는 목록의 차례다."""
    return [
        CampaignEpisode(position=position, scenario_id=episode.scenario_id, title=episode.title)
        for position, episode in enumerate(episodes)
    ]


async def create_campaign(session: AsyncSession, owner_id: uuid.UUID, data: CampaignCreate) -> Campaign:
    """캠페인을 만든다. 편의 시나리오가 자기 것이 아니면 AssetReferenceError."""
    await hold_scenarios(session, owner_id, data.episodes)
    campaign = Campaign(
        asset=assets.build_asset(owner_id, AssetType.CAMPAIGN, data), episodes=build_episodes(data.episodes)
    )
    return await assets.create(session, campaign)


async def list_campaigns(
    session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[Campaign], int]:
    """자기 캠페인의 한 쪽과 전체 개수."""
    return await assets.list_owned(session, Campaign, owner_id, limit, offset)


async def get_campaign(session: AsyncSession, owner_id: uuid.UUID, campaign_id: uuid.UUID) -> Campaign:
    """자기 캠페인 하나. 없으면 AssetNotFoundError."""
    return await assets.get_owned(session, Campaign, owner_id, campaign_id)


async def replace_episodes(session: AsyncSession, campaign: Campaign, episodes: list[EpisodeIn]) -> None:
    """
    편 목록을 통째로 바꾼다. 옛 행을 먼저 지운 뒤에 새 행을 넣는다.

    한 번에 바꾸면 옛 행이 지워지기 전에 새 행이 들어가 차례(position)와 시나리오의 UNIQUE 에 걸린다.
    """
    campaign.episodes.clear()
    await session.flush()
    campaign.episodes.extend(build_episodes(episodes))


async def update_campaign(
    session: AsyncSession, owner_id: uuid.UUID, campaign_id: uuid.UUID, data: CampaignUpdate
) -> Campaign:
    """자기 캠페인을 고친다. 보낸 칸만 바뀐다. 없으면 AssetNotFoundError, 편이 틀렸으면 AssetReferenceError."""
    campaign = await assets.lock_owned(session, Campaign, owner_id, campaign_id)
    if data.episodes is not None:
        await hold_scenarios(session, owner_id, data.episodes)
        await replace_episodes(session, campaign, data.episodes)
    return await assets.save_changes(session, campaign, data.model_copy(update={'episodes': None}))


async def delete_campaign(session: AsyncSession, owner_id: uuid.UUID, campaign_id: uuid.UUID) -> None:
    """자기 캠페인을 지운다. 지운 시각만 적는다(판과 플레이가 가리킬 수 있다)."""
    await assets.delete_owned(session, Campaign, owner_id, campaign_id)


async def scenario_titles(session: AsyncSession, scenario_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """시나리오마다 지금의 제목."""
    if not scenario_ids:
        return {}
    query = select(Asset.id, Asset.title).where(Asset.id.in_(scenario_ids))
    return {asset_id: title for asset_id, title in (await session.execute(query)).all()}


async def describe_episodes(session: AsyncSession, campaign: Campaign) -> list[EpisodeOut]:
    """초안의 편들을 응답으로. 시나리오의 지금 제목과 게시한 마지막 판 번호를 붙인다."""
    scenario_ids = [episode.scenario_id for episode in campaign.episodes]
    titles = await scenario_titles(session, scenario_ids)
    numbers = await repository.last_scenario_numbers(session, scenario_ids)
    return [
        EpisodeOut(
            scenario_id=episode.scenario_id,
            title=episode.title,
            scenario_title=titles.get(episode.scenario_id, ''),
            last_version=numbers.get(episode.scenario_id),
        )
        for episode in campaign.episodes
    ]
