# game-server/app/rounds/injuries.py

"""
라운드가 닫힐 때 부상을 다루는 작은 함수들. 판정에 주는 영향, 피해 뒤의 부상 표, 짧은 부상이 풀리기.

부상의 계산은 엔진(app/engine/injury.py)이, 부상의 기록을 고치는 것은 app/tables/injuries.py 가 한다.
여기는 그 둘을 라운드의 모양(선언의 outcome 에 넣을 문서, 서술자에게 줄 모양)으로 잇는다.
DB 를 모른다. 이미 읽어 온 시트, NPC 상태, 규칙을 받는다. 저장과 이벤트는 부른 쪽(app/rounds/service.py)이 한다.
"""

import uuid
from dataclasses import dataclass

from app.engine import injury as injury_rules
from app.engine.check import HinderedCheck
from app.engine.dice import Dice
from app.engine.health import Change
from app.engine.injury import Hindrance, TableRoll, Trigger
from app.engine.ruleset import Injury, Ruleset
from app.rounds.cast import Scene, find_cast_member
from app.rounds.narrator import InjuryNote
from app.tables import injuries
from app.tables.models import InjurySource, TableInjury, TableMember


def worn(ruleset: Ruleset, rows: list[TableInjury]) -> list[Injury]:
    """입고 있는 부상들을 규칙의 부상으로. 생긴 순서다."""
    return injury_rules.known_injuries(ruleset, injuries.active_keys(rows))


def hindrance_for(ruleset: Ruleset, rows: list[TableInjury], ability: str) -> Hindrance:
    """입고 있는 부상들이 이 능력의 판정에 주는 것."""
    return injury_rules.hindrance_of(worn(ruleset, rows), ability)


def is_incapacitated(ruleset: Ruleset, rows: list[TableInjury]) -> bool:
    """입고 있는 부상 때문에 행동을 붙일 수 없는가(기절 같은 것)."""
    return injury_rules.blocks_actions(worn(ruleset, rows))


def hindrance_document(hindered: HinderedCheck) -> dict | None:
    """
    부상이 판정에 준 것을 선언의 outcome 에 넣을 문서로. 영향이 없었으면 None.

    굴린 눈들(불리하면 둘)을 함께 적는다. 판정의 눈(roll)은 그중 쓴 것이다.
    """
    hindrance = hindered.hindrance
    if not hindrance.any:
        return None
    return {
        'injuries': list(hindrance.injuries),
        'penalty': hindrance.penalty,
        'disadvantage': hindrance.disadvantage,
        'rolls': list(hindered.rolls),
    }


def roll_after(ruleset: Ruleset, dice: Dice, change: Change, max_hp: int, dead: bool) -> TableRoll | None:
    """피해 뒤에 부상 표를 굴릴 일이면 굴린다. 굴리지 않으면 None. 규칙에 표가 없으면 굴리지 않는다."""
    trigger = injury_rules.trigger_of(ruleset, change, max_hp, dead)
    if trigger is None or ruleset.injury_table is None:
        return None
    return injury_rules.roll_table(ruleset.injury_table, trigger, dice)


def wears(rows: list[TableInjury], key: str) -> bool:
    """이 부상을 지금 입고 있는가."""
    return key in injuries.active_keys(rows)


def injury_document(trigger: Trigger, roll: int | None) -> dict:
    """
    부상이 생긴 일을 HP 의 변화를 적은 문서 안에 넣을 모양. 아직 부상은 비어 있다.

    trigger 는 까닭(큰 타격, 쓰러짐, 노려 치기)이고, roll 은 부상 표의 눈이다. 노려 쳤으면 굴리지 않아서 None 이다.
    """
    return {'trigger': trigger.value, 'roll': roll, 'injury': None, 'name': None, 'ends_after_round': None}


def wound(
    ruleset: Ruleset,
    key: str,
    source: InjurySource,
    document: dict,
    rows: list[TableInjury],
    table_id: uuid.UUID,
    round_number: int,
) -> dict:
    """부상 하나를 입히고, 문서에 무엇이 생겼는지 채워 돌려준다. 규칙에 없는 부상이면 문서를 그대로 돌려준다."""
    definition = injury_rules.find_injury(ruleset, key)
    if definition is None:
        return document
    ends = injury_rules.ends_after(definition, round_number)
    injuries.inflict(rows, table_id, definition.key, source, round_number, ends)
    return {**document, 'injury': definition.key, 'name': definition.name, 'ends_after_round': ends}


