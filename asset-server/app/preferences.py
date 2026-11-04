# asset-server/app/preferences.py

"""
보는 사람이 공개 목록을 거르는 설정(#986, #987). 성인 작품 숨김과 성향이다. DB 를 모르는 순수한 모양이다.

설정은 인증 서버의 내 정보에 있다. 이 서버는 인증 서버를 부르지 않는다(공용 코드 규칙의 원칙 2).
화면이 읽어 공개 목록의 주소에 싣는다(?hide_adult=true&orientation=male). 소개 하나를 여는 주소에는 쓰지 않는다(목록만).
시나리오의 공개 목록(trpg-server 의 app/listings)도 같은 규칙이다.
"""

import enum
from collections.abc import Sequence
from dataclasses import dataclass

from app.ratings import Rating


class Orientation(enum.StrEnum):
    """목록을 거르는 성향."""

    MALE = 'male'
    FEMALE = 'female'


# 성향마다 거르는 태그. 제작자가 이 태그를 적는다. trpg-server 의 app/listings/models.py 와 같다
ORIENTATION_TAGS = {Orientation.MALE: '남성향', Orientation.FEMALE: '여성향'}


@dataclass(frozen=True)
class Preferences:
    """
    목록을 거르는 보는 사람의 설정.

    hide_adult 는 성인 작품을 숨길지다. 볼 수 있는 사람이 숨기는 설정이다. 볼 수 없는 사람에게는 이미 없다.
    orientation 을 고르면 그 태그가 붙은 것만 나온다("그것만", 먼저 보이기가 아니다).
    """

    hide_adult: bool = False
    orientation: Orientation | None = None

    @property
    def orientation_tag(self) -> str | None:
        """거를 태그. 고르지 않았으면 None."""
        return None if self.orientation is None else ORIENTATION_TAGS[self.orientation]


def shown_ratings(ratings: Sequence[Rating], preferences: Preferences) -> list[Rating]:
    """보는 사람이 볼 수 있는 등급에서 설정이 숨기는 것을 뺀다."""
    return [rating for rating in ratings if not (preferences.hide_adult and rating == Rating.ADULT)]
