# trpg-server/app/rounds/injury_ticks.py

"""
짧은 부상(상태 이상)이 라운드마다 입히는 피해(#254). 독, 출혈, 화상 같은 것이다. 라운드가 닫힐 때 정한다
(app/rounds/service.py 의 begin_closing).

  - 규칙의 부상에 damage(등급과 성질)가 있는 짧은 것만 깎는다. 입고 있는 줄마다 한 번이다.
    같은 부상이 다시 걸리면 하나로 남고 풀릴 라운드만 새로 센다(app/rounds/injuries.py 의 wound). 피해가 겹치지 않는다.
  - 이 라운드에 걸린 것은 깎지 않는다. 다음 라운드부터 풀릴 라운드까지 라운드마다 한 번이다.
    1 라운드짜리는 한 번, 3 라운드짜리는 세 번 깎는다(효과가 드는 라운드와 같다).
  - 깎는 차례: 앉은 사람(들어온 순서), 장면의 인물(장면의 차례), 장면의 몬스터(장면의 차례).
    한 사람 안에서는 입은 순서다.
  - 죽은 쪽과 이미 쓰러진 쪽(HP 0)은 깎지 않는다. 쓰러진 캐릭터의 위험은 죽음의 굴림이 맡는다.
    장면에 나오지 않은 인물과 몬스터는 깎지 않는다(부를 이름이 없고, 보는 사람이 없다). 부상은 그대로 풀린다.
  - 피해는 다른 피해와 같은 길로 든다(app/rounds/checks.py 의 change_sheet, change_cast_member, change_scene_monster).
    성질과 저항을 따르고(#886 ③), 큰 타격이나 쓰러짐에는 부상 표를 굴린다. HP 가 0 이 되면 쓰러진다.
    캐릭터는 피해로 바로 죽지 않는다(죽음의 굴림으로 죽는다). 인물과 몬스터는 죽이려는 피해가 아니다(lethal 이 아니다).
    몬스터는 타입에 따라 쓰러지거나 부서진다. 처음 쓰러진 인물과 몬스터는 드롭을 굴린다(app/rounds/drops.py).
  - 피해를 입은 캐릭터는 이번 라운드에 다친 사람이다. 쉬기와 기다리기가 깨진다.
  - 죽음의 굴림 뒤, 부상이 풀리기 전에 깎는다. 이 라운드에 쓰러진 캐릭터는 이번에 죽음의 굴림을 굴리지 않는다.
    마지막 라운드에도 깎고 나서 풀린다.

DB 를 모른다(이벤트를 적는 record 말고). 입은 쪽의 상태를 고친다. 저장하지 않는다.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.action import ActionKind, CheckAction, Consequence, Recipient
from app.engine.dice import Dice
from app.engine.health import ChangeKind
from app.engine.injury import find_injury
from app.engine.ruleset import InjuryDamage, Ruleset
from app.events import recorder
from app.events.models import EventType, TableEvent
from app.rounds import drops, records
from app.rounds.cast import CastMember, Scene
from app.rounds.checks import change_cast_member, change_scene_monster, change_sheet
from app.rounds.effects import Judging
from app.rounds.judging import build_judging
from app.rounds.models import Round
from app.rounds.monster_scene import SceneMonster
from app.tables import monsters, npcs, sheets
from app.tables.models import GameTable, TableInjury, TableMember


@dataclass
class Ticks:
    """
    이 닫힘에 상태가 입힌 피해들과, 그 피해를 입은 앉은 사람들(user_id).

    ticks 의 한 줄은 피해 하나다. 누구(kind 와 그 쪽의 칸), 무슨 부상(injury, injury_name), 바뀐 것(effect),
    처음 쓰러져 굴린 드롭(drop)이다.
    """

    ticks: list[dict] = field(default_factory=list)
    hurt: set[uuid.UUID] = field(default_factory=set)


def is_ticking(row: TableInjury, round_number: int) -> bool:
    """이 줄이 이 라운드에 깎을 수 있는 짧은 부상인가. 입고 있고, 라운드로 세고, 이 라운드 전에 걸렸다."""
    return row.ended_at is None and row.ends_after_round is not None and row.round_number < round_number


def damage_of(ruleset: Ruleset, row: TableInjury) -> InjuryDamage | None:
    """그 줄의 부상이 라운드마다 입히는 피해. 없거나 규칙에 없는 부상이면 None."""
    definition = find_injury(ruleset, row.injury)
    return definition.damage if definition is not None else None


def ticking_rows(
    ruleset: Ruleset, rows: list[TableInjury], round_number: int
) -> list[tuple[TableInjury, InjuryDamage]]:
    """한 쪽의 부상 가운데 이 라운드에 깎을 것과 그 피해. 입은 순서다."""
    found = []
    for row in rows:
        damage = damage_of(ruleset, row) if is_ticking(row, round_number) else None
        if damage is not None:
            found.append((row, damage))
    return found


def standing_members(table: GameTable) -> list[TableMember]:
    """깎을 수 있는 앉은 사람들. 시트가 있고, 죽지 않았고, 쓰러지지 않았다. 들어온 순서다."""
    return [
        member
        for member in table.members
        if member.sheet is not None and not sheets.is_dead(member) and member.sheet.hp > 0
    ]


def standing_cast(scene: Scene) -> list[CastMember]:
    """깎을 수 있는 장면의 인물들. 죽지 않았고 쓰러지지 않았다."""
    return [person for person in scene.cast if not npcs.is_dead(person.npc) and person.npc.hp > 0]


def standing_monsters(scene: Scene) -> list[SceneMonster]:
    """깎을 수 있는 장면의 몬스터들. 죽지 않았고 쓰러지지 않았다."""
    return [monster for monster in scene.monsters if not monsters.is_dead(monster.state) and monster.state.hp > 0]


def any_ticking(table: GameTable, scene: Scene, round_number: int) -> bool:
    """
    이 라운드에 깎을지도 모르는 줄이 하나라도 있는가. 라운드로 세는 짧은 것이 이 라운드 전에 걸렸다.

    없으면 판을 읽지 않는다. 있어도 그 부상에 피해가 없을 수 있다(규칙을 읽어야 안다).
    """
    rows = [row for member in standing_members(table) for row in member.current_sheet.injuries]
    rows.extend(row for person in standing_cast(scene) for row in person.npc.injuries)
    rows.extend(row for monster in standing_monsters(scene) for row in monster.state.injuries)
    return any(is_ticking(row, round_number) for row in rows)


def harm_action(judging: Judging, damage: InjuryDamage, **aimed: uuid.UUID) -> CheckAction:
    """
    인물이나 몬스터의 HP 를 바꾸는 함수에 넘길 판정의 모양. 그 함수는 대상과 lethal 과 aim 만 읽는다.

    능력은 읽지 않지만 칸이 있어야 해서 규칙의 첫 능력치를 적는다. 대상을 적으려면 타격(harm)도 적어야 한다.
    """
    ability = judging.ruleset.abilities[0].key
    return CheckAction.model_validate({'kind': ActionKind.CHECK, 'ability': ability, 'harm': damage.magnitude, **aimed})


def harm(damage: InjuryDamage) -> Consequence:
    """상태의 피해. 입은 쪽이 받는다."""
    return Consequence(kind=ChangeKind.DAMAGE, magnitude=damage.magnitude, recipient=Recipient.TARGET)


def tick_head(row: TableInjury, judging: Judging) -> dict:
    """피해 하나의 무슨 부상인가. 이름표와 규칙의 이름이다. 이름은 누구의 이름(name)과 겹치지 않게 따로 둔다."""
    definition = find_injury(judging.ruleset, row.injury)
    return {'injury': row.injury, 'injury_name': definition.name if definition is not None else row.injury}


def tick_member(judging: Judging, member: TableMember, ticks: Ticks) -> None:
    """앉은 사람 하나의 상태들이 깎는다. 쓰러지면 멈춘다."""
    for row, damage in ticking_rows(judging.ruleset, member.current_sheet.injuries, judging.moment.round_number):
        if member.current_sheet.hp <= 0:
            return
        effect = change_sheet(judging, member, ChangeKind.DAMAGE, damage.magnitude, nature=damage.nature)
        who = {'kind': 'pc', 'user_id': str(member.user_id), 'character_name': member.character_name}
        ticks.ticks.append({**who, **tick_head(row, judging), 'effect': effect, 'drop': None})
        ticks.hurt.add(member.user_id)


def tick_npc(judging: Judging, person: CastMember, ticks: Ticks) -> None:
    """장면의 인물 하나의 상태들이 깎는다. 쓰러지거나 죽으면 멈춘다. 처음 쓰러지면 그 인물이 선 곳에 드롭을 준다."""
    for row, damage in ticking_rows(judging.ruleset, person.npc.injuries, judging.moment.round_number):
        if npcs.is_dead(person.npc) or person.npc.hp <= 0:
            return
        action = harm_action(judging, damage, npc=person.entry_id)
        effect = change_cast_member(judging, action, harm(damage), nature=damage.nature)
        drop = drops.npc_drop_at(judging, person.npc.place_id, effect)
        who = {'kind': 'npc', 'entry_id': str(person.entry_id), 'name': person.name}
        ticks.ticks.append({**who, **tick_head(row, judging), 'effect': effect, 'drop': drop})


def tick_monster(judging: Judging, monster: SceneMonster, ticks: Ticks) -> None:
    """장면의 몬스터 한 마리의 상태들이 깎는다. 쓰러지거나 부서지면 멈춘다. 처음 쓰러지면 드롭을 굴린다."""
    for row, damage in ticking_rows(judging.ruleset, monster.state.injuries, judging.moment.round_number):
        if monsters.is_dead(monster.state) or monster.state.hp <= 0:
            return
        action = harm_action(judging, damage, monster=monster.state.id)
        effect = change_scene_monster(judging, action, harm(damage), nature=damage.nature)
        drop = drops.drop_after(judging, effect)
        who = {'kind': 'monster', 'monster_id': str(monster.state.id), 'name': monster.name}
        ticks.ticks.append({**who, **tick_head(row, judging), 'effect': effect, 'drop': drop})


def settle(table: GameTable, round_: Round, dice: Dice, scene: Scene) -> Ticks:
    """
    이 라운드가 닫힐 때 상태들이 피해를 입힌다. 입힌 것과 다친 앉은 사람들을 돌려준다.

    깎을지도 모르는 줄이 없으면 판을 읽지 않고 빈 것을 돌려준다.
    """
    ticks = Ticks()
    if not any_ticking(table, scene, round_.cycle):
        return ticks
    judging = build_judging(table, round_, dice, scene)
    for member in standing_members(table):
        tick_member(judging, member, ticks)
    for person in standing_cast(scene):
        tick_npc(judging, person, ticks)
    for monster in standing_monsters(scene):
        tick_monster(judging, monster, ticks)
    return ticks


# 피해를 입은 쪽의 kind 마다 이벤트에 적을 누구의 칸
HOLDER_KEYS = {
    'pc': ('user_id', 'character_name'),
    'npc': ('entry_id', 'name'),
    'monster': ('monster_id', 'name'),
}


def holder_of(tick: dict) -> dict:
    """피해 하나의 누구. 부상의 이벤트와 같은 모양이다(캐릭터, NPC, 몬스터)."""
    return {key: tick[key] for key in HOLDER_KEYS[tick['kind']]}


def record_change(session: AsyncSession, table: GameTable, tick: dict, cause: TableEvent) -> TableEvent:
    """피해로 바뀐 것을 그 쪽의 이벤트로 적는다. 캐릭터는 HP, 인물은 NPC, 몬스터는 몬스터의 변화다."""
    if tick['kind'] == 'pc':
        return records.record_hp_change(session, table, tick['effect'], cause=cause)
    if tick['kind'] == 'npc':
        return records.record_npc_change(session, table, tick['effect'], cause=cause)
    return records.record_monster_change(session, table, tick['effect'], cause=cause)


def record(session: AsyncSession, table: GameTable, ticks: Ticks, round_number: int, group: uuid.UUID) -> None:
    """
    상태가 입힌 피해마다 이벤트를 적는다(injury_hurt). 닫힘의 묶음에 넣는다. 행한 사람은 없다(엔진이 깎았다).

    그 뒤에 바뀐 것(HP, 인물, 몬스터의 변화), 그 피해로 굴린 부상, 처음 쓰러져 나온 드롭을 잇는다.
    """
    for tick in ticks.ticks:
        holder = holder_of(tick)
        payload = {'round': round_number, **holder, 'injury': tick['injury']}
        hurt = recorder.record(session, table, EventType.INJURY_HURT, payload=payload, group=group)
        effect = tick['effect']
        if effect is None:
            continue
        changed = record_change(session, table, tick, hurt)
        records.record_injury(session, table, effect.get('injury_roll'), holder, cause=changed)
        records.record_drop(session, table, tick['drop'], cause=changed)
