# trpg-server/app/campaigns/service.py

"""
캠페인의 플레이를 시작하고 읽는다(#481 B, docs/architecture/campaigns.md 의 "한 판(플레이)의 흐름").

  - 시작: 캠페인의 주인이 자기 캠페인의 판(비우면 마지막 판)으로 첫 편의 테이블을 연다. 테이블을 여는 일은
    보통의 테이블 만들기(app/tables/service.py 의 create_table)와 같고, 시나리오와 판만 캠페인의 판이 정한다.
  - 편의 끝: app/campaigns/ending.py. 방장이 테이블을 끝낼 때 넘길 것을 적는다.
  - 다음 편: 방장이 앞 편의 테이블이 끝난 뒤에 다음 편의 테이블을 연다. 방장이 넘긴 캐릭터가 있으면 그것으로 앉는다.
  - 들어오기: 그 플레이의 사람(앞 편에 앉았거나 넘긴 것이 있는 사람)은 초대 코드 없이 지금 편의 테이블에 앉는다.
    넘긴 캐릭터가 있으면 그것으로 앉는다(app/campaigns/seating.py).

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
from app.campaigns import repository, seating
from app.campaigns.carrying import Carry
from app.campaigns.ending import is_last, run_snapshot
from app.campaigns.models import CampaignCarry, CampaignRun, CampaignTable, RunStatus
from app.campaigns.schemas import QuestResultOut, RunCreate, RunDetail, RunEpisodeOut, RunTable
from app.events import recorder
from app.events.models import EventType
from app.tables import repository as table_repository
from app.tables import service as tables
from app.tables.building import require_rating
from app.tables.errors import Conflict, NotHostError, TableConflictError
from app.tables.model_picker import ModelPicker
from app.tables.models import GameTable, TableMember, TableStatus
from app.tables.schemas import TableCreate
from app.tables.seating import take_seat
from app.tables.state import find_member


async def find_version(
    session: AsyncSession, owner_id: uuid.UUID, campaign_id: uuid.UUID, number: int | None
) -> CampaignVersion:
    """자기 캠페인의 그 판. 번호가 없으면 마지막 판이다. 캠페인이나 판이 없으면 AssetNotFoundError."""
    if number is None:
        await assets.get_owned(session, Campaign, owner_id, campaign_id)
        number = await campaign_repository.last_number(session, campaign_id)
    return await campaign_versions.get_version(session, owner_id, campaign_id, number)


def episode_table(table: RunTable, snapshot: CampaignSnapshot, position: int) -> TableCreate:
    """그 편의 테이블을 여는 값. 받은 테이블의 값에 그 편의 시나리오와 판을 채운다."""
    episode = snapshot.episodes[position]
    options = table.model_dump(exclude={'scenario_id', 'version'}, exclude_unset=True)
    return TableCreate(scenario_id=episode.scenario_id, version=episode.version, **options)


async def start_run(session: AsyncSession, viewer: AccessClaims, data: RunCreate, picker: ModelPicker) -> CampaignRun:
    """
    플레이를 시작한다. 첫 편의 테이블을 열고 그 테이블을 플레이의 1편으로 잇는다.

    캠페인이나 판이 없으면 AssetNotFoundError. 테이블을 열지 못하는 까닭(정원, 등급, 서술 모델 …)은
    테이블 만들기와 같다.
    테이블과 플레이와 그 이음을 한 묶음으로 저장한다. 일부만 저장되는 일이 없다.
    """
    version = await find_version(session, viewer.user_id, data.campaign_id, data.version)
    snapshot = CampaignSnapshot.model_validate(version.snapshot)
    table = await tables.open_table(session, viewer, episode_table(data.table, snapshot, 0), picker)
    run = CampaignRun(campaign_id=data.campaign_id, version_id=version.id, host_id=viewer.user_id, position=0)
    repository.add(session, run)
    await session.flush()
    repository.add(session, CampaignTable(table_id=table.id, run_id=run.id, position=0))
    await tables.commit(session, table)
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
            RunEpisodeOut(
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


# --- 다음 편 ---


async def lock_hosted(session: AsyncSession, user_id: uuid.UUID, run_id: uuid.UUID) -> CampaignRun:
    """
    방장이 자기 플레이를 잠근다. 볼 수 없는 플레이면 AssetNotFoundError, 방장이 아니면 NotHostError.

    볼 수 있는지는 잠그기 전에 본다(get_run). 방장은 바뀌지 않으므로 잠근 뒤에 다시 보지 않아도 된다.
    """
    await get_run(session, user_id, run_id)
    run = await repository.lock_run(session, run_id)
    if run is None:
        raise AssetNotFoundError
    if run.host_id != user_id:
        raise NotHostError
    return run


async def advance(session: AsyncSession, run: CampaignRun, snapshot: CampaignSnapshot) -> None:
    """
    다음 편으로 넘어갈 수 있는지 보고 넘어간다. 지금 편의 테이블이 없으면 그 편을 연다(지금은 생기지 않는다).

    플레이가 끝났으면 TableConflictError(run_ended),
    지금 편의 테이블이 끝나지 않았으면 TableConflictError(episode_not_ended).
    앞 편의 테이블은 잠그지 않고 읽는다. 끝난 테이블은 다시 바뀌지 않는다.
    잠그면 편의 끝(테이블 → 플레이)과 잠그는 차례가 엇갈려 서로 기다리다 막힐 수 있다.
    """
    if run.status == RunStatus.ENDED:
        raise TableConflictError(Conflict.RUN_ENDED)
    link = await repository.table_at(session, run.id, run.position)
    if link is None:
        return
    table = await table_repository.find_table(session, link.table_id)
    if table is None or table.status != TableStatus.ENDED:
        raise TableConflictError(Conflict.EPISODE_NOT_ENDED)
    if is_last(run, snapshot):
        raise TableConflictError(Conflict.RUN_ENDED)
    run.position += 1


async def seat_host(session: AsyncSession, run: CampaignRun, table: GameTable) -> None:
    """새 편의 테이블에 앉은 방장이 넘긴 캐릭터가 있으면 그것으로 앉힌다. 저장은 부른 쪽이 한다."""
    member = find_member(table, run.host_id)
    if member is not None:
        await seating.seat_carried(session, run, table, member)


async def open_next(
    session: AsyncSession, viewer: AccessClaims, run_id: uuid.UUID, options: RunTable, picker: ModelPicker
) -> CampaignRun:
    """
    방장이 다음 편의 테이블을 연다. 테이블을 여는 값은 테이블 만들기와 같다(시나리오와 판은 캠페인의 판이 정한다).

    플레이를 잠그고 한다. 넘어간 편의 번호, 새 테이블, 그 이음, 방장의 넘긴 캐릭터를 한 묶음으로 저장한다.
    잠근 채로 저장하므로 두 요청이 같은 편을 두 번 열지 못한다.
    """
    run = await lock_hosted(session, viewer.user_id, run_id)
    snapshot = await run_snapshot(session, run)
    await advance(session, run, snapshot)
    table = await tables.open_table(session, viewer, episode_table(options, snapshot, run.position), picker)
    repository.add(session, CampaignTable(table_id=table.id, run_id=run_id, position=run.position))
    await seat_host(session, run, table)
    await tables.commit(session, table)
    return run


# --- 들어오기 ---


async def join_run(session: AsyncSession, viewer: AccessClaims, run_id: uuid.UUID) -> GameTable:
    """
    그 플레이의 사람이 지금 편의 테이블에 초대 코드 없이 앉는다. 넘긴 캐릭터가 있으면 그것으로 앉는다.

    볼 수 없는 플레이면 AssetNotFoundError, 지금 편의 테이블이 없으면 TableConflictError(not_recruiting).
    성인용 테이블인데 성인용을 볼 수 없으면 AdultContentRequiredError. 모집 중이 아니거나, 이미 앉아 있거나,
    자리가 없으면 TableConflictError(테이블에 들어오기와 같다).
    """
    run = await get_run(session, viewer.user_id, run_id)
    link = await repository.table_at(session, run.id, run.position)
    if link is None:
        raise TableConflictError(Conflict.NOT_RECRUITING)
    table = await table_repository.lock_table(session, link.table_id)
    if table is None:
        raise AssetNotFoundError
    require_rating(viewer, table.rating)
    take_seat(table, viewer.user_id)
    member = find_member(table, viewer.user_id)
    if member is not None:
        await seating.seat_carried(session, run, table, member)
    recorder.record(session, table, EventType.MEMBER_JOINED, actor_id=viewer.user_id, payload={'via': 'campaign'})
    return await tables.save(session, table)
