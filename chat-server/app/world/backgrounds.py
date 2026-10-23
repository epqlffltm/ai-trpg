# chat-server/app/world/backgrounds.py

"""
지금 장소와 시간대의 배경 그림을 고른다. DB 를 모르는 순수 함수다(#668).

그 시간대의 배경이 있으면 그것, 없으면 그 장소의 기본 배경, 그것도 없으면 없다(None).
화면이 같은 규칙을 다시 짜지 않게 서버가 고른 것을 상태의 응답에 싣는다.
기본 배경의 색감만 바꿔 시간대를 보이는 연출은 화면의 일이다(설계의 "그림", 나중).
"""

import uuid

from app.assets.schemas import CharacterDocument
from app.world.clock import TimeOfDay
from app.world.moves import find_place


def background_of(document: CharacterDocument, place_id: str | None, time_of_day: TimeOfDay) -> uuid.UUID | None:
    """place_id 의 장소의 time_of_day 의 배경. 장소가 없으면 None."""
    place = find_place(document, place_id) if place_id else None
    if place is None:
        return None
    return place.backgrounds.get(time_of_day, place.image_id)
