# trpg-server/app/rounds/injuries.py

"""
라운드가 닫힐 때 부상을 다루는 작은 함수들. 판정에 주는 영향, 피해 뒤의 부상 표, 부상이 풀리거나 낫기, 후유증.

부상의 계산은 엔진(app/engine/injury.py)이, 부상의 기록을 고치는 것은 app/tables/injuries.py 가 한다.
여기는 그 둘을 라운드의 모양(선언의 outcome 에 넣을 문서, 서술자에게 줄 모양)으로 잇는다.
DB 를 모른다. 이미 읽어 온 시트, NPC 상태, 규칙을 받는다.
저장과 이벤트는 부른 쪽(app/rounds/service.py, records.py)이 한다.
"""

import enum
import uuid
from dataclasses import dataclass

from app.calendar import clock
from app.calendar import state as calendar
from app.engine import injury as injury_rules
from app.engine.check import HinderedCheck
from app.engine.dice import Dice
from app.engine.health import Change
from app.engine.injury import Hindrance, TableRoll, Trigger
from app.engine.ruleset import Healing, Injury, Ruleset
from app.rounds.cast import Scene, find_cast_member
from app.rounds.narrator import InjuryNote
from app.tables import injuries, npcs, sheets
from app.tables.injuries import Moment
from app.tables.models import GameTable, InjurySource, TableInjury, TableMember


def moment_of(table: GameTable, round_number: int) -> Moment:
    """
    닫히는 라운드의 때. 테이블의 시계에서 지금 시각과 이 장면이 끝나는 시각을 읽는다.

    라운드가 닫기 시작할 때 한 번 읽는다. 기다리기로 늘어난 걸음은 이미 들어 있다(app/rounds/waits.py).
    """
    return Moment(
        round_number=round_number,
        now=table.clock.minutes,
        scene_end=calendar.scene_end(table),
    )


def heals_at_document(minutes: int | None) -> dict | None:
    """나을 시각을 문서에 적을 모양(며칠째, 몇 시, 몇 분, 하루의 어느 때). 없으면 None."""
    return None if minutes is None else clock.as_document(minutes)


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
    return {
        'trigger': trigger.value,
        'roll': roll,
        'injury': None,
        'name': None,
        'ends_after_round': None,
        'heals_at': None,
    }


def wound(
    ruleset: Ruleset,
    key: str,
    source: InjurySource,
    document: dict,
    rows: list[TableInjury],
    table_id: uuid.UUID,
    moment: Moment,
) -> dict:
    """
    부상 하나를 입히고, 문서에 무엇이 생겼는지 채워 돌려준다. 규칙에 없는 부상이면 문서를 그대로 돌려준다.

    짧은 것은 풀릴 라운드, 오래 가는 것은 나을 시각이 적힌다. 결손은 둘 다 없다.
    """
    definition = injury_rules.find_injury(ruleset, key)
    if definition is None:
        return document
    ends = injury_rules.ends_after(definition, moment.round_number)
    heals = injury_rules.heals_at(definition, moment.now)
    injuries.inflict(rows, table_id, definition.key, source, moment.round_number, ends, heals)
    return {
        **document,
        'injury': definition.key,
        'name': definition.name,
        'ends_after_round': ends,
        'heals_at': heals_at_document(heals),
    }


def take(ruleset: Ruleset, rolled: TableRoll, rows: list[TableInjury], table_id: uuid.UUID, moment: Moment) -> dict:
    """
    부상 표의 결과를 받아들인다. 부상이 나왔으면 입히고, 굴린 것을 문서로 돌려준다.

    rows 는 입는 쪽(시트나 NPC 상태)의 부상 목록이다. 문서는 HP 의 변화를 적은 문서 안에 들어간다.
    부상이 없는 줄이 나왔어도 굴린 것은 적는다. 큰 타격을 받고도 운 좋게 멀쩡했다는 기록이다.
    """
    document = injury_document(rolled.trigger, rolled.roll)
    if rolled.injury is None:
        return document
    return wound(ruleset, rolled.injury, InjurySource.INJURY_TABLE, document, rows, table_id, moment)


def take_aimed(ruleset: Ruleset, key: str, rows: list[TableInjury], table_id: uuid.UUID, moment: Moment) -> dict:
    """
    노려 친 부상을 입힌다. 문서로 돌려준다. 표를 굴리지 않는다.

    이미 그 부상을 입고 있으면 또 입히지 않는다(같은 라운드에 둘이 같은 눈을 노렸다). 문서의 부상이 비어 있다.
    """
    document = injury_document(Trigger.CALLED_SHOT, None)
    if wears(rows, key):
        return document
    return wound(ruleset, key, InjurySource.CALLED_SHOT, document, rows, table_id, moment)


def take_aftermath(
    ruleset: Ruleset, rolled: TableRoll, rows: list[TableInjury], table_id: uuid.UUID, moment: Moment
) -> dict:
    """후유증 표의 결과를 받아들인다. 후유증이 나왔으면 입히고(결손이다), 굴린 것을 문서로 돌려준다."""
    document = injury_document(rolled.trigger, rolled.roll)
    if rolled.injury is None:
        return document
    return wound(ruleset, rolled.injury, InjurySource.AFTERMATH, document, rows, table_id, moment)


