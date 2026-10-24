# trpg-server/app/rounds/moves.py

"""
닫히는 라운드에서 각자 한 일을 서술자에게 줄 모양(app/rounds/narrator.py)으로 만든다.

닫기 시작할 때 한 번 만들어 라운드에 굳힌다(build_moves). 서술은 지금 앉은 사람이 아니라 굳혀 둔 것을 읽는다
(frozen_moves). 그사이에 누가 나가도 장면에서 빠지지 않는다. 문체도 그때 굳힌다(frozen_style).
판정의 결과와 HP 의 변화, 지목의 결과는 선언에 적힌 것을, 죽음의 굴림은 라운드에 적힌 것을 읽는다. 여기서 굴리지 않는다.
DB 를 모른다.
"""

import uuid
from dataclasses import dataclass

from app.assets.bestiaries.models import MonsterKind
from app.assets.models import NarrationStyle
from app.assets.scenarios.snapshot import CurrencySnapshot, Snapshot, place_entries, read_snapshot
from app.engine.check import find_ability
from app.engine.injury import find_injury
from app.engine.ruleset import Ruleset
from app.rounds import injuries as round_injuries
from app.rounds import narration_request
from app.rounds.cast import CastMember, condition_of
from app.rounds.models import Round
from app.rounds.monster_scene import SceneMonster
from app.rounds.monster_scene import condition as monster_condition
from app.rounds.narrator import HealNote, InjuryNote, ItemNote, MonsterNote, Move, PersonState, PlaceNote, WornNote
from app.rounds.rests import NOTHING, Recovered
from app.rounds.state import (
    find_arrival,
    find_declaration,
    has_outcome,
    is_down,
    naming_of,
    pay_of,
    rules_of,
    trade_of,
)
from app.tables import equipment, injuries, items, money, place_items, places, route_locks, sheets
from app.tables.items import CatalogItem
from app.tables.models import GameTable, TableMember
from app.tables.npc_attitudes import attitude_word


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


def build_moves(
    table: GameTable,
    round_: Round,
    ended: list[round_injuries.Ended] | None = None,
    recovered: Recovered = NOTHING,
    quest_changes: list[dict] | None = None,
    met: list[dict] | None = None,
) -> list[Move]:
    """
    닫히는 라운드에서 각자 한 일을 서술자에게 줄 모양으로 만든다. 닫기 시작할 때 한 번 만들어 라운드에 굳힌다.

    지금 앉아 있는 사람 모두가 들어간다. 선언을 내지 않은 사람은 아무것도 하지 않은 것으로 들어간다.
    판정의 결과와 HP 의 변화는 선언에 적힌 것을, 죽음의 굴림은 라운드에 적힌 것을 읽는다. 여기서 굴리지 않는다.
    쓰러져 있는지, 죽었는지는 이번 라운드의 결과를 반영한 뒤의 것이다. 그래서 판정과 죽음의 굴림 뒤에 부른다.
    이 라운드에 새로 들어온 캐릭터는 라운드에 적힌 것(arrivals)으로 안다. 누구의 뒤를 잇는지를 함께 준다.
    ended 는 이 라운드가 닫힐 때 끝난 부상들이다(expire_injuries). 시간이 지나 나은 것을 함께 준다.
    recovered 는 이 라운드가 닫힐 때의 되살아나기와 저절로 회복이다(app/rounds/rests.py 의 settle).
    quest_changes 는 이 라운드가 닫힐 때 엔진이 바꾼 퀘스트들이다(app/rounds/quest_goals.py). 가져간 물건을 함께 준다.
    met 은 이 라운드가 닫힐 때 무작위 조우로 나온 무리들이다(app/rounds/wanders.py, #283). 그 장소에 선 사람에게 준다.
    쉬는 행동의 결과는 선언에 적혀 있다.
    """
    ended = ended or []
    quest_changes = quest_changes or []
    met = met or []
    declarations = [find_declaration(round_, member.user_id) for member in table.members]
    wounded = any(member.sheet is not None and injuries.active(member.sheet.injuries) for member in table.members)
    needs_rules = wounded or bool(ended) or any(has_outcome(declaration) for declaration in declarations)
    ruleset = rules_of(table) if needs_rules else None
    holding = any(member.sheet is not None and member.sheet.items for member in table.members)
    on_map = any(member.sheet is not None and member.sheet.place_id is not None for member in table.members)
    paying = has_money(table) or any(trade_of(one) or pay_of(one) for one in declarations)
    # 판의 복사본은 통째로 읽는 일이라 싸지 않다. 소지품이나 맵이나 돈이 있을 때만 한 번 읽는다
    snapshot = read_snapshot(table.content) if holding or on_map or paying else None
    catalog = items.catalog(snapshot) if snapshot is not None else {}
    mapping = map_view(table, snapshot, catalog) if on_map else None
    currency = snapshot.currency if snapshot is not None else None

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
                lost_turn=declaration.outcome.get('turn_lost') if declaration and declaration.outcome else None,
                replaces=arrival['replaces'] if arrival else None,
                injuries=worn_notes(ruleset, member),
                healed=healed_notes(ruleset, ended, member.user_id),
                naming=narration_request.to_naming(naming_of(declaration)),
                item_action=narration_request.to_item_action(declaration),
                throw=narration_request.to_throw(declaration),
                items=held_notes(catalog, member),
                worn=worn_notes_of(snapshot, catalog, member),
                travel=narration_request.to_travel(declaration, snapshot.rulebook.rules if snapshot else None),
                search=narration_request.to_search(declaration),
                door=narration_request.to_door(declaration, snapshot.rulebook.rules if snapshot else None),
                take=narration_request.to_take(declaration),
                put_down=narration_request.to_put_down(declaration),
                steal=narration_request.to_steal(declaration),
                loot=narration_request.to_loot(declaration),
                trade=narration_request.to_trade(declaration, currency),
                pay=narration_request.to_pay(declaration, currency),
                money=money_note(currency, member),
                handed_over=narration_request.find_handed_over(quest_changes, member.user_id),
                target_gone=narration_request.to_target_gone(declaration),
                rest=narration_request.to_rest(declaration),
                wait=narration_request.to_wait(declaration),
                cover=narration_request.to_cover(declaration),
                revival=narration_request.find_revival(recovered.revivals, member.user_id),
                recovery=narration_request.find_recovery(recovered.natural, member.user_id),
                place=place_note(mapping, member),
                wander=narration_request.find_wander(met, member.sheet.place_id if member.sheet else None),
            )
        )
    return moves


