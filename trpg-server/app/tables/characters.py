# trpg-server/app/tables/characters.py

"""
캐릭터를 정한다. 입력을 테이블과 견주어 보고, 받아들인 캐릭터를 자리에 적는다. 시작할 때의 명단을 만든다.

DB 를 모른다. 이미 읽어 온 테이블, 판, 자리를 받는다. 저장은 부른 쪽이 한다.
모집 중에 캐릭터를 정할 때(app/tables/service.py)와 진행 중에 새 캐릭터를 들일 때(app/tables/replacements.py)가
같은 검사(accept_character)를 쓴다. 다른 것은 언제 되느냐와, 받아들인 뒤에 무슨 일이 일어나느냐다.
캐릭터의 숫자(시트)는 게임을 시작할 때 준다(app/tables/sheets.py). 여기서는 무엇으로 시트를 만들지를 적어 둔다.
"""

from dataclasses import dataclass

from app.assets.models import CharacterMode
from app.assets.scenarios.snapshot import Snapshot
from app.engine.sheet import abilities_fit
from app.tables import sheets
from app.tables.errors import Conflict, TableConflictError, TableOptionError
from app.tables.models import GameTable, TableMember, TableRoll
from app.tables.schemas import CharacterUpdate


def require_pregen_free(table: GameTable, member: TableMember, pregen_index: int) -> None:
    """
    이 프리젠을 고를 수 있는지 확인한다. 못 고르면 TableConflictError.

    다른 사람이 가져갔으면 못 고른다.
    이 테이블에서 시트를 받은 적이 있는 프리젠도 못 고른다. 그 캐릭터가 죽었어도, 자기 캐릭터였어도 그렇다.
    죽은 인물이 다시 걸어 들어오지 못한다. 시작 전에는 시트가 없으므로 앞의 조건만 남는다.
    """
    others = [other for other in table.members if other is not member]
    if any(other.pregen_index == pregen_index for other in others):
        raise TableConflictError(Conflict.PREGEN_TAKEN)
    if sheets.pregen_has_sheet(table, pregen_index):
        raise TableConflictError(Conflict.PREGEN_TAKEN)


def resolve_character(snapshot: Snapshot, data: CharacterUpdate) -> tuple[str, str]:
    """
    입력에서 캐릭터의 이름과 설명을 정한다. 없는 프리젠을 골랐으면 TableOptionError.

    프리젠을 골랐으면 프리젠의 것이 바탕이고, 함께 보낸 칸은 보낸 것으로 고쳐 쓴다.
    """
    if data.pregen_index is None:
        return data.name, data.description or ''

    if data.pregen_index >= len(snapshot.pregens):
        raise TableOptionError('pregen_index')
    pregen = snapshot.pregens[data.pregen_index]
    name = data.name if data.name is not None else pregen.name
    description = data.description if data.description is not None else pregen.description
    return name, description


def accept_abilities(snapshot: Snapshot, data: CharacterUpdate, roll: TableRoll | None) -> dict[str, int] | None:
    """
    플레이어가 정한 능력치를 이 테이블의 규칙과 견주어 보고, 자리에 적을 값을 돌려준다. 능력치를 적지 않았으면 None.
    roll 은 이 사람이 지금 정하는 캐릭터를 위해 굴려 둔 것이다(app/tables/sheets.py 의 find_fresh_roll).

    규칙의 능력치가 빠짐없이 있어야 하고, 점수가 규칙의 범위 안이어야 한다. 아니면 TableOptionError.
    거기에 방식이 거는 제한을 지켜야 한다. 점수제는 총점 안이어야 하고, 주사위는 굴려 둔 점수를 그대로 써야 한다.
    직접 적기는 제한이 없다.
    무엇이 틀렸는지는 가르지 않는다. 총점과 값표, 굴린 점수는 응답에 있어서 보내기 전에 견주어 볼 수 있다.

    주사위 방식인데 아직 굴리지 않았으면 TableConflictError 다. 보낸 값이 틀린 것이 아니라 순서가 틀린 것이다.
    """
    if data.abilities is None:
        return None
    mode = data.chosen_mode
    if mode == CharacterMode.ROLLED and roll is None:
        raise TableConflictError(Conflict.NOT_ROLLED)
    ruleset = snapshot.rulebook.rules
    if not abilities_fit(ruleset, data.abilities) or not sheets.obeys_mode(ruleset, mode, data.abilities, roll):
        raise TableOptionError('abilities')
    return dict(data.abilities)


@dataclass(frozen=True)
class ChosenCharacter:
    """받아들인 캐릭터. 입력을 이 테이블과 견주어 본 뒤의 값이다. 자리에 그대로 적는다."""

    name: str
    description: str
    mode: CharacterMode
    pregen_index: int | None
    abilities: dict[str, int] | None


def accept_character(
    table: GameTable, snapshot: Snapshot, member: TableMember, data: CharacterUpdate
) -> ChosenCharacter:
    """
    캐릭터를 정하는 입력을 이 테이블과 견주어 보고, 자리에 적을 값을 돌려준다. 자리를 고치지는 않는다.

    이 테이블에서 허용하지 않는 방식이거나, 고를 수 없는 프리젠이거나,
    주사위 방식인데 이 캐릭터를 위해 아직 굴리지 않았으면 TableConflictError.
    없는 프리젠이거나, 직접 정한 능력치가 이 테이블의 규칙에 맞지 않으면 TableOptionError.

    모집 중에 캐릭터를 정할 때와 진행 중에 새 캐릭터를 들일 때(app/tables/replacements.py)가 함께 쓴다.
    받아들이는 조건은 같다. 다른 것은 언제 되느냐와, 받아들인 뒤에 무슨 일이 일어나느냐다.
    """
    if data.chosen_mode not in table.character_modes:
        raise TableConflictError(Conflict.CHARACTER_MODE_NOT_ALLOWED)
    name, description = resolve_character(snapshot, data)
    abilities = accept_abilities(snapshot, data, sheets.find_fresh_roll(table, member))
    if data.pregen_index is not None:
        require_pregen_free(table, member, data.pregen_index)
    return ChosenCharacter(
        name=name,
        description=description,
        mode=data.chosen_mode,
        pregen_index=data.pregen_index,
        abilities=abilities,
    )


def write_character(member: TableMember, chosen: ChosenCharacter) -> None:
    """받아들인 캐릭터를 자리에 적는다. 앞의 캐릭터가 있었으면 통째로 바뀐다."""
    member.character_name = chosen.name
    member.character_description = chosen.description
    member.character_mode = chosen.mode
    member.pregen_index = chosen.pregen_index
    member.abilities = chosen.abilities


def describe_sheet(member: TableMember) -> dict | None:
    """시작할 때의 시트를 이벤트에 적을 모양으로 바꾼다. 시트가 없으면 None."""
    if member.sheet is None:
        return None
    return {'abilities': member.sheet.abilities, 'max_hp': member.sheet.max_hp}


def roster(table: GameTable) -> list[dict]:
    """
    앉은 사람과 캐릭터 이름, 시작할 때의 시트의 목록. 이벤트에 적을 모양이다.

    시트를 함께 적어 둔다. 뒤에 HP 가 바뀐 일들이 이벤트로 쌓이므로, 처음의 값이 기록에 있어야 과정을 따라갈 수 있다.
    """
    return [
        {'user_id': str(member.user_id), 'character_name': member.character_name, 'sheet': describe_sheet(member)}
        for member in table.members
    ]
