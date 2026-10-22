# trpg-server/app/rounds/rests.py

"""
쉬기. 캐릭터가 쉬는 행동(rest)을 받고, 라운드가 닫힐 때 쉰 사람과 쓰러진 사람과 모두의 HP 를 돌려준다.

규칙은 룰북의 쉬기(Ruleset.rest)다. 시간과 회복량은 거기서 온다.
  - 쉬기(선언): 짧게(short) 또는 길게(long). 판정이 없다. 차례가 오면 다음 라운드가 적어도 그 휴식의 시간만큼 뒤에
    열리게 한다(judge_rest). 여럿이 쉬거나 길을 가면 가장 긴 쪽을 따른다.
    시계는 하나라서 한 사람이 여덟 시간 쉬면 그 라운드는 모두에게 여덟 시간이다(길을 갈 때와 같다).
  - 회복은 판정과 죽음의 굴림과 부상을 다 끝낸 뒤에 정한다(settle). 그 라운드에 다쳤는지를 다 본 다음이다.
    다쳤으면 휴식이 깨져 회복하지 않는다(hurt). 쓰러졌거나 죽었으면 그것이 까닭이다(downed, dead).
    짧은 휴식은 규칙의 등급만큼, 긴 휴식은 최대 HP 까지 회복한다.
  - 쉴 수 없는 곳은 없다. 몬스터가 있어도 쉴 수 있다. 막으면 숨은 몬스터가 있는지 알아내는 길이 된다.
    전투 중에 쉬면 맞아서 깨질 뿐이다.
  - 되살아나기: 고비를 넘기고(죽음의 굴림의 성공이 다 모여) 쓰러져 있는 캐릭터는 의식이 없어 선언하지 못한다.
    대신 한 장면에 규칙의 시간이 흐르면 되살아나기를 굴린다. 성공하면 HP 1 로 일어난다.
    죽음의 굴림과 다르다. 그것은 죽어 가는 캐릭터가 죽는지를, 이것은 고비를 넘긴 캐릭터가 일어나는지를 정한다.
    죽어 가는 캐릭터는 굴리지 않는다. 죽은 캐릭터는 어떤 것으로도 돌아오지 않는다.
  - 저절로 회복하기: 규칙에 있으면, 시계가 정한 간격의 눈금을 지날 때마다 회복한다. 쉰 사람과 다친 사람은 받지 않는다.

DB 를 모른다. 시트의 HP 와 선언의 결과를 고친다. 저장과 이벤트는 부른 쪽이 한다(app/rounds/service.py).
"""

import enum
import uuid
from dataclasses import dataclass

from app.calendar import state as calendar
from app.engine import death, health
from app.engine.action import RestAction, RestLength
from app.engine.dice import Dice
from app.engine.health import ChangeKind
from app.engine.ruleset import NaturalRecovery, Rest, Revive, Ruleset
from app.rounds.effects import Judging
from app.rounds.errors import ActionNotInRulesError
from app.rounds.models import Declaration, Round
from app.rounds.state import find_declaration, rest_of, rules_of
from app.tables import sheets
from app.tables.models import GameTable, TableMember, TableSheet


class Cause(enum.StrEnum):
    """회복한 까닭. 이벤트의 cause 에 적는다."""

    # 쉬는 행동을 선언했다
    REST = 'rest'
    # 시간이 흘러 저절로 회복했다
    NATURAL = 'natural'


class Broken(enum.StrEnum):
    """선언한 휴식이 깨진 까닭."""

    # 그 라운드에 피해를 입었다
    HURT = 'hurt'
    # 라운드가 닫힐 때 쓰러져 있다
    DOWNED = 'downed'
    # 라운드가 닫힐 때 죽어 있다
    DEAD = 'dead'


@dataclass(frozen=True)
class Recovered:
    """라운드가 닫힐 때 쉬기로 일어난 일. 이벤트에 적을 모양들이다. 선언한 휴식의 결과는 그 선언에 적혀 있다."""

    revivals: list[dict]
    natural: list[dict]


NOTHING = Recovered(revivals=[], natural=[])


# --- 받기와 차례 ---


def accept_rest(ruleset: Ruleset, action: RestAction) -> dict:
    """쉬는 행동을 받는다. 이 규칙에 쉬기가 없으면 ActionNotInRulesError(kind)."""
    if ruleset.rest is None:
        raise ActionNotInRulesError('kind')
    return action.model_dump(mode='json')


def rest_minutes(rest: Rest, length: RestLength) -> int:
    """그 휴식에 드는 시간(분)."""
    return rest.short.minutes if length == RestLength.SHORT else rest.long.minutes


def judge_rest(judging: Judging, action: RestAction) -> dict:
    """
    쉬는 사람의 차례. 다음 라운드가 적어도 그 휴식의 시간만큼 뒤에 열리게 한다. 결과의 문서를 돌려준다.

    회복은 아직 정하지 않는다. 뒤의 차례에 맞을 수 있다. 라운드가 닫힐 때 정한다(settle).
    """
    minutes = rest_minutes(judging.ruleset.rest, action.length)
    calendar.stretch_next_step(judging.table, minutes)
    return {'rest': {'length': action.length.value, 'minutes': minutes}}


