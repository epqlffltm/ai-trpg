# trpg-server/app/campaigns/ending.py

"""
캠페인의 편이 끝날 때 넘길 것과 퀘스트 결과를 적는다(docs/architecture/campaigns.md 의 "편의 끝").
방장이 테이블을 끝낼 때(app/tables/service.py 의 end_table) 부른다. 테이블이 끝나는 것과 한 묶음으로 저장된다.

  - 캠페인의 테이블이 아니면 아무것도 하지 않는다.
  - 앉은 사람마다 지금 캐릭터의 넘길 것을 적는다. 죽은 캐릭터, 시작 전이라 시트가 없는 사람은 적지 않는다.
  - 그 편에서 이루었거나 실패한 퀘스트를 적는다.
  - 마지막 편이면 플레이가 끝난다.

모두 나가 끝난 테이블과 운영자의 제재로 끝난 테이블은 부르지 않는다. 넘길 사람이 없거나, 넘기면 안 되는 끝이다.
플레이를 잠그고 한다. 같은 편을 두 번 적지 않는다(UNIQUE 가 마지막 방어선이다).
"""

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.campaigns.models import CampaignVersion
from app.assets.campaigns.schemas import CampaignSnapshot
from app.campaigns import repository
from app.campaigns.carrying import carries_of, quest_results
from app.campaigns.models import CampaignCarry, CampaignQuestResult, CampaignRun, RunStatus
from app.tables.models import GameTable


def is_last(run: CampaignRun, snapshot: CampaignSnapshot) -> bool:
    """지금 편이 마지막 편인가."""
    return run.position >= len(snapshot.episodes) - 1


async def run_snapshot(session: AsyncSession, run: CampaignRun) -> CampaignSnapshot:
    """플레이가 고정한 캠페인 판의 내용."""
    version = await session.get(CampaignVersion, run.version_id)
    if version is None:
        raise LookupError('플레이의 캠페인 판이 없습니다.')
    return CampaignSnapshot.model_validate(version.snapshot)


def write_carries(session: AsyncSession, run: CampaignRun, position: int, table: GameTable) -> None:
    """앉은 사람마다의 넘길 것과 그 편의 퀘스트 결과를 세션에 올린다."""
    for user_id, carry in carries_of(table).items():
        repository.add(
            session,
            CampaignCarry(run_id=run.id, position=position, user_id=user_id, carry=carry.model_dump(mode='json')),
        )
    for entry_id, result in quest_results(table).items():
        repository.add(session, CampaignQuestResult(run_id=run.id, position=position, entry_id=entry_id, result=result))


async def record_end(session: AsyncSession, table: GameTable) -> None:
    """끝나는 테이블이 캠페인의 편이면 넘길 것을 적고, 마지막 편이면 플레이를 끝낸다. 저장은 부른 쪽이 한다."""
    link = await repository.find_link(session, table.id)
    if link is None:
        return
    run = await repository.lock_run(session, link.run_id)
    if run is None:
        return
    write_carries(session, run, link.position, table)
    if is_last(run, await run_snapshot(session, run)):
        run.status = RunStatus.ENDED
        run.ended_at = func.now()
