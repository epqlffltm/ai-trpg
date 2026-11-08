# trpg-server/app/portraits/repository.py

"""
캐릭터 그림의 기록을 넣고 찾고 지운다. 저장(commit)은 서비스가 한다.

그림을 지울 때와 프리젠에 붙일 때가 겹치지 않게 기록의 행을 잠근다.
  - 붙일 때(시나리오 저장): 나눠 잠근다(FOR SHARE). 여럿이 함께 붙여도 서로 기다리지 않는다
  - 지울 때: 혼자 잠근다(FOR UPDATE). 붙이는 저장이 끝날 때까지 기다리고, 지우는 동안 새로 붙지 못한다
"""

import uuid

from sqlalchemy import delete, func, or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset, Scenario, ScenarioVersion
from app.calendar.clock import TimeOfDay
from app.listings.models import Listing
from app.portraits.models import Portrait


async def count_owned(session: AsyncSession, owner_id: uuid.UUID) -> int:
    """이 사람이 올린 그림의 수."""
    total = await session.scalar(select(func.count()).select_from(Portrait).where(Portrait.owner_id == owner_id))
    return total or 0


def add(session: AsyncSession, image_id: uuid.UUID, owner_id: uuid.UUID) -> Portrait:
    """기록 하나를 넣는다."""
    portrait = Portrait(id=image_id, owner_id=owner_id)
    session.add(portrait)
    return portrait


async def list_owned(session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int) -> tuple[list[Portrait], int]:
    """이 사람이 올린 그림들의 한 쪽과 전체 개수. 최근에 올린 것부터다."""
    query = select(Portrait).where(Portrait.owner_id == owner_id)
    page = query.order_by(Portrait.created_at.desc(), Portrait.id.desc()).limit(limit).offset(offset)
    rows = await session.scalars(page)
    return list(rows), await count_owned(session, owner_id)


async def owned_ids(session: AsyncSession, owner_id: uuid.UUID, image_ids: set[uuid.UUID]) -> set[uuid.UUID]:
    """그 id 들 가운데 이 사람이 올린 그림의 id 들. 찾은 행은 트랜잭션이 끝날 때까지 나눠 잠근다(지우지 못하게)."""
    if not image_ids:
        return set()
    query = select(Portrait.id).where(Portrait.owner_id == owner_id, Portrait.id.in_(image_ids))
    return set(await session.scalars(query.with_for_update(read=True)))


async def find_owned(session: AsyncSession, owner_id: uuid.UUID, image_id: uuid.UUID) -> Portrait | None:
    """이 사람이 올린 그림 하나. 남의 것이나 없는 것이면 None."""
    query = select(Portrait).where(Portrait.id == image_id, Portrait.owner_id == owner_id)
    return await session.scalar(query)


async def lock_owned(session: AsyncSession, owner_id: uuid.UUID, image_id: uuid.UUID) -> Portrait | None:
    """이 사람이 올린 그림 하나를 혼자 잠그고 돌려준다. 남의 것이나 없는 것이면 None."""
    query = select(Portrait).where(Portrait.id == image_id, Portrait.owner_id == owner_id).with_for_update()
    return await session.scalar(query)


def pregens_with(image_id: uuid.UUID) -> list[dict]:
    """JSONB 의 포함(@>)으로 찾을 모양. 목록(프리젠, 로어 항목마다의 그림)에 그 그림을 붙인 줄이 있다."""
    return [{'image_id': str(image_id)}]


def timed_with(image_id: uuid.UUID) -> list[list[dict]]:
    """JSONB 의 포함으로 찾을 모양들. 로어 항목마다의 그림에 하루의 때 하나의 그림으로 그 그림을 붙인 줄이 있다."""
    return [[{'by_time': {part.value: str(image_id)}}] for part in TimeOfDay]


def pictures_use(column, image_id: uuid.UUID):
    """그림들의 JSONB 칸(시나리오의 pictures, 판의 pictures)이 그 그림을 쓰는가. 기본 그림이거나 때마다의 그림이다."""
    return or_(column.contains(pregens_with(image_id)), *(column.contains(one) for one in timed_with(image_id)))


async def using_scenarios(session: AsyncSession, image_id: uuid.UUID) -> list[tuple[uuid.UUID, str]]:
    """
    그 그림을 쓰는 시나리오들의 (id, 제목). 지우지 않은 초안의 프리젠이나 게시한 판의 프리젠에 붙어 있으면 쓴다.

    판은 시나리오를 지워도 남는다(테이블이 그 판으로 돈다). 그래서 지운 시나리오라도 판이 쓰면 넣는다.
    테이블은 판의 사본을 들고 있고 판은 지우지 않으므로, 판을 보면 테이블이 쓰는 그림도 찾는다.
    공개 정보의 표지(#1164)로 쓰는 것도 넣는다. 공개 정보는 시나리오의 행을 지울 때만 함께 지워지므로
    지운 시나리오의 것이라도 넣는다(넣지 않으면 기록을 지울 때 FK 가 막는다).
    로어 항목마다의 그림(pictures, #1163)도 프리젠과 같이 초안과 판에서 찾는다.
    """
    wanted = pregens_with(image_id)
    drafts = (
        select(Scenario.asset_id.label('scenario_id'))
        .join(Asset, Asset.id == Scenario.asset_id)
        .where(
            Asset.deleted_at.is_(None),
            or_(Scenario.pregens.contains(wanted), pictures_use(Scenario.pictures, image_id)),
        )
    )
    versions = select(ScenarioVersion.scenario_id.label('scenario_id')).where(
        or_(
            ScenarioVersion.snapshot['pregens'].contains(wanted),
            pictures_use(ScenarioVersion.snapshot['pictures'], image_id),
        )
    )
    covers = select(Listing.scenario_id.label('scenario_id')).where(Listing.cover_image_id == image_id)
    used = union(drafts, versions, covers).subquery()
    query = select(Asset.id, Asset.title).join(used, used.c.scenario_id == Asset.id).order_by(Asset.title, Asset.id)
    return [(row.id, row.title) for row in await session.execute(query)]


async def delete_portrait(session: AsyncSession, image_id: uuid.UUID) -> None:
    """기록 하나를 지운다."""
    await session.execute(delete(Portrait).where(Portrait.id == image_id))
