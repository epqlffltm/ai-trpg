# game-server/app/rounds/moves.py

"""
닫히는 라운드에서 각자 한 일을 서술자에게 줄 모양(app/rounds/narrator.py)으로 만든다.

닫기 시작할 때 한 번 만들어 라운드에 굳힌다(build_moves). 서술은 지금 앉은 사람이 아니라 굳혀 둔 것을 읽는다
(frozen_moves). 그사이에 누가 나가도 장면에서 빠지지 않는다. 문체도 그때 굳힌다(frozen_style).
판정의 결과와 HP 의 변화, 지목의 결과는 선언에 적힌 것을, 죽음의 굴림은 라운드에 적힌 것을 읽는다. 여기서 굴리지 않는다.
DB 를 모른다.
"""

import uuid

from app.assets.models import NarrationStyle
from app.engine.injury import find_injury
from app.engine.ruleset import Ruleset
from app.rounds import injuries as round_injuries
from app.rounds import narration_request
from app.rounds.cast import CastMember, condition_of
from app.rounds.models import Round
from app.rounds.narrator import HealNote, InjuryNote, Move, PersonState
from app.rounds.state import find_arrival, find_declaration, has_outcome, is_down, naming_of, rules_of
from app.tables import injuries, sheets
from app.tables.models import GameTable, TableMember


def healed_notes(ruleset: Ruleset | None, ended: list[round_injuries.Ended], user_id: uuid.UUID) -> list[HealNote]:
    """
    이 라운드가 닫힐 때 시간이 지나 나은 이 사람의 오래 가는 부상들을 서술자에게 줄 모양으로. 생긴 순서다.

    짧은 것이 풀린 것은 넣지 않는다. 지금 입고 있는 부상(injuries)에서 빠지는 것으로 충분하다.
    """
    if ruleset is None:
        return []
    notes = []
    for one in ended:
        if one.reason != round_injuries.EndReason.HEALED or one.holder.get('user_id') != str(user_id):
            continue
        definition = find_injury(ruleset, one.injury.injury)
        if definition is None:
            continue
        aftermath = one.aftermath['name'] if one.aftermath else None
        notes.append(HealNote(name=definition.name, aftermath=aftermath))
    return notes


def build_moves(table: GameTable, round_: Round, ended: list[round_injuries.Ended] | None = None) -> list[Move]:
    """
    닫히는 라운드에서 각자 한 일을 서술자에게 줄 모양으로 만든다. 닫기 시작할 때 한 번 만들어 라운드에 굳힌다.

    지금 앉아 있는 사람 모두가 들어간다. 선언을 내지 않은 사람은 아무것도 하지 않은 것으로 들어간다.
    판정의 결과와 HP 의 변화는 선언에 적힌 것을, 죽음의 굴림은 라운드에 적힌 것을 읽는다. 여기서 굴리지 않는다.
    쓰러져 있는지, 죽었는지는 이번 라운드의 결과를 반영한 뒤의 것이다. 그래서 판정과 죽음의 굴림 뒤에 부른다.
    이 라운드에 새로 들어온 캐릭터는 라운드에 적힌 것(arrivals)으로 안다. 누구의 뒤를 잇는지를 함께 준다.
    ended 는 이 라운드가 닫힐 때 끝난 부상들이다(expire_injuries). 시간이 지나 나은 것을 함께 준다.
    """
    ended = ended or []
    declarations = [find_declaration(round_, member.user_id) for member in table.members]
    wounded = any(member.sheet is not None and injuries.active(member.sheet.injuries) for member in table.members)
    needs_rules = wounded or bool(ended) or any(has_outcome(declaration) for declaration in declarations)
    ruleset = rules_of(table) if needs_rules else None

    moves = []
    for member, declaration in zip(table.members, declarations, strict=True):
        content = declaration.content if declaration else None
        verdict = narration_request.to_verdict(ruleset, declaration) if has_outcome(declaration) else None
        arrival = find_arrival(round_, member.user_id)
        moves.append(
            Move(
                character_name=member.character_name,
                content=content,
                verdict=verdict,
                downed=is_down(member),
                death_save=narration_request.find_death_save(round_, member.user_id),
                dead=sheets.is_dead(member),
                replaces=arrival['replaces'] if arrival else None,
                injuries=worn_notes(ruleset, member),
                healed=healed_notes(ruleset, ended, member.user_id),
                naming=narration_request.to_naming(naming_of(declaration)),
            )
        )
    return moves


def worn_notes(ruleset: Ruleset | None, member: TableMember) -> list[InjuryNote]:
    """이 사람의 지금 캐릭터가 입고 있는 부상들을 서술자에게 줄 모양으로. 규칙을 읽지 않았으면 입은 것이 없다."""
    if ruleset is None or member.sheet is None:
        return []
    return round_injuries.notes(ruleset, member.sheet.injuries)


def frozen_style(table: GameTable, round_: Round) -> NarrationStyle:
    """
    닫는 중인 라운드에 굳혀 둔 문체를 읽는다.

    굳혀 둔 것이 없으면 지금 테이블의 문체다. 굳히기 전에 닫기 시작한 라운드만 그렇다.
    """
    return NarrationStyle(round_.narration_style or table.narration_style)


def frozen_moves(table: GameTable, round_: Round) -> list[Move]:
    """
    닫는 중인 라운드에 굳혀 둔 각자 한 일을 읽는다.

    굳혀 둔 것이 없으면 지금 앉은 사람들로 만든다. 굳히기 전에 닫기 시작한 라운드만 그렇다(마이그레이션 c9e1f3a5b7d8).
    """
    if round_.moves is None:
        return build_moves(table, round_)
    return narration_request.read_moves(round_.moves)


def to_people(cast: list[CastMember], ruleset: Ruleset) -> list[PersonState]:
    """이번 장면의 인물들을 서술자에게 줄 모양으로. 몸 상태를 말로 적는다. 숫자는 주지 않는다. 입은 부상을 함께 준다."""
    return [
        PersonState(
            name=member.name,
            condition=condition_of(member.npc),
            injuries=round_injuries.notes(ruleset, member.npc.injuries),
        )
        for member in cast
    ]
