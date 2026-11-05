# trpg-server/app/portraits/seats.py

"""
테이블에서 캐릭터 그림(#983)을 찾는다. DB 도 HTTP 도 모르는 순수 함수다.

  - 그림은 판의 프리젠에 붙어 있다(테이블의 content 의 pregens[].image_id). 테이블은 판의 사본을 들고 있다
  - 앉은 사람의 그림은 그 사람이 고른 프리젠의 그림이다. 직접 만든 캐릭터에는 그림이 없다
  - 테이블에서 내줄 수 있는 그림은 그 테이블의 판에 붙은 그림뿐이다. 다른 그림의 id 를 적어도 내주지 않는다
"""

import uuid
from collections.abc import Iterable

from app.tables.models import GameTable, TableMember

# 장면 그림에 넘기는 인물 그림의 수. Nano Banana 2.1 이 한 요청에 받는 인물 그림의 수다
MAX_CHARACTER_REFERENCES = 4


def image_of(pregen: dict) -> uuid.UUID | None:
    """프리젠 하나의 그림. 없거나 옛 판이면 None."""
    value = pregen.get('image_id')
    return uuid.UUID(str(value)) if value else None


def pregen_portrait(content: dict, pregen_index: int | None) -> uuid.UUID | None:
    """그 번호의 프리젠의 그림. 프리젠을 고르지 않았거나 그림이 없으면 None."""
    pregens = content.get('pregens') or []
    if pregen_index is None or not 0 <= pregen_index < len(pregens):
        return None
    return image_of(pregens[pregen_index])


def table_portraits(content: dict) -> set[uuid.UUID]:
    """그 테이블의 판에 붙은 그림들."""
    return {image for image in (image_of(pregen) for pregen in content.get('pregens') or []) if image is not None}


def member_portrait(table: GameTable, member: TableMember) -> uuid.UUID | None:
    """앉은 사람의 캐릭터 그림. 고른 프리젠의 그림이다."""
    return pregen_portrait(table.content, member.pregen_index)


def character_portraits(table: GameTable, members: Iterable[TableMember]) -> list[tuple[str, uuid.UUID]]:
    """이름이 있고 그림이 있는 캐릭터들의 (이름, 그림). 앉은 차례대로, 넘길 수 있는 수까지."""
    found = [
        (member.character_name.strip(), image)
        for member in members
        if member.character_name and (image := member_portrait(table, member)) is not None
    ]
    return found[:MAX_CHARACTER_REFERENCES]
