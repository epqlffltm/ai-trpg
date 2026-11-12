# trpg-server/app/campaigns/listing.py

"""
캠페인의 플레이를 찾는다(#481 B, 웹의 내 플레이 목록과 테이블 방의 편 표시).

  - 내 플레이: 내가 연 것, 그 플레이의 테이블에 앉아 있는 것, 넘긴 것이 있는 것. 최근에 시작한 것부터.
    볼 수 있는 사람은 GET /campaign-runs/{id} 와 같다(app/campaigns/service.py 의 get_run).
  - 테이블의 플레이: 그 테이블이 어느 플레이의 몇 편인가. 캠페인의 테이블이 아니거나 볼 수 없으면 None 이다.
    볼 수 없는 것과 없는 것을 가르지 않는다(있다는 것을 드러내지 않는다).
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.campaigns.models import CampaignVersion
from app.assets.campaigns.schemas import CampaignSnapshot
from app.assets.service import AssetNotFoundError
from app.campaigns import repository, service
from app.campaigns.models import CampaignRun, RunStatus
from app.campaigns.schemas import RunPage, RunSummary


def to_run_summary(run: CampaignRun, version: CampaignVersion, table_id: uuid.UUID | None) -> RunSummary:
    """플레이 하나를 목록의 값으로. 제목과 편은 그 플레이의 판에서 읽는다."""
    snapshot = CampaignSnapshot.model_validate(version.snapshot)
    return RunSummary(
        id=run.id,
        campaign_id=run.campaign_id,
        title=snapshot.title,
        host_id=run.host_id,
        status=RunStatus(run.status),
        position=run.position,
        episode_count=len(snapshot.episodes),
        episode_title=snapshot.episodes[run.position].title,
        table_id=table_id,
        created_at=run.created_at,
        ended_at=run.ended_at,
    )


async def list_my_runs(session: AsyncSession, user_id: uuid.UUID, limit: int, offset: int) -> RunPage:
    """내 플레이의 한 쪽과 전체의 수."""
    runs = await repository.list_runs_of(session, user_id, limit, offset)
    versions = await repository.versions_of(session, [run.version_id for run in runs])
    tables = await repository.current_tables(session, runs)
    items = [to_run_summary(run, versions[run.version_id], tables.get(run.id)) for run in runs]
    return RunPage(items=items, total=await repository.count_runs_of(session, user_id))


async def run_of_table(session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID) -> CampaignRun | None:
    """그 테이블의 플레이. 캠페인의 테이블이 아니거나 볼 수 없으면 None."""
    link = await repository.find_link(session, table_id)
    if link is None:
        return None
    try:
        return await service.get_run(session, user_id, link.run_id)
    except AssetNotFoundError:
        return None
