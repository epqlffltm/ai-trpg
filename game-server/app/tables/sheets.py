# game-server/app/tables/sheets.py

"""
테이블의 캐릭터 방식과 캐릭터 시트를 다루는 작은 함수들.

DB 를 모른다. 이미 읽어 온 테이블과 판을 받아 판단하고, 객체를 만든다.
예외를 던지지 않는다. 안 되는 경우는 None 이나 False 로 알리고, 무슨 오류로 답할지는 서비스가 정한다.

흐름은 이렇다.
  1. 테이블을 만들 때: 방장이 고른 방식이 판이 허용한 것 안에 있는지 본다(narrow_modes).
  2. 캐릭터를 정할 때: 그 방식이 이 테이블에서 허용되는지 본다. 방식은 요청에 적혀 있다(app/tables/schemas.py).
  3. 게임을 시작할 때: 사람마다 받을 시트를 찾아(find_source) 이 테이블의 시트로 만든다(hand_out).

시트가 오는 곳은 셋이다.
  - 프리젠을 골랐으면 그 프리젠의 시트(제작자가 적은 숫자).
  - 플레이어가 능력치를 정했으면(직접 적기, 점수제) 그 점수로 만든 시트. 최대 HP 는 규칙으로 구한다
    (app/engine/creation.py). 어느 방식으로 정했든 시트를 만드는 법은 같다. 다른 것은 받을 때의 제한이다(obeys_mode).
  - 둘 다 아니면 판의 기본 시트(제작자가 적은 숫자).
"""

from app.assets.models import CharacterMode
from app.assets.scenarios.snapshot import Snapshot
from app.engine.creation import build_sheet
from app.engine.point_buy import affordable
from app.engine.ruleset import Ruleset
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


def obeys_mode(ruleset: Ruleset, mode: CharacterMode, abilities: dict[str, int]) -> bool:
    """
    이 능력치가 그 방식이 거는 제한을 지켰는가.

    점수제는 규칙의 총점 안에서 살 수 있는 점수여야 한다. 직접 적기는 거는 제한이 없다.
    규칙의 능력치와 점수 범위에 맞는지는 방식과 상관없다. 여기서 보지 않는다(app/engine/sheet.py 의 abilities_fit).
    """
    if mode == CharacterMode.POINT_BUY:
        return affordable(ruleset, abilities)
    return True


def build_player_made(snapshot: Snapshot, abilities: dict[str, int]) -> Sheet | None:
    """
    플레이어가 정한 능력치로 시트를 만든다. 판에 최대 HP 를 구하는 값이 없으면 None.

    그런 방식을 허용한 판에는 그 값이 반드시 있다(게시 조건). 없는 것은 있을 수 없는 일이라 None 으로 알린다.
    """
    hp = snapshot.player_made_hp
    if hp is None:
        return None
    return build_sheet(snapshot.rulebook.rules, abilities, hp.base, hp.cap)


def find_source(snapshot: Snapshot, member: TableMember) -> Sheet | None:
    """
    이 사람이 받을 시트를 찾는다. 받을 시트가 없으면 None.

    프리젠을 골랐으면 그 프리젠의 시트, 능력치를 직접 정했으면 그 점수로 만든 시트, 둘 다 아니면 판의 기본 시트다.
    캐릭터를 아직 정하지 않았거나, 기본 시트를 받을 사람인데 판에 기본 시트가 없으면 None 이다.
    """
    if member.character_name is None:
        return None
    if member.pregen_index is not None:
        return snapshot.pregens[member.pregen_index].sheet
    if member.abilities is not None:
        return build_player_made(snapshot, member.abilities)
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
