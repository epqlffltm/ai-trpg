# trpg-server/app/rounds/injury_escapes.py

"""
짧은 부상(상태 이상)에서 판정으로 벗어나기(#254). 라운드가 닫힐 때 상태의 피해(app/rounds/injury_ticks.py) 바로 뒤에
정한다(app/rounds/service.py 의 begin_closing).

  - 규칙의 부상에 escape(능력치와 난이도)가 있는 짧은 것만 굴린다. 입고 있는 줄마다 한 번이다.
  - 이 라운드에 걸린 것은 굴리지 않는다. 이 라운드가 닫힐 때 어차피 풀리는 것(풀릴 라운드가 이 라운드)도 굴리지 않는다.
    그래서 3 라운드짜리는 걸린 다음 두 라운드가 닫힐 때 두 번 굴릴 기회가 있다(세 번째에는 어차피 풀린다).
  - 굴리는 쪽은 상태의 피해와 같다. 앉은 사람, 장면의 인물, 장면의 몬스터의 차례이고, 죽었거나 쓰러진 쪽과
    장면에 나오지 않은 인물과 몬스터는 굴리지 않는다(app/rounds/injury_ticks.py 의 standing_*).
  - 그 쪽의 능력치로 굴린다. 입은 부상의 영향(보정 깎기, 불리함)을 받는다. 벗어나려는 그 상태의 영향도 받는다.
  - 성공하면 그 부상을 바로 끝낸다(ended_at). 실패하면 그대로다. 풀릴 라운드가 되면 늘 그렇듯 풀린다.
  - 피해를 먼저 입고 나서 굴린다. 벗어난 라운드에도 그 라운드의 피해는 입는다.

DB 를 모른다(이벤트를 적는 record 말고). 입은 쪽의 부상을 끝낸다. 저장하지 않는다.
"""

import uuid
from dataclasses import asdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.check import known_difficulty, resolve_hindered
from app.engine.dice import Dice
from app.engine.injury import find_injury
from app.engine.ruleset import InjuryEscape, Ruleset
from app.events import recorder
from app.events.models import EventType
from app.rounds import injuries as round_injuries
from app.rounds.cast import Scene
from app.rounds.injury_ticks import is_ticking, standing_cast, standing_members, standing_monsters
from app.rounds.models import Round
from app.rounds.state import required, rules_of
from app.tables import injuries
from app.tables.models import GameTable, TableInjury


def is_escapable(row: TableInjury, round_number: int) -> bool:
    """이 줄이 이 라운드에 벗어나기를 굴릴 짧은 부상인가. 이 라운드 전에 걸렸고, 이 라운드가 닫힐 때 풀리지 않는다."""
    return is_ticking(row, round_number) and row.ends_after_round is not None and row.ends_after_round > round_number


def escape_of(ruleset: Ruleset, row: TableInjury) -> InjuryEscape | None:
    """그 줄의 부상에서 벗어나는 판정. 없거나 규칙에 없는 부상이면 None."""
    definition = find_injury(ruleset, row.injury)
    return definition.escape if definition is not None else None


def escapable_rows(
    ruleset: Ruleset, rows: list[TableInjury], round_number: int
) -> list[tuple[TableInjury, InjuryEscape]]:
    """한 쪽의 부상 가운데 이 라운드에 벗어나기를 굴릴 것과 그 판정. 입은 순서다."""
    found = []
    for row in rows:
        escape = escape_of(ruleset, row) if is_escapable(row, round_number) else None
        if escape is not None:
            found.append((row, escape))
    return found


def holders(table: GameTable, scene: Scene) -> list[tuple[dict, dict[str, int], list[TableInjury]]]:
    """
    굴릴 수 있는 쪽마다 (누구, 능력치, 부상 목록). 앉은 사람, 장면의 인물, 장면의 몬스터의 차례다.

    누구는 부상의 이벤트와 같은 모양이다(캐릭터, NPC, 몬스터).
    """
    found = []
    for member in standing_members(table):
        who = {'user_id': str(member.user_id), 'character_name': member.character_name}
        found.append((who, member.current_sheet.abilities, member.current_sheet.injuries))
    for person in standing_cast(scene):
        found.append(
            ({'entry_id': str(person.entry_id), 'name': person.name}, person.npc.abilities, person.npc.injuries)
        )
    for monster in standing_monsters(scene):
        who = {'monster_id': str(monster.state.id), 'name': monster.name}
        found.append((who, monster.state.abilities, monster.state.injuries))
    return found


def any_escapable(table: GameTable, scene: Scene, round_number: int) -> bool:
    """이 라운드에 굴릴지도 모르는 줄이 하나라도 있는가. 없으면 판을 읽지 않는다."""
    return any(is_escapable(row, round_number) for _, _, rows in holders(table, scene) for row in rows)


def roll_escape(
    ruleset: Ruleset, dice: Dice, abilities: dict[str, int], rows: list[TableInjury], escape: InjuryEscape
) -> dict:
    """벗어나는 판정을 한 번 굴린다. 결과에 적을 모양(능력, 난이도, 판정, 부상의 영향)을 돌려준다."""
    difficulty = known_difficulty(ruleset, escape.difficulty)
    hindrance = round_injuries.hindrance_for(ruleset, rows, escape.ability)
    rolled = resolve_hindered(ruleset, abilities[escape.ability], difficulty, dice, hindrance)
    return {
        'ability': escape.ability,
        'difficulty': difficulty.key,
        **asdict(rolled.check),
        'hindrance': round_injuries.hindrance_document(rolled),
    }


def settle(table: GameTable, round_: Round, dice: Dice, scene: Scene) -> list[dict]:
    """
    이 라운드가 닫힐 때 상태에서 벗어나기를 굴린다. 굴린 것들을 돌려준다. 성공한 부상은 끝낸다.

    한 줄은 누구(holder), 무슨 부상(injury, injury_name), 판정(check)이다. 판정의 success 가 벗어났는가다.
    굴릴지도 모르는 줄이 없으면 판을 읽지 않고 빈 목록을 돌려준다.
    """
    if not any_escapable(table, scene, round_.cycle):
        return []
    ruleset = rules_of(table)
    rolled = []
    for holder, abilities, rows in holders(table, scene):
        for row, escape in escapable_rows(ruleset, rows, round_.cycle):
            check = roll_escape(ruleset, dice, abilities, rows, escape)
            if check['success']:
                injuries.end(row)
            name = required(find_injury(ruleset, row.injury), 'injury').name
            rolled.append({'holder': holder, 'injury': row.injury, 'injury_name': name, 'check': check})
    return rolled


def record(session: AsyncSession, table: GameTable, rolled: list[dict], round_number: int, group: uuid.UUID) -> None:
    """
    벗어나기를 굴린 것마다 이벤트를 적는다(injury_escape_rolled). 닫힘의 묶음에 넣는다. 행한 사람은 없다.

    벗어났으면 바로 뒤에 그 부상이 끝난 것(injury_ended, reason escaped)을 그 굴림에 잇는다.
    """
    for one in rolled:
        head = {'round': round_number, **one['holder'], 'injury': one['injury']}
        event = recorder.record(
            session, table, EventType.INJURY_ESCAPE_ROLLED, payload={**head, **one['check']}, group=group
        )
        if one['check']['success']:
            ended = {**head, 'reason': round_injuries.EndReason.ESCAPED.value}
            recorder.record(session, table, EventType.INJURY_ENDED, payload=ended, cause=event)
