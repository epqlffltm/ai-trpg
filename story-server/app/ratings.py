# story-server/app/ratings.py

"""
이용 등급과, 누가 어느 등급을 보고 쓸 수 있는지. 거르는 곳은 여기 하나다.

asset 서버의 app/ratings.py, chat 서버, 게임 서버와 같은 규칙이다.
토큰의 값(server_core 의 AccessClaims)만 보고 DB 를 모른다.
  - 성인용 내용을 볼 수 있는 사람(adult_content)과 운영자는 전체 이용가와 성인용을 본다.
  - 그 밖의 사람은 전체 이용가만 본다.
세션 목록과 세션 하나를 읽을 때 거른다.
"""

import enum

from server_core.auth.tokens import AccessClaims


class Rating(enum.StrEnum):
    """이용 등급. asset 서버, chat 서버, 게임 서버와 같은 값이다."""

    ALL = 'all'
    ADULT = 'adult'


def allowed_ratings(viewer: AccessClaims) -> list[Rating]:
    """이 사람이 보고 쓸 수 있는 등급."""
    if viewer.adult_content or viewer.is_operator:
        return [Rating.ALL, Rating.ADULT]
    return [Rating.ALL]
