# trpg-server/app/operators/repository.py

"""
운영자 API 가 쓰는 SQL. 감사 기록을 적고, 남의 것을 주인을 가리지 않고 읽고, 제재의 상태를 적고 읽는다.

일반 API 의 저장소는 "자기 것"과 "앉아 있는 테이블"로 걸러 읽는다. 여기의 함수는 거르지 않는다.
그래서 운영자 API(app/operators/service.py) 말고는 부르지 않는다.
"""

import uuid
from datetime import datetime

from sqlalchemy import ColumnElement, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset, Scenario
from app.operators.models import OperatorAction, OperatorRead, PublishingBan, ScenarioSanction
from app.whispers.models import Whisper


def add_read(session: AsyncSession, read: OperatorRead) -> None:
    """감사 기록 한 줄을 세션에 올린다. 커밋은 부르는 쪽이 한다."""
    session.add(read)


async def find_scenario(session: AsyncSession, scenario_id: uuid.UUID) -> Scenario | None:
    """누구의 것이든 지우지 않은 시나리오 하나를 찾는다. 없으면 None."""
    query = select(Scenario).join(Scenario.asset).where(Scenario.asset_id == scenario_id, Asset.deleted_at.is_(None))
    return await session.scalar(query)


def sent_copies(table_id: uuid.UUID) -> tuple[ColumnElement[bool], ...]:
    """
    테이블의 귓속말을 한 장씩 고르는 조건.

    쪽지는 보낸 사람과 받은 사람의 쪽지함에 한 장씩 적힌다. 보낸 사람의 쪽지함의 것만 고르면 한 장씩이다.
    """
    return Whisper.table_id == table_id, Whisper.owner_id == Whisper.sender_id


async def list_whispers(session: AsyncSession, table_id: uuid.UUID, limit: int, offset: int) -> list[Whisper]:
    """테이블의 귓속말 전부를 보낸 순서대로 돌려준다. 쪽지함이 아니라 테이블 전체라 번호가 아니라 offset 으로 넘긴다."""
    query = (
        select(Whisper)
        .where(*sent_copies(table_id))
        .order_by(Whisper.created_at, Whisper.id)
        .limit(limit)
        .offset(offset)
    )
    return list(await session.scalars(query))


async def count_whispers(session: AsyncSession, table_id: uuid.UUID) -> int:
    """테이블의 귓속말이 모두 몇 장인가."""
    query = select(func.count()).select_from(Whisper).where(*sent_copies(table_id))
    return await session.scalar(query) or 0


# --- 제재(#392) ---


def add_action(session: AsyncSession, action: OperatorAction) -> None:
    """제재의 감사 기록 한 줄을 세션에 올린다. 제재와 같은 트랜잭션에서 커밋한다."""
    session.add(action)


def add_sanction(session: AsyncSession, sanction: ScenarioSanction) -> None:
    """제재된 판 하나를 세션에 올린다."""
    session.add(sanction)


async def lock_scenario(session: AsyncSession, scenario_id: uuid.UUID) -> Scenario | None:
    """누구의 것이든 지우지 않은 시나리오 하나를 찾아 잠근다. 제작자의 공개와 운영자의 제재가 엇갈리지 않게."""
    query = (
        select(Scenario)
        .join(Scenario.asset)
        .where(Scenario.asset_id == scenario_id, Asset.deleted_at.is_(None))
        .with_for_update(of=Asset)
    )
    return await session.scalar(query)


async def lock_owner(session: AsyncSession, owner_id: uuid.UUID) -> None:
    """
    한 사람의 공개 금지를 정하는 일을 이 트랜잭션이 끝날 때까지 혼자 한다.

    두 시나리오가 동시에 제재되면 둘 다 상대의 제재를 보지 못하고 세어, 금지에 닿고도 넘어갈 수 있다.
    금지의 줄은 아직 없을 수 있어서 줄을 잠그지 않고 사람마다의 잠금(advisory lock)을 쓴다.
    """
    await session.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key': f'publishing:{owner_id}'})


async def is_sanctioned(session: AsyncSession, version_id: uuid.UUID) -> bool:
    """그 판이 제재되었는가."""
    return await session.get(ScenarioSanction, version_id) is not None


async def find_ban(session: AsyncSession, user_id: uuid.UUID) -> PublishingBan | None:
    """그 사람의 공개 금지의 줄. 한 번도 금지된 적이 없으면 None."""
    return await session.get(PublishingBan, user_id)


def add_ban(session: AsyncSession, ban: PublishingBan) -> None:
    """공개 금지의 줄을 세션에 올린다. 처음 금지될 때만 쓴다."""
    session.add(ban)


async def count_sanctions(session: AsyncSession, owner_id: uuid.UUID, since: datetime | None) -> int:
    """그 사람의 시나리오가 제재된 수. since 를 주면 그 뒤의 것만 센다(공개 금지가 풀린 뒤)."""
    query = select(func.count()).select_from(ScenarioSanction).where(ScenarioSanction.owner_id == owner_id)
    if since is not None:
        query = query.where(ScenarioSanction.sanctioned_at > since)
    return await session.scalar(query) or 0
