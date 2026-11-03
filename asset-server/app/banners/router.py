# asset-server/app/banners/router.py

"""
홍보 배너 API(#994). 주소가 두 갈래다. 시나리오의 배너는 trpg-server 의 같은 주소에 있다.
  - GET /banners: 누구나 지금 걸린 캐릭터와 세계관의 배너를 본다. 로그인하지 않아도 전체 이용가는 본다(공개 목록과 같다)
  - /admin/banners: 운영자가 걸고, 차례와 기간을 고치고, 내린다.
    운영자가 아니면 404 다(운영자의 주소가 있다는 것을 알리지 않는다)
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from server_core.auth.dependencies import OptionalUser

from app.banners import service
from app.banners.schemas import BannerCreate, BannerOut, BannerUpdate, PublicBanner, PublicBannerList
from app.banners.service import BannerNotFoundError, BannerView, ShownBanner, TargetNotPublishedError
from app.characters.listings import to_public_summary as to_character_summary
from app.core.dependencies import Session
from app.operators.router import Operator
from app.worlds.listings import to_public_summary as to_world_summary

public_router = APIRouter(prefix='/banners', tags=['banners'])
admin_router = APIRouter(prefix='/admin/banners', tags=['admin'])


def utc_now() -> datetime:
    """서버의 지금 시각(UTC)."""
    return datetime.now(UTC)


def to_public(shown: ShownBanner) -> PublicBanner:
    """보는 사람에게 낼 응답으로 바꾼다. 공개 목록의 한 줄과 같은 모양이다."""
    banner = shown.banner
    return PublicBanner(
        id=banner.id,
        kind=banner.kind,
        character=to_character_summary(*shown.character) if shown.character else None,
        world=to_world_summary(*shown.world) if shown.world else None,
    )


def to_out(view: BannerView) -> BannerOut:
    """운영자에게 보이는 응답으로 바꾼다."""
    banner = view.banner
    return BannerOut(
        id=banner.id,
        kind=banner.kind,
        target_id=banner.target_id,
        name=view.name,
        position=banner.position,
        starts_at=banner.starts_at,
        ends_at=banner.ends_at,
        created_at=banner.created_at,
        shown=view.shown,
    )


def not_found() -> HTTPException:
    """없는 배너. 운영자의 주소라 다른 404 와 같은 글이다."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Not Found')


@public_router.get('', response_model=PublicBannerList, status_code=status.HTTP_200_OK)
async def list_banners(user: OptionalUser, session: Session) -> PublicBannerList:
    """지금 걸린 배너. 차례대로다. 비공개로 돌렸거나 숨긴 작품, 볼 수 없는 등급은 빠진다."""
    return PublicBannerList(items=[to_public(shown) for shown in await service.list_shown(session, user, utc_now())])


@admin_router.get('', response_model=list[BannerOut], status_code=status.HTTP_200_OK)
async def list_all_banners(operator: Operator, session: Session) -> list[BannerOut]:
    """모든 배너(지난 것까지)와 지금 보이는지. 차례대로다."""
    return [to_out(view) for view in await service.list_for_operator(session, utc_now())]


@admin_router.post(
    '',
    response_model=BannerOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {'description': '공개 목록에 나오는 작품이 아니다(code: not_published)'}},
)
async def create_banner(data: BannerCreate, operator: Operator, session: Session) -> BannerOut | JSONResponse:
    """공개 목록에 나오는 작품의 배너를 건다. 아니면 409 not_published, 끝이 지금보다 앞이면 422 다."""
    try:
        view = await service.create_banner(session, operator.user_id, data, utc_now())
    except TargetNotPublishedError:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={'detail': '공개 목록에 나오는 작품만 걸 수 있습니다.', 'code': 'not_published'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return to_out(view)


@admin_router.patch('/{banner_id}', response_model=BannerOut, status_code=status.HTTP_200_OK)
async def update_banner(banner_id: uuid.UUID, data: BannerUpdate, operator: Operator, session: Session) -> BannerOut:
    """배너의 차례와 기간을 고친다. 없으면 404, 기간이 거꾸로면 422 다."""
    try:
        return to_out(await service.update_banner(session, banner_id, data, utc_now()))
    except BannerNotFoundError as exc:
        raise not_found() from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@admin_router.delete('/{banner_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_banner(banner_id: uuid.UUID, operator: Operator, session: Session) -> None:
    """배너를 내린다. 없으면 404 다."""
    try:
        await service.delete_banner(session, banner_id)
    except BannerNotFoundError as exc:
        raise not_found() from exc