# --- 선언한 휴식 ---


def broken_by(member: TableMember, hurt: set[uuid.UUID]) -> Broken | None:
    """휴식이 깨진 까닭. 깨지지 않았으면 None. 죽음, 쓰러짐, 다침의 순서로 본다."""
    if sheets.is_dead(member):
        return Broken.DEAD
    if sheets.is_downed_alive(member):
        return Broken.DOWNED
    if member.user_id in hurt:
        return Broken.HURT
    return None


def recover(ruleset: Ruleset, length: RestLength, sheet: TableSheet, dice: Dice) -> tuple[list[int], int]:
    """휴식 하나의 회복. 굴린 눈들과 회복한 뒤의 HP 다. 긴 휴식은 굴리지 않고 최대 HP 까지다."""
    if length == RestLength.LONG:
        return [], sheet.max_hp
    magnitude = health.find_magnitude(ruleset, ruleset.rest.short.heal)
    change = health.change_hp(ChangeKind.RECOVERY, magnitude, sheet.hp, sheet.max_hp, dice)
    return list(change.rolls), change.after


def finish_rest(
    ruleset: Ruleset, member: TableMember, declaration: Declaration, hurt: set[uuid.UUID], dice: Dice
) -> None:
    """선언한 휴식 하나를 끝낸다. 깨지지 않았으면 회복한다. 결과를 그 선언의 outcome 의 rest 에 적는다."""
    rest = rest_of(declaration)
    sheet = member.sheet
    broken = broken_by(member, hurt)
    before = sheet.hp
    rolls, after = ([], before) if broken is not None else recover(ruleset, RestLength(rest['length']), sheet, dice)
    sheet.hp = after
    result = {
        **rest,
        'rested': broken is None,
        'reason': broken,
        'rolls': rolls,
        'before': before,
        'after': after,
        'max_hp': sheet.max_hp,
    }
    # 새 문서로 바꿔 끼운다. 안을 고치면 DB 의 JSON 칸이 바뀐 줄 모른다
    declaration.outcome = {**declaration.outcome, 'rest': result}


def resting(table: GameTable, round_: Round) -> list[tuple[TableMember, Declaration]]:
    """이번 라운드에 쉰 사람과 그 선언. 앉은 순서다. 차례가 와서 쉬기를 시작한 사람만이다."""
    pairs = []
    for member in table.members:
        declaration = find_declaration(round_, member.user_id)
        if rest_of(declaration) is not None and member.sheet is not None:
            pairs.append((member, declaration))
    return pairs


def settle_rests(
    ruleset: Ruleset, pairs: list[tuple[TableMember, Declaration]], hurt: set[uuid.UUID], dice: Dice
) -> None:
    """쉰 사람마다 휴식을 끝낸다. 앉은 순서로 굴린다."""
    for member, declaration in pairs:
        finish_rest(ruleset, member, declaration, hurt, dice)


# --- 되살아나기 ---


def is_stable(ruleset: Ruleset, sheet: TableSheet) -> bool:
    """
    쓰러져 있는 캐릭터가 고비를 넘겼는가. 죽음의 굴림의 성공이 다 모였다.

    죽음의 굴림이 없는 규칙에서는 쓰러진 캐릭터가 죽지 않는다. 늘 고비를 넘긴 것으로 본다.
    """
    if ruleset.death_save is None:
        return True
    fate = death.fate_of(ruleset.death_save, sheet.death_successes, sheet.death_failures)
    return fate == death.Fate.STABLE


def revive(ruleset: Ruleset, revival: Revive, member: TableMember, round_number: int, dice: Dice) -> dict:
    """
    되살아나기를 한 번 굴린다. 성공이면 HP 1 로 일어나고 죽음의 굴림에서 센 것을 지운다. 이벤트의 모양을 돌려준다.

    규칙의 주사위를 굴린다. 능력치의 보정은 더하지 않는다(죽음의 굴림과 같다).
    """
    sheet = member.sheet
    roll = dice.roll(ruleset.die)
    success = roll >= revival.target
    if success:
        sheet.hp = 1
        sheets.clear_death_saves(sheet)
    return {
        'round': round_number,
        'user_id': str(member.user_id),
        'character_name': member.character_name,
        'roll': roll,
        'target': revival.target,
        'success': success,
        'hp': sheet.hp,
    }


def revive_all(ruleset: Ruleset, table: GameTable, round_number: int, hurt: set[uuid.UUID], dice: Dice) -> list[dict]:
    """
    고비를 넘기고 쓰러져 있는 캐릭터마다 되살아나기를 굴린다. 앉은 순서다.

    이 장면에 규칙의 시간이 흘러야 한다. 그 라운드에 맞은 캐릭터는 굴리지 않는다. 쉬지 못했다.
    """
    revival = ruleset.rest.revive
    if revival is None or calendar.next_step(table) < revival.minutes:
        return []
    return [
        revive(ruleset, revival, member, round_number, dice)
        for member in table.members
        if sheets.is_downed_alive(member) and member.user_id not in hurt and is_stable(ruleset, member.sheet)
    ]