@dataclass(frozen=True)
class MapView:
    """
    이 라운드의 행동까지 반영한 뒤에 테이블이 아는 맵과, 판의 장소 이름들. 캐릭터마다 서 있는 곳을 적을 때 함께 쓴다.

    아는 맵에는 이 라운드에 찾은 숨긴 길이 들어 있다. 찾기와 가기를 판정한 뒤에 만든다.
    table 은 장소에 남은 물건(app/tables/place_items.py)을, catalog 는 판의 물건의 이름을 찾는다.
    """

    table: GameTable
    snapshot: Snapshot
    known: places.KnownMap | None
    knowledge: places.Knowledge
    names: dict[uuid.UUID, str]
    catalog: dict[uuid.UUID, CatalogItem]


def map_view(table: GameTable, snapshot: Snapshot, catalog: dict[uuid.UUID, CatalogItem]) -> MapView:
    """테이블이 지금 아는 맵을 읽는다. 맵이 없는 판이면 아는 맵이 None 이다."""
    knowledge = places.knowledge(table)
    names = {entry.id: entry.name for entry in place_entries(snapshot)}
    return MapView(table, snapshot, places.known_map(snapshot, knowledge), knowledge, names, catalog)


def item_notes_at(mapping: MapView, place_id: uuid.UUID) -> list[ItemNote]:
    """그 장소에 보이게 놓인 물건들을 서술자에게 줄 모양으로. 같은 물건은 합친다."""
    return [
        ItemNote(name=mapping.catalog[pile.entry_id].name, count=pile.count)
        for pile in place_items.piles_at(mapping.table, place_id)
    ]


def hidden_item_names(mapping: MapView, place_id: uuid.UUID) -> list[str]:
    """그 장소에 아직 찾지 않은 숨긴 물건의 이름들. GM 만 안다. 같은 이름은 한 번만 적는다."""
    names = [mapping.catalog[row.entry_id].name for row in place_items.hidden_rows(mapping.table, place_id)]
    return list(dict.fromkeys(names))


def exit_name(mapping: MapView, here: uuid.UUID, there: uuid.UUID) -> str:
    """
    나가는 길 하나의 이름. 길의 조건이 있으면 이름 뒤에 붙인다(#281).

    예: 광장, 탑(잠긴 문), 절벽 위(넘기: 근력), 창고(빗장 걸림), 지하실(부서진 문).
    무슨 열쇠인지와 실패의 피해는 적지 않는다.
    """
    route = places.route_between(mapping.known, here, there)
    marks = []
    if route_locks.is_broken(mapping.table, route):
        marks.append('부서진 문')
    if route_locks.is_barred(mapping.table, route):
        marks.append('빗장 걸림')
    if route_locks.is_locked(mapping.table, route):
        marks.append('잠긴 문')
    if route.cross is not None:
        ability = find_ability(mapping.snapshot.rulebook.rules, route.cross.ability)
        marks.append(f'넘기: {ability.name}')
    return f'{mapping.names[there]}({", ".join(marks)})' if marks else mapping.names[there]


