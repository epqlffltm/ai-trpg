# game-server/app/assets/routing.py

"""
자산 API 들이 함께 쓰는 것. 세션, 쪽 나누기, 목록용 응답, "없다"의 응답.

종류별 라우터(worlds/router.py 등)가 이것을 가져다 쓴다.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset, AssetContent
from app.assets.schemas import AssetPage, AssetSummary
from app.assets.service import AssetNotFoundError
from app.core.database import get_session

# 요청 하나가 쓰는 DB 세션
Session = Annotated[AsyncSession, Depends(get_session)]

# 목록의 한 쪽에 싣는 개수. 상한을 둔다. 한 번에 전부 달라는 요청으로 서버가 느려지지 않게 한다
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@dataclass
class PageParams:
    """목록을 어디서부터 몇 개 달라는 요청. 주소의 ?limit=..&offset=.. 에서 읽는다."""

    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE
    offset: Annotated[int, Query(ge=0)] = 0


# 목록 API 가 인자의 형식으로 쓴다
Paging = Annotated[PageParams, Depends()]


def to_summary(asset: Asset) -> AssetSummary:
    """자산의 공통 부분을 목록용 응답으로 바꾼다."""
    return AssetSummary(
        id=asset.id,
        title=asset.title,
        description=asset.description,
        rating=asset.rating,
        visibility=asset.visibility,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


def to_page(contents: list[AssetContent], total: int) -> AssetPage:
    """자산 여러 개를 목록의 한 쪽으로 바꾼다."""
    return AssetPage(items=[to_summary(content.asset) for content in contents], total=total)


async def handle_asset_not_found(request: Request, error: AssetNotFoundError) -> JSONResponse:
    """
    서비스가 "그런 자산이 없다"고 하면 404 로 답한다. 앱에 한 번 등록한다(app/main.py).

    남의 자산도 404 다. 403 을 주면 그 ID 의 자산이 있다는 것이 드러난다.
    """
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={'detail': '찾을 수 없습니다.'})
