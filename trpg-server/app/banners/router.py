# trpg-server/app/banners/router.py

"""
홍보 배너 API(#994). 주소가 두 갈래다.
  - GET /banners: 누구나 지금 걸린 배너를 본다. 로그인하지 않아도 전체 이용가는 본다(공개 목록과 같다, #530).
    공개 목록처럼 hide_adult(#986), orientation(#987)으로 거른다
  - /admin/banners: 운영자가 걸고, 차례와 기간을 고치고, 내린다.
    운영자가 아니면 404 다(운영자의 주소가 있다는 것을 알리지 않는다)
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from server_core.auth.dependencies import OptionalUser

from app.assets.routing import Session
from app.banners import service
from app.banners.schemas import BannerCreate, BannerOut, BannerUpdate, PublicBanner, PublicBannerList
from app.banners.service import BannerNotFoundError, BannerView, ScenarioNotPublishedError
from app.listings.repository import ListingFilter
from app.listings.router import HideAdultFilter, OrientationFilter, to_public
from app.operators.router import Operator

public_router = APIRouter(prefix='/banners', tags=['banners'])
admin_router = APIRouter(prefix='/admin/banners', tags=['operators'])


def utc_now() -> datetime:
    """서버의 지금 시각(UTC)."""
    return datetime.now(UTC)


def to_out(view: BannerView) -> BannerOut:
    """운영자에게 보이는 응답으로 바꾼다."""
    banner = view.banner
    return BannerOut(
        id=banner.id,
        scenario_id=banner.scenario_id,
        title=view.title,
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
async def list_banners(
    user: OptionalUser, session: Session, hide_adult: HideAdultFilter = False, orientation: OrientationFilter = None
) -> PublicBannerList:
    """
    지금 걸린 배너. 차례대로다. 공개를 내렸거나 지운 시나리오, 링크로만 여는 것, 볼 수 없는 등급은 빠진다.

    공개 목록처럼 성인 작품을 숨기거나(hide_adult) 성향(orientation)의 태그가 붙은 것만 낸다.
    """
    where = ListingFilter(hide_adult=hide_adult, orientation=orientation)
    rows = await service.list_shown(session, user, where, utc_now())
    return PublicBannerList(items=[PublicBanner(id=banner.id, listing=to_public(*row)) for banner, row in rows])


@admin_router.get('', response_model=list[BannerOut], status_code=status.HTTP_200_OK)
async def list_all_banners(operator: Operator, session: Session) -> list[BannerOut]:
    """모든 배너(지난 것까지)와 지금 보이는지. 차례대로다."""
    return [to_out(view) for view in await service.list_for_operator(session, utc_now())]


@admin_router.post(
    '',
    response_model=BannerOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {'description': '공개 중인 시나리오가 아니다(code: not_published)'}},
)
async def create_banner(data: BannerCreate, operator: Operator, session: Session) -> BannerOut | JSONResponse:
    """공개 중인 시나리오의 배너를 건다. 공개 중이 아니면 409 not_published, 끝이 지금보다 앞이면 422 다."""
    try:
        view = await service.create_banner(session, operator.user_id, data, utc_now())
    except ScenarioNotPublishedError:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={'detail': '공개 중인 시나리오만 걸 수 있습니다.', 'code': 'not_published'},
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