def place_note(mapping: MapView | None, member: TableMember) -> PlaceNote | None:
    """
    이 사람의 지금 캐릭터가 서 있는 곳을 서술자에게 줄 모양으로. 맵에 서 있지 않으면 None.

    아는 길로 갈 수 있는 곳(exits)과, 그곳에 닿은 아직 찾지 않은 숨긴 길의 다른 끝(hidden)을 함께 준다.
    그곳에 보이게 놓인 물건(items)과 아직 찾지 않은 숨긴 물건(hidden_items)도 준다.
    hidden 과 hidden_items 는 GM 만 안다. 언어 모델의 맵 절에만 들어간다(app/rounds/prompt.py).
    """
    if mapping is None or member.sheet is None or member.sheet.place_id is None:
        return None
    here = member.sheet.place_id
    exits = places.exits(mapping.known, here)
    hidden = places.hidden_routes_at(mapping.snapshot, mapping.knowledge, here)
    return PlaceNote(
        name=mapping.names[here],
        exits=[exit_name(mapping, here, place) for place in exits],
        hidden=[mapping.names[route.to_place if route.from_place == here else route.from_place] for route in hidden],
        items=item_notes_at(mapping, here),
        hidden_items=hidden_item_names(mapping, here),
    )


def held_notes(catalog: dict[uuid.UUID, CatalogItem], member: TableMember) -> list[ItemNote]:
    """이 사람의 지금 캐릭터가 가진 물건들을 서술자에게 줄 모양으로. 판의 물건 순서다."""
    if member.sheet is None:
        return []
    rows = items.in_catalog_order(member.sheet.items, catalog)
    return [ItemNote(name=catalog[item.entry_id].name, count=item.count) for item in rows]


def worn_notes_of(
    snapshot: Snapshot | None, catalog: dict[uuid.UUID, CatalogItem], member: TableMember
) -> list[WornNote]:
    """이 사람의 지금 캐릭터가 착용한 물건들을 서술자에게 줄 모양으로(#276). 규칙의 칸의 차례, 칸은 이름이다."""
    if snapshot is None or member.sheet is None:
        return []
    rules = snapshot.rulebook.rules
    rows = equipment.in_slot_order(member.sheet.worn, rules)
    return [WornNote(name=catalog[row.entry_id].name, slots=equipment.slot_names(rules, row.slots)) for row in rows]


def has_money(table: GameTable) -> bool:
    """앉은 사람 중 누가 돈을 가졌는가(#278). 돈이 없는 판의 테이블은 늘 거짓이다."""
    return any(member.sheet is not None and member.sheet.money > 0 for member in table.members)


def money_note(currency: CurrencySnapshot | None, member: TableMember) -> str | None:
    """이 사람의 지금 캐릭터가 가진 돈의 글(금화 30닢). 돈이 없는 판이거나 판을 읽지 않았으면 None."""
    if currency is None or member.sheet is None:
        return None
    return money.money_text(currency, member.sheet.money)


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


def to_people(
    cast: list[CastMember], ruleset: Ruleset, places: dict[uuid.UUID, str] | None = None
) -> list[PersonState]:
    """
    이번 장면의 인물들을 서술자에게 줄 모양으로. 몸 상태를 말로 적는다. 숫자는 주지 않는다. 입은 부상을 함께 준다.

    places 는 판의 장소 항목의 이름이다. 자리가 있는 인물에는 있는 장소의 이름을 붙인다(#282).
    """
    names = places or {}
    return [
        PersonState(
            name=member.name,
            condition=condition_of(member.npc),
            injuries=round_injuries.notes(ruleset, member.npc.injuries),
            attitude=attitude_word(member.npc),
            place=names.get(member.npc.place_id),
        )
        for member in cast
    ]


def place_names(snapshot: Snapshot) -> dict[uuid.UUID, str]:
    """판의 장소 항목마다 이름."""
    return {entry.id: entry.name for entry in place_entries(snapshot)}


# 몬스터의 타입을 서술자에게 보일 말. 기타는 적지 않는다
MONSTER_KINDS = {
    MonsterKind.HUMANOID: '인간형',
    MonsterKind.BEAST: '야수',
    MonsterKind.UNDEAD: '언데드',
    MonsterKind.CONSTRUCT: '구조물',
}


def monster_note(monsters: list[SceneMonster], place: str) -> MonsterNote:
    """
    같은 장소의 같은 몬스터 마리들(네임드면 한 마리)을 서술자에게 줄 모양으로. 마리마다의 몸 상태를 번호 순서로 준다.
    """
    definition = monsters[0].definition
    return MonsterNote(
        name=definition.name,
        kind=MONSTER_KINDS.get(definition.kind, ''),
        content=definition.content,
        place=place,
        unique=definition.unique,
        conditions=[monster_condition(monster) for monster in monsters],
    )


def to_monster_notes(snapshot: Snapshot, monsters: list[SceneMonster]) -> list[MonsterNote]:
    """
    이번 장면의 몬스터들을 서술자에게 줄 모양으로. 같은 장소의 같은 몬스터를 하나로 모은다. 장면의 순서다.

    네임드 몹은 판 전체에서 한 마리라 늘 혼자다. 일반 몹은 종류와 마리마다의 몸 상태만 준다.
    숫자(HP, 능력치)는 주지 않는다.
    """
    if not monsters:
        return []
    names = {entry.id: entry.name for entry in place_entries(snapshot)}
    groups: dict[tuple, list[SceneMonster]] = {}
    for monster in monsters:
        groups.setdefault((monster.state.place_id, monster.state.monster_id), []).append(monster)
    return [monster_note(group, names.get(place_id, '')) for (place_id, _), group in groups.items()]
