# notification-server/app/follows/router.py

"""
제작자 팔로우의 API(#989). 인증 서버가 발급한 access 토큰으로 누구인지 안다(server_core/auth).

    GET    /api/v1/notification/me/follows                    내 팔로잉(최근에 한 것부터). limit, offset
    GET    /api/v1/notification/me/follows/{creator_id}       내가 팔로우하는지와 그 제작자의 팔로워 수
    PUT    /api/v1/notification/me/follows/{creator_id}       팔로우한다
    DELETE /api/v1/notification/me/follows/{creator_id}       팔로우를 끊는다
    GET    /api/v1/notification/creators/{creator_id}/followers   그 제작자의 팔로워 수. 로그인하지 않아도 된다

  - 팔로우하기와 끊기는 바뀐 뒤의 값({following, follower_count})을 200 으로 돌려준다. 몇 번 해도 같다
  - 자기 자신은 422(detail.code: follow_self), 상한을 넘으면 409(detail.code: follow_limit)다
  - 누가 하는지는 토큰에서만 정한다. 남의 팔로잉을 읽을 길이 없다(팔로워의 수만 누구나 본다)
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from server_core.auth.dependencies import CurrentUser
from server_core.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession

from app.follows import service
from app.follows.schemas import FollowerCount, FollowingPage, FollowState

router = APIRouter(prefix='/me/follows', tags=['follows'])
public_router = APIRouter(prefix='/creators', tags=['follows'])

Session = Annotated[AsyncSession, Depends(get_session)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]

FOLLOW_RESPONSES = {
    status.HTTP_409_CONFLICT: {'description': '팔로우할 수 있는 제작자의 수를 넘었다(follow_limit)'},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {'description': '자기 자신이다(follow_self)'},
}


def follow_limit(request: Request) -> int:
    """한 사람이 팔로우할 수 있는 제작자의 수(설정)."""
    return request.app.state.settings.follow_max_per_user


@router.get('', response_model=FollowingPage, status_code=status.HTTP_200_OK)
async def list_following(user: CurrentUser, session: Session, limit: Limit = 20, offset: Offset = 0) -> FollowingPage:
    """내가 팔로우한 제작자들. 최근에 팔로우한 것부터다. 이름은 화면이 인증 서버에 묻는다."""
    return await service.following_page(session, user.user_id, limit, offset)


@router.get('/{creator_id}', response_model=FollowState, status_code=status.HTTP_200_OK)
async def read_follow(creator_id: uuid.UUID, user: CurrentUser, session: Session) -> FollowState:
    """내가 그 제작자를 팔로우하는지와 그 제작자의 팔로워 수."""
    return await service.state_of(session, user.user_id, creator_id)


@router.put('/{creator_id}', response_model=FollowState, status_code=status.HTTP_200_OK, responses=FOLLOW_RESPONSES)
async def follow(creator_id: uuid.UUID, user: CurrentUser, session: Session, request: Request) -> FollowState:
    """그 제작자를 팔로우한다. 이미 하고 있어도 200 이다."""
    try:
        return await service.follow(session, user.user_id, creator_id, follow_limit(request), datetime.now(UTC))
    except service.FollowSelfError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail={'code': 'follow_self'}) from error
    except service.FollowLimitError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail={'code': 'follow_limit'}) from error


@router.delete('/{creator_id}', response_model=FollowState, status_code=status.HTTP_200_OK)
async def unfollow(creator_id: uuid.UUID, user: CurrentUser, session: Session) -> FollowState:
    """팔로우를 끊는다. 하고 있지 않아도 200 이다."""
    return await service.unfollow(session, user.user_id, creator_id)


@public_router.get('/{creator_id}/followers', response_model=FollowerCount, status_code=status.HTTP_200_OK)
async def count_followers(creator_id: uuid.UUID, session: Session) -> FollowerCount:
    """그 제작자의 팔로워 수. 로그인하지 않아도 본다. 누가 팔로우하는지는 싣지 않는다."""
    return await service.followers_of(session, creator_id)
