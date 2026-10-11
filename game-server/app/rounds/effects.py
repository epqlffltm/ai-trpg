# game-server/app/rounds/effects.py

"""
닫히는 라운드의 판정이 함께 쓰는 것과, 바뀐 HP 를 선언의 outcome 에 적을 문서로 만드는 함수들.

판정(app/rounds/checks.py)과 치료(app/rounds/treatments.py)가 함께 쓴다. 둘이 서로를 가져오지 않게 여기 둔다.
DB 를 모른다. 저장하지 않는다.
"""

from dataclasses import dataclass

from app.engine.dice import Dice
from app.engine.health import Change
from app.engine.ruleset import Ruleset
from app.rounds import injuries as round_injuries
from app.rounds.cast import CastMember, condition_of
from app.tables.models import GameTable, TableMember


@dataclass(frozen=True)
class Judging:
    """
    닫히는 라운드의 판정에 함께 쓰는 것들. 테이블, 규칙, 주사위, 이번 장면의 인물, 라운드의 번호.

    판정 하나와 그 결과(HP, NPC 의 상태, 부상)를 정하는 함수들이 이것을 함께 받는다.
    """

    table: GameTable
    ruleset: Ruleset
    dice: Dice
    cast: list[CastMember]
    round_number: int


def injury_after(judging: Judging, change: Change, max_hp: int, dead: bool, rows: list) -> dict | None:
    """
    피해 뒤에 부상 표를 굴릴 일이면 굴리고, 나온 부상을 입힌다. 굴린 것을 문서로 돌려준다. 굴리지 않았으면 None.

    rows 는 입는 쪽(시트나 NPC 상태)의 부상 목록이다.
    """
    rolled = round_injuries.roll_after(judging.ruleset, judging.dice, change, max_hp, dead)
    if rolled is None:
        return None
    return round_injuries.take(judging.ruleset, rolled, rows, judging.table.id, judging.round_number)


def member_effect(affected: TableMember, magnitude: str, change: Change, injury_roll: dict | None) -> dict:
    """
    앉은 사람의 HP 가 바뀐 것을 선언의 outcome 에 넣을 문서로. 누구의 HP 가 얼마에서 얼마로 바뀌었는지가 다 담긴다.

    injury_roll 은 그 피해로 부상 표를 굴린 것이다. 굴리지 않았으면 None.
    """
    return {
        'kind': change.kind.value,
        'magnitude': magnitude,
        'user_id': str(affected.user_id),
        'character_name': affected.character_name,
        'rolls': list(change.rolls),
        'amount': change.amount,
        'before': change.before,
        'after': change.after,
        'max_hp': affected.sheet.max_hp,
        'downed': change.downed,
        'injury_roll': injury_roll,
    }


def npc_effect(
    member: CastMember, magnitude: str, change: Change, lethal: bool, status_before: str, injury_roll: dict | None
) -> dict:
    """
    NPC 의 상태가 바뀐 것을 선언의 outcome 에 넣을 문서로.

    HP 의 숫자까지 다 적는다. 앉은 사람에게 내보낼 때 숫자를 뺀다(app/rounds/schemas.py, 이벤트의 VISIBLE).
    몸 상태(condition)는 부상까지 정한 뒤의 것이다.
    """
    npc = member.npc
    return {
        'kind': change.kind.value,
        'magnitude': magnitude,
        'entry_id': str(member.entry_id),
        'name': member.name,
        'rolls': list(change.rolls),
        'amount': change.amount,
        'before': change.before,
        'after': change.after,
        'max_hp': npc.max_hp,
        'lethal': lethal,
        'status_before': status_before,
        'status': npc.status,
        'condition': condition_of(npc),
        'injury_roll': injury_roll,
    }
