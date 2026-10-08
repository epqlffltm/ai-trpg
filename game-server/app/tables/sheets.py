# game-server/app/tables/sheets.py

"""
테이블의 캐릭터 방식과 캐릭터 시트를 다루는 작은 함수들.

DB 를 모른다. 이미 읽어 온 테이블과 판을 받아 판단하고, 객체를 만든다.
예외를 던지지 않는다. 안 되는 경우는 None 이나 False 로 알리고, 무슨 오류로 답할지는 서비스가 정한다.

흐름은 이렇다.
  1. 테이블을 만들 때: 방장이 고른 방식이 판이 허용한 것 안에 있는지 본다(narrow_modes).
  2. 캐릭터를 정할 때: 그 방식이 이 테이블에서 허용되는지 본다. 방식은 요청에 적혀 있다(app/tables/schemas.py).
  3. 게임을 시작할 때: 사람마다 받을 시트를 찾아(find_source) 이 테이블의 시트로 만든다(hand_out).
  4. 캐릭터가 죽어 새 캐릭터를 들일 때: 그 사람이 받을 시트를 찾아 하나 더 준다(give_sheet).
     앞의 시트는 지우지 않는다. 한 사람의 시트에는 번호가 붙는다(next_number).

시트가 오는 곳은 셋이다.
  - 프리젠을 골랐으면 그 프리젠의 시트(제작자가 적은 숫자).
  - 플레이어가 능력치를 정했으면(직접 적기, 점수제, 주사위) 그 점수로 만든 시트. 최대 HP 는 규칙으로 구한다
    (app/engine/creation.py). 어느 방식으로 정했든 시트를 만드는 법은 같다. 다른 것은 받을 때의 제한이다(obeys_mode).
  - 둘 다 아니면 판의 기본 시트(제작자가 적은 숫자).
"""

import uuid
from datetime import UTC, datetime

from app.assets.models import CharacterMode
from app.assets.scenarios.snapshot import Snapshot
from app.engine.creation import build_sheet
from app.engine.health import is_downed
from app.engine.point_buy import affordable
from app.engine.ruleset import Ruleset
from app.engine.score_roll import uses_exactly
from app.engine.sheet import Sheet
from app.tables.models import GameTable, TableMember, TableRoll, TableSheet


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


def find_roll(table: GameTable, user_id: uuid.UUID) -> TableRoll | None:
    """이 사람이 이 테이블에서 굴린 것을 찾는다. 굴린 적이 없으면 None."""
    return next((roll for roll in table.rolls if roll.user_id == user_id), None)


def next_number(member: TableMember) -> int:
    """
    이 사람이 다음에 받을 시트의 번호. 지금 정하고 있는 캐릭터가 이 사람의 몇 번째 캐릭터인가.

    시작 전에는 1 이다. 캐릭터가 죽어 새 캐릭터를 들일 때는 2, 그다음은 3 이다.
    """
    return len(member.sheets) + 1


def is_fresh(roll: TableRoll | None, member: TableMember) -> bool:
    """이 굴림이 지금 정하고 있는 캐릭터를 위해 굴린 것인가. 지난 캐릭터를 위해 굴린 것이면 아니다."""
    return roll is not None and roll.character_number == next_number(member)


def find_fresh_roll(table: GameTable, member: TableMember) -> TableRoll | None:
    """
    이 사람이 지금 정하고 있는 캐릭터를 위해 굴려 둔 것을 찾는다. 없으면 None.

    지난 캐릭터를 위해 굴린 것은 없는 것으로 본다. 그 점수로 새 캐릭터를 만들지 못한다.
    """
    roll = find_roll(table, member.user_id)
    return roll if is_fresh(roll, member) else None


def may_roll(roll: TableRoll | None, member: TableMember) -> bool:
    """
    지금 굴릴 수 있는가. 이 캐릭터를 위해 아직 굴리지 않았거나, 방장이 "한 번 더"를 줬을 때다.

    캐릭터 하나에 한 번 굴린다. 좋은 눈이 나올 때까지 굴릴 수 있으면 주사위의 뜻이 없다.
    """
    return not is_fresh(roll, member) or roll.reroll_granted


