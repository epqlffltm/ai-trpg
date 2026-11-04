# notification-server/app/follows/schemas.py

"""제작자 팔로우(#989)의 응답 모양."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class FollowState(BaseModel):
    """내가 그 제작자를 팔로우하는지와 그 제작자의 팔로워 수. 팔로우하고 끊은 뒤의 값이다."""

    following: bool
    follower_count: int


class FollowerCount(BaseModel):
    """그 제작자의 팔로워 수. 누구나 본다."""

    follower_count: int


class Followed(BaseModel):
    """내가 팔로우한 제작자 하나. 이름은 화면이 인증 서버에 묻는다."""

    creator_id: uuid.UUID
    followed_at: datetime


class FollowingPage(BaseModel):
    """내 팔로잉의 한 쪽과 전체 수. 최근에 팔로우한 것부터다."""

    items: list[Followed]
    total: int