def aftermath_of(
    ruleset: Ruleset, dice: Dice, row: TableInjury, rows: list[TableInjury], table_id: uuid.UUID, moment: Moment
) -> dict | None:
    """
    나은 부상의 후유증 표를 굴리고, 나온 후유증을 입힌다. 굴린 것을 문서로 돌려준다. 굴리지 않았으면 None.

    오래 가는 부상 중 후유증 표가 있는 것만 굴린다. 규칙에 없는 부상이면(규칙이 바뀐 판) 굴리지 않는다.
    """
    definition = injury_rules.find_injury(ruleset, row.injury)
    if definition is None:
        return None
    rolled = injury_rules.roll_aftermath(definition, dice)
    if rolled is None:
        return None
    return take_aftermath(ruleset, rolled, rows, table_id, moment)


def heal(
    ruleset: Ruleset, dice: Dice, row: TableInjury, rows: list[TableInjury], table_id: uuid.UUID, moment: Moment
) -> dict | None:
    """
    오래 가는 부상을 지금 낫게 한다. 치료로 나을 시각이 이 장면이 끝나는 때에 닿았을 때 부른다. 후유증 문서를 돌려준다.

    부상을 끝내고, 후유증 표를 굴린다. 후유증 표가 없으면 깨끗이 나아서 None.
    """
    injuries.end(row)
    return aftermath_of(ruleset, dice, row, rows, table_id, moment)


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


class EndReason(enum.StrEnum):
    """부상이 끝난 까닭. 이벤트에 적는다."""

    # 짧은 것이 정한 라운드가 지나 풀렸다
    EXPIRED = 'expired'
    # 오래 가는 것이 나을 시각이 지나 나았다
    HEALED = 'healed'
    # 치료로 나을 시각이 앞당겨져 나았다
    TREATED = 'treated'
    # 소모품으로 풀었다(#277, 해독제)
    CURED = 'cured'


@dataclass(frozen=True)
class Ended:
    """
    이 라운드가 닫힐 때 끝난 부상 하나와, 누가 입고 있었는지(이벤트에 적을 칸들).

    reason 은 풀렸는지(expired) 나았는지(healed)다. 나았으면 굴린 후유증(aftermath)이 있을 수 있다.
    """

    holder: dict
    injury: TableInjury
    reason: EndReason = EndReason.EXPIRED
    aftermath: dict | None = None


def is_lasting(ruleset: Ruleset, row: TableInjury) -> bool:
    """이 부상이 오래 가는 것인가. 규칙에 없는 부상이면(규칙이 바뀐 판) 짧은 것으로 본다."""
    definition = injury_rules.find_injury(ruleset, row.injury)
    return definition is not None and definition.healing == Healing.HEALS


def close_out(
    ruleset: Ruleset,
    dice: Dice,
    holder: dict,
    row: TableInjury,
    rows: list[TableInjury],
    table_id: uuid.UUID,
    moment: Moment,
) -> Ended:
    """
    끝난 부상 하나를 정리한다. 오래 가는 것이면 나은 것이고 후유증 표를 굴린다. 짧은 것이면 풀린 것이다.

    후유증은 같은 사람의 부상 목록(rows)에 입힌다.
    """
    if not is_lasting(ruleset, row):
        return Ended(holder, row)
    aftermath = aftermath_of(ruleset, dice, row, rows, table_id, moment)
    return Ended(holder, row, EndReason.HEALED, aftermath)


def any_due(members: list[TableMember], scene: Scene, moment: Moment) -> bool:
    """
    이 라운드가 닫힐 때 풀리거나 나을 부상이 하나라도 있는가. 죽은 쪽은 보지 않는다.

    없으면 규칙을 읽지 않아도 된다.
    """
    living = [member for member in members if member.sheet is not None and not sheets.is_dead(member)]
    rows = [row for member in living for row in member.sheet.injuries]
    rows.extend(row for npc in scene.npcs if not npcs.is_dead(npc) for row in npc.injuries)
    return any(injuries.is_due(row, moment) for row in rows)


def expire_all(
    members: list[TableMember], scene: Scene, ruleset: Ruleset, dice: Dice, table_id: uuid.UUID, moment: Moment
) -> list[Ended]:
    """
    이 라운드가 닫힐 때 풀리거나 나을 부상을 모두 끝낸다. 앉은 사람의 지금 캐릭터와 테이블의 NPC 전부다.

    오래 가는 것이 나으면 후유증 표를 굴린다. 사람마다 생긴 순서로, 앉은 사람 먼저, 그다음 NPC 의 순서로 굴린다.
    끝난 것과 누가 입고 있었는지를 돌려준다. 이벤트에 적을 것이다.
    장면에 나오지 않은 NPC 의 부상도 끝내고 후유증도 굴리지만 돌려주지 않는다. 이벤트는 앉은 사람 모두가 읽는데,
    그 인물을 부를 이름(장면의 호칭)이 없다. 끝낸 것은 부상의 기록(ended_at)에 남는다.
    죽은 캐릭터와 NPC 의 부상은 그대로 둔다. 죽은 뒤에 낫거나 후유증이 생기지 않는다.
    """
    ended: list[Ended] = []
    for member in members:
        if member.sheet is None or sheets.is_dead(member):
            continue
        holder = {'user_id': str(member.user_id), 'character_name': member.character_name}
        rows = member.sheet.injuries
        for row in injuries.expire(rows, moment):
            ended.append(close_out(ruleset, dice, holder, row, rows, table_id, moment))
    for npc in scene.npcs:
        if npcs.is_dead(npc):
            continue
        seen = find_cast_member(scene.cast, npc.entry_id)
        holder = {'entry_id': str(npc.entry_id), 'name': seen.name if seen else ''}
        closed = [
            close_out(ruleset, dice, holder, row, npc.injuries, table_id, moment)
            for row in injuries.expire(npc.injuries, moment)
        ]
        if seen is not None:
            ended.extend(closed)
    return ended