def obeys_mode(ruleset: Ruleset, mode: CharacterMode, abilities: dict[str, int], roll: TableRoll | None) -> bool:
    """
    이 능력치가 그 방식이 거는 제한을 지켰는가. roll 은 이 사람이 굴려 둔 것이다(없으면 None).

    점수제는 규칙의 총점 안에서 살 수 있는 점수여야 한다.
    주사위는 굴려 둔 점수를 남김없이 한 번씩 쓴 것이어야 한다. 굴린 적이 없으면 지킨 것이 아니다.
    직접 적기는 거는 제한이 없다.
    규칙의 능력치와 점수 범위에 맞는지는 방식과 상관없다. 여기서 보지 않는다(app/engine/sheet.py 의 abilities_fit).
    """
    if mode == CharacterMode.POINT_BUY:
        return affordable(ruleset, abilities)
    if mode == CharacterMode.ROLLED:
        return roll is not None and uses_exactly(roll.scores, abilities)
    return True


def clear_character(member: TableMember) -> None:
    """자리의 캐릭터를 지운다. 캐릭터를 정하기 전으로 돌아간다."""
    member.character_name = None
    member.character_description = ''
    member.character_mode = None
    member.pregen_index = None
    member.abilities = None


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
    return source_of(snapshot, member.pregen_index, member.abilities)


def source_of(snapshot: Snapshot, pregen_index: int | None, abilities: dict[str, int] | None) -> Sheet | None:
    """
    그렇게 정한 캐릭터가 받을 시트를 찾는다. 받을 시트가 없으면 None.

    자리에 적기 전에 물어볼 수 있게 자리가 아니라 값을 받는다. 받을 시트가 없는 캐릭터를 자리에 적지 않으려는 것이다.
    """
    if pregen_index is not None:
        return snapshot.pregens[pregen_index].sheet
    if abilities is not None:
        return build_player_made(snapshot, abilities)
    return snapshot.default_sheet


def give_sheet(member: TableMember, source: Sheet) -> TableSheet:
    """
    이 사람의 지금 캐릭터에게 시트를 준다. 준 시트를 돌려준다. HP 는 가득 찬 채로 시작한다.

    이 사람이 받은 시트들의 맨 뒤에 놓인다. 누구의 시트인지(이름, 프리젠)를 자리에서 복사해 둔다.
    앞의 캐릭터가 죽었는지는 보지 않는다. 부르는 쪽이 확인한다.
    """
    sheet = TableSheet(
        number=next_number(member),
        character_name=member.character_name,
        pregen_index=member.pregen_index,
        abilities=dict(source.abilities),
        max_hp=source.max_hp,
        hp=source.max_hp,
    )
    member.sheets.append(sheet)
    return sheet


def hand_out(table: GameTable, snapshot: Snapshot) -> bool:
    """
    앉은 사람 모두에게 시트를 준다. 받을 시트가 없는 사람이 하나라도 있으면 아무에게도 주지 않고 False.

    먼저 모두의 것을 찾고, 다 있을 때만 준다. 몇 사람만 받은 상태를 만들지 않는다.
    """
    sources = [find_source(snapshot, member) for member in table.members]
    if any(source is None for source in sources):
        return False
    for member, source in zip(table.members, sources, strict=True):
        give_sheet(member, source)
    return True


def pregen_has_sheet(table: GameTable, pregen_index: int) -> bool:
    """
    이 프리젠이 이 테이블에서 시트를 받은 적이 있는가. 그 캐릭터가 죽었어도, 누구의 캐릭터였어도 그렇다.

    시작 전에는 시트가 없으므로 늘 False 다.
    """
    return any(sheet.pregen_index == pregen_index for member in table.members for sheet in member.sheets)


def is_dead(member: TableMember) -> bool:
    """이 사람의 캐릭터가 죽었는가. 시트가 없으면(시작 전) 죽은 것이 아니다."""
    return member.sheet is not None and member.sheet.died_at is not None


def is_downed_alive(member: TableMember) -> bool:
    """이 사람의 캐릭터가 쓰러져 있지만 아직 죽지 않았는가. 죽음의 굴림을 굴리고, 스스로 보낼 수 있는 때다."""
    return member.sheet is not None and is_downed(member.sheet.hp) and member.sheet.died_at is None


def mark_dead(sheet: TableSheet) -> None:
    """캐릭터가 죽었다고 시트에 적는다. 되돌리는 함수는 없다."""
    sheet.died_at = datetime.now(UTC)


def clear_death_saves(sheet: TableSheet) -> None:
    """죽음의 굴림에서 센 것을 처음으로 돌린다. 회복을 받아 일어났을 때 부른다."""
    sheet.death_successes = 0
    sheet.death_failures = 0
