# asset-server/app/worlds/listings.py

"""
공개 세계관의 목록과 소개(story 의 D1, 첫 화면의 story 카드). 로그인하지 않아도 읽는다(OptionalUser).

공개이고 게시한 판이 있는 세계관의 마지막 판을 내준다. 보는 사람이 볼 수 있는 등급만이다(app/ratings.py).
캐릭터의 공개 목록(app/characters/listings.py)과 같은 규칙이다.
  - 로그인하지 않은 사람과 성인 확인을 하지 않은 사람은 전체 이용가만 본다.
  - 볼 수 없는 세계관은 없는 것과 같다(404). 403 이면 그런 세계관이 있다는 것이 드러난다.
토큰을 보냈는데 틀렸으면 401 이다(로그인하지 않은 것으로 넘기지 않는다, server_core 의 OptionalUser).

캐릭터와 달리 판의 문서를 통째로 내주지 않는다. 판에는 이벤트와 엔딩의 조건, 숨긴 인물이 들어 있다.
소개에 보여도 되는 것만 골라 싣는다(to_public_detail). 인물은 제작자가 고른 공개를 따른다:
보임은 이름과 그림, 실루엣은 둘 다 가리고, 숨김은 목록에서 뺀다.
"""

import uuid

from fastapi import APIRouter, status
from server_core.auth.dependencies import OptionalUser

from app.core.dependencies import Paging, Session
from app.worlds import service
from app.worlds.documents import CastDocument, WorldDocument
from app.worlds.models import Reveal, World, WorldVersion
from app.worlds.schemas import PublicCastMember, PublicWorldDetail, PublicWorldPage, PublicWorldSummary

router = APIRouter(prefix='/listings/worlds', tags=['listings'])


def to_public_summary(world: World, version: WorldVersion) -> PublicWorldSummary:
    """공개 목록의 한 줄. 마지막 판의 값이다(초안이 아니다)."""
    document = WorldDocument.model_validate(version.document)
    return PublicWorldSummary(
        id=world.id,
        version=version.number,
        name=document.name,
        tags=document.tags,
        rating=document.rating,
        image_id=document.image_id,
        deadline_days=document.deadline_days,
        published_at=version.created_at,
    )


def public_member(member: CastDocument) -> PublicCastMember | None:
    """소개에 보이는 인물. 숨김이면 None, 실루엣이면 이름과 그림을 가린다."""
    if member.reveal == Reveal.HIDDEN:
        return None
    shown = member.reveal == Reveal.SHOWN
    return PublicCastMember(
        id=member.id,
        reveal=member.reveal,
        name=member.character.name if shown else None,
        image_id=member.character.image_id if shown else None,
    )


def public_cast(document: WorldDocument) -> list[PublicCastMember]:
    """소개에 보이는 인물들. 판에 적힌 차례다."""
    members = (public_member(member) for member in document.cast)
    return [member for member in members if member is not None]


def to_public_detail(world: World, version: WorldVersion) -> PublicWorldDetail:
    """공개 세계관의 소개. 마지막 판에서 보여도 되는 것만 고른다."""
    document = WorldDocument.model_validate(version.document)
    return PublicWorldDetail(
        id=world.id,
        version=version.number,
        published_at=version.created_at,
        name=document.name,
        intro_html=document.intro_html,
        tags=document.tags,
        rating=document.rating,
        image_id=document.image_id,
        deadline_days=document.deadline_days,
        after_ending=document.after_ending,
        cast=public_cast(document),
        ending_count=sum(1 for ending in document.endings if ending.unlock),
    )


@router.get('', response_model=PublicWorldPage, status_code=status.HTTP_200_OK)
async def list_public(user: OptionalUser, session: Session, paging: Paging) -> PublicWorldPage:
    """공개 세계관의 목록. 최근에 게시한 것부터다."""
    rows, total = await service.list_public(session, user, paging.limit, paging.offset)
    return PublicWorldPage(items=[to_public_summary(world, version) for world, version in rows], total=total)


@router.get('/{world_id}', response_model=PublicWorldDetail, status_code=status.HTTP_200_OK)
async def read_public(world_id: uuid.UUID, user: OptionalUser, session: Session) -> PublicWorldDetail:
    """공개 세계관의 소개. 볼 수 없으면 404 다."""
    world, version = await service.get_public(session, user, world_id)
    return to_public_detail(world, version)