# --- 저절로 회복하기 ---


def ticks_between(natural: NaturalRecovery, start: int, end: int) -> int:
    """시각 start 에서 end 까지 지난 눈금의 수. 눈금은 1일째 0시부터 every_minutes 분마다다."""
    return end // natural.every_minutes - start // natural.every_minutes


def recover_naturally(
    ruleset: Ruleset, natural: NaturalRecovery, member: TableMember, ticks: int, round_number: int, dice: Dice
) -> dict | None:
    """
    한 사람이 눈금마다 회복한다. 최대 HP 에 닿으면 그만 굴린다. 이벤트의 모양을 돌려준다. 회복할 것이 없었으면 None.
    """
    sheet = member.sheet
    magnitude = health.find_magnitude(ruleset, natural.heal)
    before, rolls = sheet.hp, []
    for _ in range(ticks):
        if sheet.hp >= sheet.max_hp:
            break
        change = health.change_hp(ChangeKind.RECOVERY, magnitude, sheet.hp, sheet.max_hp, dice)
        rolls += change.rolls
        sheet.hp = change.after
    if not rolls:
        return None
    return {
        'round': round_number,
        'user_id': str(member.user_id),
        'character_name': member.character_name,
        'cause': Cause.NATURAL,
        'length': None,
        'rested': True,
        'reason': None,
        'rolls': rolls,
        'before': before,
        'after': sheet.hp,
        'max_hp': sheet.max_hp,
    }


def can_recover_naturally(member: TableMember, skipped: set[uuid.UUID]) -> bool:
    """저절로 회복할 사람인가. 살아 있고, 깨어 있고, 다치지도 쉬지도 않았다."""
    alive = member.sheet is not None and not sheets.is_dead(member) and not sheets.is_downed_alive(member)
    return alive and member.user_id not in skipped


def natural_all(
    ruleset: Ruleset, table: GameTable, round_number: int, skipped: set[uuid.UUID], dice: Dice
) -> list[dict]:
    """
    저절로 회복할 사람마다 이 장면에 지난 눈금만큼 회복한다. 앉은 순서다.

    규칙에 없거나 눈금을 하나도 안 지났으면 빈 목록이다.
    """
    natural = ruleset.rest.natural
    if natural is None:
        return []
    ticks = ticks_between(natural, table.clock.minutes, calendar.scene_end(table))
    if ticks <= 0:
        return []
    recovered = (
        recover_naturally(ruleset, natural, member, ticks, round_number, dice)
        for member in table.members
        if can_recover_naturally(member, skipped)
    )
    return [one for one in recovered if one is not None]


# --- 라운드가 닫힐 때 ---


def needs_rules(table: GameTable, pairs: list) -> bool:
    """
    쉬기의 규칙을 읽어야 하는가. 쉰 사람이나 쓰러진 사람이 있거나, 판이 저절로 회복을 켰을 수 있다.

    규칙을 읽는 것은 판에 굳은 복사본을 통째로 읽는 일이라 싸지 않다. 저절로 회복은 규칙을 봐야 알므로
    쉰 사람도 쓰러진 사람도 없으면 HP 가 가득 차지 않은 사람이 있을 때만 읽는다.
    """
    if pairs or any(sheets.is_downed_alive(member) for member in table.members):
        return True
    return any(member.sheet is not None and member.sheet.hp < member.sheet.max_hp for member in table.members)


def settle(table: GameTable, round_: Round, hurt: set[uuid.UUID], dice: Dice) -> Recovered:
    """
    라운드가 닫힐 때 쉬기로 일어날 일을 모두 정한다. 선언한 휴식 → 되살아나기 → 저절로 회복의 순서다.

    hurt 는 이번 라운드에 피해를 입은 사람들이다(app/rounds/judging.py 의 roll_checks).
    선언한 휴식의 결과는 그 선언에 적고, 나머지는 이벤트에 적을 모양으로 돌려준다.
    쉰 사람과 일어난 사람은 저절로 회복하지 않는다.
    """
    pairs = resting(table, round_)
    if not needs_rules(table, pairs):
        return NOTHING
    ruleset = rules_of(table)
    if ruleset.rest is None:
        return NOTHING
    settle_rests(ruleset, pairs, hurt, dice)
    revivals = revive_all(ruleset, table, round_.number, hurt, dice)
    # 쉰 사람과 방금 일어난 사람은 저절로 회복하지 않는다. 이 장면의 회복을 이미 받았다
    rested = {member.user_id for member, _ in pairs}
    revived = {uuid.UUID(one['user_id']) for one in revivals if one['success']}
    natural = natural_all(ruleset, table, round_.number, hurt | rested | revived, dice)
    return Recovered(revivals=revivals, natural=natural)
