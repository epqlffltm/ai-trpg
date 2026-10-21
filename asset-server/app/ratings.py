# asset-server/app/ratings.py

"""
이용 등급과, 누가 어느 등급을 보고 쓸 수 있는지(#59, #390). 등급을 가르는 곳은 여기 하나다.

게임 서버의 app/assets/ratings.py 와 같은 규칙이다. 토큰의 값(server_core 의 AccessClaims)만 보고 DB 를 모른다.
  - 성인용 내용을 볼 수 있는 사람(adult_content)과 운영자는 전체 이용가와 성인용을 본다.
  - 그 밖의 사람과 로그인하지 않은 사람은 전체 이용가만 본다.
나이와 성별로는 거르지 않는다(2026-10-21). 등급은 캐릭터를 만든 사람이 정한다.
"""

import enum
from collections.abc import Sequence

from fastapi import Request, status
from fastapi.responses import JSONResponse
from server_core.auth.tokens import AccessClaims


class Rating(enum.StrEnum):
    """이용 등급. 게임 서버와 같은 값이다."""

    ALL = 'all'
    ADULT = 'adult'


class AdultContentRequiredError(Exception):
    """
    성인용인데 성인용 내용을 볼 수 없는 사람이다. 403 이다.

    그것이 있다는 것을 이미 아는 경우(자기 캐릭터를 성인용으로 쓰려는 사람)에만 던진다.
    공개 목록과 소개에서는 던지지 않는다. 그쪽에서는 없는 것으로 보인다(404).
    """


def allowed_ratings(viewer: AccessClaims | None) -> list[Rating]:
    """이 사람이 보고 쓸 수 있는 등급. 로그인하지 않은 사람(None)은 전체 이용가만이다."""
    if viewer is not None and (viewer.adult_content or viewer.is_operator):
        return [Rating.ALL, Rating.ADULT]
    return [Rating.ALL]


def require_rating(rating: str, allowed: Sequence[Rating]) -> None:
    """그 등급이 allowed 에 없으면 AdultContentRequiredError."""
    if rating not in allowed:
        raise AdultContentRequiredError


async def handle_adult_content_required(request: Request, error: AdultContentRequiredError) -> JSONResponse:
    """
    성인용인데 볼 수 없는 사람이면 403 이다. 화면이 본인인증으로 안내하게 code 를 싣는다(게임 서버와 같다).

    앱에 한 번 등록한다(app/main.py).
    """
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={'detail': '성인 인증을 한 사람만 이용할 수 있습니다.', 'code': 'adult_content_required'},
    )
