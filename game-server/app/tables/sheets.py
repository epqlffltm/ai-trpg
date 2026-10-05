# game-server/app/tables/sheets.py

"""
테이블의 캐릭터 방식과 캐릭터 시트를 다루는 작은 함수들.

DB 를 모른다. 이미 읽어 온 테이블과 판을 받아 판단하고, 객체를 만든다.
예외를 던지지 않는다. 안 되는 경우는 None 이나 False 로 알리고, 무슨 오류로 답할지는 서비스가 정한다.

흐름은 이렇다.
  1. 테이블을 만들 때: 방장이 고른 방식이 판이 허용한 것 안에 있는지 본다(narrow_modes).
  2. 캐릭터를 정할 때: 그 방식이 이 테이블에서 허용되는지 본다(mode_of).
  3. 게임을 시작할 때: 사람마다 판에서 시트를 찾아(find_source) 이 테이블의 시트로 만든다(hand_out).
"""

from app.assets.models import CharacterMode
from app.assets.scenarios.snapshot import Snapshot
from app.engine.sheet import Sheet
from app.tables.models import GameTable, TableMember, TableSheet


def narrow_modes(allowed: list[CharacterMode], chosen: list[CharacterMode] | None) -> list[CharacterMode] | None:
    """
    이 테이블에서 허용할 방식을 정한다. 방장이 고른 것 중에 판이 허용하지 않은 것이 있으면 None.

    방장이 고르지 않았으면 판이 허용한 그대로다. 방장은 좁힐 수만 있고 넓힐 수 없다.
    """
    if chosen is None:
        return list(allowed)
    if not set(chosen) <= set(allowed):
        return None
    return list(chosen)


def seats_by_pregens(snapshot: Snapshot, modes: list[CharacterMode]) -> int | None:
    """
    프리젠의 수 때문에 앉을 수 있는 사람의 수에 한도가 있으면 그 수를 돌려준다. 한도가 없으면 None.

    프리젠 하나는 한 사람만 고른다. 프리젠만 허용한 테이블은 프리젠의 수보다 많이 앉을 수 없다.
    """
    if modes == [CharacterMode.PREGEN]:
        return len(snapshot.pregens)
    return None


def mode_of(pregen_index: int | None) -> CharacterMode:
    """캐릭터를 정하는 요청이 어느 방식인지 본다. 프리젠을 골랐으면 프리젠, 아니면 직접 만들기다."""
    return CharacterMode.PREGEN if pregen_index is not None else CharacterMode.CUSTOM


def find_source(snapshot: Snapshot, member: TableMember) -> Sheet | None:
    """
    이 사람이 받을 시트를 판에서 찾는다. 받을 시트가 없으면 None.

    프리젠을 골랐으면 그 프리젠의 시트, 직접 만들었으면 판의 기본 시트다.
    캐릭터를 아직 정하지 않았거나, 직접 만들었는데 판에 기본 시트가 없으면 None 이다.
    """
    if member.character_name is None:
        return None
    if member.pregen_index is not None:
        return snapshot.pregens[member.pregen_index].sheet
    return snapshot.default_sheet


def new_sheet(source: Sheet) -> TableSheet:
    """판의 시트에서 이 테이블의 시트를 만든다. HP 는 가득 찬 채로 시작한다."""
    return TableSheet(abilities=dict(source.abilities), max_hp=source.max_hp, hp=source.max_hp)


def hand_out(table: GameTable, snapshot: Snapshot) -> bool:
    """
    앉은 사람 모두에게 시트를 준다. 받을 시트가 없는 사람이 하나라도 있으면 아무에게도 주지 않고 False.

    먼저 모두의 것을 찾고, 다 있을 때만 준다. 몇 사람만 받은 상태를 만들지 않는다.
    """
    sources = [find_source(snapshot, member) for member in table.members]
    if any(source is None for source in sources):
        return False
    for member, source in zip(table.members, sources, strict=True):
        member.sheet = new_sheet(source)
    return True
