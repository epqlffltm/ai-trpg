# trpg-server/app/portraits/seats.py

"""
테이블에서 캐릭터 그림(#983)을 찾는다. DB 도 HTTP 도 모르는 순수 함수다.

  - 그림은 판의 프리젠에 붙어 있다(테이블의 content 의 pregens[].image_id). 테이블은 판의 사본을 들고 있다
  - 앉은 사람의 그림은 그 사람이 고른 프리젠의 그림이다. 직접 만든 캐릭터에는 그림이 없다
  - 테이블에서 내줄 수 있는 그림은 그 테이블의 판에 붙은 그림뿐이다. 다른 그림의 id 를 적어도 내주지 않는다
  - 판에는 로어 항목마다의 그림(pictures, #1163)도 붙는다. 장소의 배경, 인물의 그림, 사건의 컷신이다.
    응답에는 보일 때만 그 id 를 싣는다(아는 장소, 장면의 인물, 일어난 사건). 모르는 것의 그림은 id 를 알 길이 없다
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


def entry_pictures(content: dict) -> dict[uuid.UUID, uuid.UUID]:
    """판의 로어 항목마다의 그림(#1163). 항목 → 그림. 옛 판이면 비어 있다."""
    return {uuid.UUID(str(one['entry_id'])): uuid.UUID(str(one['image_id'])) for one in content.get('pictures') or []}


def picture_of(content: dict, entry_id: uuid.UUID | str | None) -> uuid.UUID | None:
    """그 항목의 그림. 항목이 없거나 그림이 없으면 None."""
    if entry_id is None:
        return None
    return entry_pictures(content).get(uuid.UUID(str(entry_id)))


def with_cutscene(content: dict, payload: dict) -> dict:
    """
    이벤트에 적을 내용에 그 사건 항목(entry_id)의 컷신(#1163)을 붙인다. 그림이 없으면 image_id 가 null 이다.

    사건이 일어났거나 퀘스트를 이룬 뒤에만 부른다. 그 전에는 그림의 id 가 나가지 않는다.
    """
    image = picture_of(content, payload.get('entry_id'))
    return {**payload, 'image_id': str(image) if image is not None else None}


def table_portraits(content: dict) -> set[uuid.UUID]:
    """그 테이블의 판에 붙은 그림들. 프리젠의 그림과 로어 항목마다의 그림이다."""
    pregens = {image for image in (image_of(pregen) for pregen in content.get('pregens') or []) if image is not None}
    return pregens | set(entry_pictures(content).values())


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
