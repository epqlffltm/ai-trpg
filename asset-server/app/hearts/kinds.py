# asset-server/app/hearts/kinds.py

"""관심을 두는 작품의 종류(#989). 종류마다 작품의 표, 판의 표, 관심의 표와 "주소로 열 수 있는가"의 조건이 다르다."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement
from sqlalchemy.orm import InstrumentedAttribute

from app.characters import repository as characters
from app.characters.models import Character, CharacterHeart, CharacterVersion
from app.ratings import Rating
from app.worlds import repository as worlds
from app.worlds.models import World, WorldHeart, WorldVersion


@dataclass(frozen=True)
class HeartKind:
    """작품의 종류 하나. opened 는 주소로 열 수 있는 조건이다(공개나 링크 공개, 숨기지 않음, 볼 수 있는 등급)."""

    work: Any
    version: Any
    heart: Any
    heart_work_id: InstrumentedAttribute
    latest_join: Callable[[], ColumnElement[bool]]
    opened: Callable[[Sequence[Rating]], ColumnElement[bool]]


CHARACTER_HEARTS = HeartKind(
    work=Character,
    version=CharacterVersion,
    heart=CharacterHeart,
    heart_work_id=CharacterHeart.character_id,
    latest_join=characters.latest_join,
    opened=characters.opened,
)

WORLD_HEARTS = HeartKind(
    work=World,
    version=WorldVersion,
    heart=WorldHeart,
    heart_work_id=WorldHeart.world_id,
    latest_join=worlds.latest_join,
    opened=worlds.opened,
)