def take(ruleset: Ruleset, rolled: TableRoll, rows: list[TableInjury], table_id: uuid.UUID, round_number: int) -> dict:
    """
    부상 표의 결과를 받아들인다. 부상이 나왔으면 입히고, 굴린 것을 문서로 돌려준다.

    rows 는 입는 쪽(시트나 NPC 상태)의 부상 목록이다. 문서는 HP 의 변화를 적은 문서 안에 들어간다.
    부상이 없는 줄이 나왔어도 굴린 것은 적는다. 큰 타격을 받고도 운 좋게 멀쩡했다는 기록이다.
    """
    document = injury_document(rolled.trigger, rolled.roll)
    if rolled.injury is None:
        return document
    return wound(ruleset, rolled.injury, InjurySource.INJURY_TABLE, document, rows, table_id, round_number)


def take_aimed(ruleset: Ruleset, key: str, rows: list[TableInjury], table_id: uuid.UUID, round_number: int) -> dict:
    """
    노려 친 부상을 입힌다. 문서로 돌려준다. 표를 굴리지 않는다.

    이미 그 부상을 입고 있으면 또 입히지 않는다(같은 라운드에 둘이 같은 눈을 노렸다). 문서의 부상이 비어 있다.
    """
    document = injury_document(Trigger.CALLED_SHOT, None)
    if wears(rows, key):
        return document
    return wound(ruleset, key, InjurySource.CALLED_SHOT, document, rows, table_id, round_number)


def called_shot_document(ruleset: Ruleset, aim: str | None) -> dict | None:
    """
    노려 치기를 선언의 outcome 에 넣을 문서로. 노려 치지 않았으면 None.

    무엇을 노렸는지와 판정이 얼마나 어려워졌는지(규칙의 방식과 양)다. 판정의 target 은 이미 오른 값이다.
    """
    if aim is None or ruleset.called_shot is None:
        return None
    return {'aim': aim, 'mode': ruleset.called_shot.mode.value, 'amount': ruleset.called_shot.amount}


def notes(ruleset: Ruleset, rows: list[TableInjury]) -> list[InjuryNote]:
    """입고 있는 부상들을 서술자에게 줄 모양으로. 이름과 사실이다."""
    return [InjuryNote(name=injury.name, fact=injury.fact) for injury in worn(ruleset, rows)]


@dataclass(frozen=True)
class Ended:
    """이 라운드가 닫힐 때 풀린 부상 하나와, 누가 입고 있었는지(이벤트에 적을 칸들)."""

    holder: dict
    injury: TableInjury


def expire_all(members: list[TableMember], scene: Scene, round_number: int) -> list[Ended]:
    """
    이 라운드가 닫힐 때 풀릴 짧은 부상을 모두 푼다. 앉은 사람의 지금 캐릭터와 테이블의 NPC 전부다.

    풀린 것과 누가 입고 있었는지를 돌려준다. 이벤트에 적을 것이다.
    장면에 나오지 않은 NPC 의 부상도 풀지만 돌려주지 않는다. 이벤트는 앉은 사람 모두가 읽는데,
    그 인물을 부를 이름(장면의 호칭)이 없다. 푼 것은 부상의 기록(ended_at)에 남는다.
    """
    ended: list[Ended] = []
    for member in members:
        if member.sheet is None:
            continue
        holder = {'user_id': str(member.user_id), 'character_name': member.character_name}
        ended.extend(Ended(holder, row) for row in injuries.expire(member.sheet.injuries, round_number))
    for npc in scene.npcs:
        rows = injuries.expire(npc.injuries, round_number)
        seen = find_cast_member(scene.cast, npc.entry_id)
        if seen is not None:
            holder = {'entry_id': str(npc.entry_id), 'name': seen.name}
            ended.extend(Ended(holder, row) for row in rows)
    return ended
