# trpg-server/app/rounds/resource_rounds.py

"""
라운드가 닫힐 때 수치(#804)에 일어나는 일. 저절로 바뀌는 것(each_round)과 문턱의 부상(at_min, at_max)이다.

순서: 판정과 쉬기가 수치를 바꾼 뒤에 부른다(app/rounds/service.py 의 begin_closing). 앉은 사람마다
  1. 규칙의 each_round 대로 수치를 바꾼다(광기 +1, 마나 +1).
  2. 문턱을 맞춘다. 닿아 있는 문턱의 부상을 입히고, 벗어난 문턱의 부상을 푼다.
부상은 수치의 그림자다. 문턱에서 생긴 부상(source resource)은 라운드나 시간으로 풀리지 않고, 수치가 문턱을 벗어나야
풀린다. 다른 길(물건의 풀기, 치료)로 풀렸어도 수치가 여전히 문턱에 있으면 다음 닫힘에 다시 입는다.
같은 부상을 다른 까닭으로 이미 입고 있으면 또 입히지 않는다. 그 부상은 이 모듈이 풀지 않는다.
판정, 쉬기, 물건이 수치를 바꾼 것도 여기서 한 번에 문턱을 본다. 라운드 안에서는 수치가 문턱에 닿아도 부상이 없다.

죽은 캐릭터는 보지 않는다. NPC 와 몬스터에는 아직 수치가 없다.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine import injury as injury_rules
from app.engine.ruleset import Ruleset
from app.events import recorder
from app.events.models import EventType
from app.rounds.injuries import EndReason
from app.rounds.models import Round
from app.rounds.records import ResourceSource
from app.rounds.state import rules_of
from app.tables import injuries, resources, sheets
from app.tables.models import GameTable, InjurySource, TableInjury, TableMember, TableSheet


@dataclass(frozen=True)
class Drift:
    """앉은 사람 하나에게 이 닫힘이 수치로 한 일. 바뀐 수치들, 입은 부상들, 풀린 부상들이다."""

    holder: dict
    shifts: list[dict]
    gained: list[dict]
    ended: list[TableInjury]


def has_resources(table: GameTable) -> bool:
    """
    이 판의 규칙에 수치가 있는가. 판의 문서를 올리지 않고 들여다본다.

    규칙을 읽는 것은 판의 복사본을 통째로 읽는 일이라 싸지 않다. 수치가 없는 판(대부분)은 여기서 끝낸다.
    수치가 생기기 전의 판(형식 65 앞)에는 그 칸이 없다. 올리면 빈 목록이 되므로 없는 것과 같다.
    """
    rules = (table.content or {}).get('rulebook', {}).get('rules', {})
    return bool(rules.get('resources'))


def holder_of(member: TableMember) -> dict:
    """이벤트에 적을 캐릭터. 누구의 수치인지다."""
    return {'user_id': str(member.user_id), 'character_name': member.character_name}


def threshold_document(ruleset: Ruleset, key: str) -> dict:
    """문턱으로 입은 부상 하나를 적을 모양. 라운드나 시간으로 풀리지 않아 풀릴 때가 비어 있다."""
    definition = injury_rules.find_injury(ruleset, key)
    return {
        'injury': key,
        'name': definition.name if definition else key,
        'source': InjurySource.RESOURCE.value,
        'ends_after_round': None,
        'heals_at': None,
    }


def from_thresholds(rows: list[TableInjury]) -> list[TableInjury]:
    """문턱으로 입어 아직 입고 있는 부상들."""
    return [row for row in injuries.active(rows) if row.source == InjurySource.RESOURCE]


def release(rows: list[TableInjury], wanted: list[str]) -> list[TableInjury]:
    """문턱을 벗어난 부상들을 푼다. 푼 것을 돌려준다."""
    released = [row for row in from_thresholds(rows) if row.injury not in wanted]
    for row in released:
        injuries.end(row)
    return released


def inflict_wanted(
    ruleset: Ruleset, rows: list[TableInjury], wanted: list[str], table_id: uuid.UUID, round_number: int
) -> list[dict]:
    """닿아 있는 문턱의 부상 중 입고 있지 않은 것을 입힌다. 입힌 것을 문서로 돌려준다."""
    gained = []
    for key in wanted:
        if key in injuries.active_keys(rows):
            continue
        injuries.inflict(rows, table_id, key, InjurySource.RESOURCE, round_number, None, None)
        gained.append(threshold_document(ruleset, key))
    return gained


def follow_thresholds(
    ruleset: Ruleset, sheet: TableSheet, table_id: uuid.UUID, round_number: int
) -> tuple[list[dict], list[TableInjury]]:
    """시트의 부상을 수치의 문턱에 맞춘다. 벗어난 것을 먼저 풀고, 닿은 것을 입힌다. 입힌 것과 푼 것이다."""
    wanted = resources.wanted_injuries(ruleset, sheet)
    ended = release(sheet.injuries, wanted)
    gained = inflict_wanted(ruleset, sheet.injuries, wanted, table_id, round_number)
    return gained, ended


def drift_member(ruleset: Ruleset, member: TableMember, table_id: uuid.UUID, round_number: int) -> Drift | None:
    """앉은 사람 하나의 라운드마다의 변화와 문턱. 아무 일도 없었으면 None."""
    shifts = [resources.shift_document(shift) for shift in resources.each_round(ruleset, member.sheet)]
    gained, ended = follow_thresholds(ruleset, member.sheet, table_id, round_number)
    if not shifts and not gained and not ended:
        return None
    return Drift(holder=holder_of(member), shifts=shifts, gained=gained, ended=ended)


def settle(table: GameTable, round_: Round) -> list[Drift]:
    """
    이 라운드가 닫힐 때 수치에 일어나는 일을 정한다. 앉은 사람마다, 들어온 순서다. 주사위를 굴리지 않는다.

    시트를 고친다. 저장은 부른 쪽이 한다. 이벤트에 적을 것을 돌려준다(record).
    """
    if not has_resources(table):
        return []
    ruleset = rules_of(table)
    drifts = []
    for member in table.members:
        if member.sheet is None or sheets.is_dead(member):
            continue
        drift = drift_member(ruleset, member, table.id, round_.number)
        if drift is not None:
            drifts.append(drift)
    return drifts


def record(session: AsyncSession, table: GameTable, drifts: list[Drift], round_number: int, group: uuid.UUID) -> None:
    """
    수치의 변화(resource_changed, source round), 문턱으로 입은 부상(injury_gained, source resource),
    벗어나 풀린 부상(injury_ended, reason resource)을 이벤트로 적는다. 닫힘의 묶음에 넣는다. 행한 사람은 없다.
    """
    for drift in drifts:
        for shift in drift.shifts:
            payload = {'round': round_number, **drift.holder, **shift, 'source': ResourceSource.ROUND}
            recorder.record(session, table, EventType.RESOURCE_CHANGED, payload=payload, group=group)
        for row in drift.ended:
            payload = {'round': round_number, **drift.holder, 'injury': row.injury, 'reason': EndReason.RESOURCE.value}
            recorder.record(session, table, EventType.INJURY_ENDED, payload=payload, group=group)
        for gained in drift.gained:
            payload = {
                'round': round_number,
                **drift.holder,
                'injury': gained['injury'],
                'source': gained['source'],
                'ends_after_round': None,
                'heals_at': None,
            }
            recorder.record(session, table, EventType.INJURY_GAINED, payload=payload, group=group)
