# trpg-server/app/campaigns/service.py

"""
캠페인의 플레이를 시작하고 읽는다(#481 B, docs/architecture/campaigns.md 의 "한 판(플레이)의 흐름").

  - 시작: 캠페인의 주인이 자기 캠페인의 판(비우면 마지막 판)으로 첫 편의 테이블을 연다. 테이블을 여는 일은
    보통의 테이블 만들기(app/tables/service.py 의 create_table)와 같고, 시나리오와 판만 캠페인의 판이 정한다.
  - 편의 끝: app/campaigns/ending.py. 방장이 테이블을 끝낼 때 넘길 것을 적는다.
  - 다음 편, 넘긴 캐릭터로 앉기: 다음 단계다.

플레이는 그 플레이의 테이블에 앉았던 사람과 넘긴 것이 있는 사람과 방장만 본다. 다른 사람에게는 없는 것이다(404).
HTTP 를 모른다.
"""

import uuid

from server_core.auth.tokens import AccessClaims
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import service as assets
from app.assets.campaigns import publishing as campaign_versions
from app.assets.campaigns import repository as campaign_repository
from app.assets.campaigns.models import Campaign, CampaignVersion
from app.assets.campaigns.schemas import CampaignSnapshot
from app.assets.service import AssetNotFoundError
from app.campaigns import repository
from app.campaigns.carrying import Carry
from app.campaigns.models import CampaignCarry, CampaignRun, CampaignTable
from app.campaigns.schemas import EpisodeOut, QuestResultOut, RunCreate, RunDetail
from app.tables import service as tables
from app.tables.model_picker import ModelPicker
from app.tables.models import TableMember
from app.tables.schemas import TableCreate


async def find_version(
    session: AsyncSession, owner_id: uuid.UUID, campaign_id: uuid.UUID, number: int | None
) -> CampaignVersion:
    """자기 캠페인의 그 판. 번호가 없으면 마지막 판이다. 캠페인이나 판이 없으면 AssetNotFoundError."""
    if number is None:
        await assets.get_owned(session, Campaign, owner_id, campaign_id)
        number = await campaign_repository.last_number(session, campaign_id)
    return await campaign_versions.get_version(session, owner_id, campaign_id, number)


def episode_table(data: RunCreate, snapshot: CampaignSnapshot, position: int) -> TableCreate:
    """그 편의 테이블을 여는 값. 받은 테이블의 값에 그 편의 시나리오와 판을 채운다."""
    episode = snapshot.episodes[position]
    options = data.table.model_dump(exclude={'scenario_id', 'version'}, exclude_unset=True)
    return TableCreate(scenario_id=episode.scenario_id, version=episode.version, **options)


async def start_run(session: AsyncSession, viewer: AccessClaims, data: RunCreate, picker: ModelPicker) -> CampaignRun:
    """
    플레이를 시작한다. 첫 편의 테이블을 열고 그 테이블을 플레이의 1편으로 잇는다.

    캠페인이나 판이 없으면 AssetNotFoundError. 테이블을 열지 못하는 까닭(정원, 등급, 서술 모델 …)은
    테이블 만들기와 같다.
    테이블을 연 뒤에 플레이를 저장한다(테이블 만들기가 저장까지 한다). 플레이를 저장하지 못하면 보통의 테이블로 남는다.
    """
    version = await find_version(session, viewer.user_id, data.campaign_id, data.version)
    snapshot = CampaignSnapshot.model_validate(version.snapshot)
    table = await tables.create_table(session, viewer, episode_table(data, snapshot, 0), picker)
    run = CampaignRun(campaign_id=data.campaign_id, version_id=version.id, host_id=viewer.user_id, position=0)
    repository.add(session, run)
    await session.flush()
    repository.add(session, CampaignTable(table_id=table.id, run_id=run.id, position=0))
    await session.commit()
    await session.refresh(run)
    return run


async def seated_in_run(session: AsyncSession, run_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """그 사람이 그 플레이의 테이블에 앉았거나(지금도 앉아 있는 사람) 넘긴 것이 있는가."""
    seated = (
        select(TableMember.user_id)
        .join(CampaignTable, CampaignTable.table_id == TableMember.table_id)
        .where(CampaignTable.run_id == run_id, TableMember.user_id == user_id)
    )
    carried = select(CampaignCarry.user_id).where(CampaignCarry.run_id == run_id, CampaignCarry.user_id == user_id)
    return (await session.scalar(seated.limit(1))) is not None or (await session.scalar(carried.limit(1))) is not None


async def get_run(session: AsyncSession, user_id: uuid.UUID, run_id: uuid.UUID) -> CampaignRun:
    """볼 수 있는 플레이 하나. 없거나 볼 수 없으면 AssetNotFoundError(있다는 것을 드러내지 않는다)."""
    run = await repository.find_run(session, run_id)
    if run is None or (run.host_id != user_id and not await seated_in_run(session, run_id, user_id)):
        raise AssetNotFoundError
    return run


async def describe(session: AsyncSession, run: CampaignRun, viewer_id: uuid.UUID) -> RunDetail:
    """플레이를 응답으로. 편마다의 테이블, 끝난 퀘스트의 결과, 보는 사람이 가장 나중에 넘긴 것을 붙인다."""
    version = await session.get(CampaignVersion, run.version_id)
    if version is None:
        raise AssetNotFoundError
    snapshot = CampaignSnapshot.model_validate(version.snapshot)
    tables_by_position = {link.position: link.table_id for link in await repository.run_tables(session, run.id)}
    carry = await repository.last_carry(session, run.id, viewer_id)
    return RunDetail(
        id=run.id,
        campaign_id=run.campaign_id,
        title=snapshot.title,
        version=version.number,
        host_id=run.host_id,
        status=run.status,
        position=run.position,
        episodes=[
            EpisodeOut(
                position=position,
                title=episode.title,
                scenario_id=episode.scenario_id,
                version=episode.version,
                table_id=tables_by_position.get(position),
            )
            for position, episode in enumerate(snapshot.episodes)
        ],
        quest_results=[
            QuestResultOut(position=row.position, entry_id=row.entry_id, result=row.result)
            for row in await repository.quest_results(session, run.id)
        ],
        my_carry=None if carry is None else Carry.model_validate(carry.carry),
        created_at=run.created_at,
        ended_at=run.ended_at,
    )
