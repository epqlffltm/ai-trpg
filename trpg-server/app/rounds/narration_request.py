# trpg-server/app/rounds/narration_request.py

"""
DB 에 적힌 라운드를 서술자에게 줄 모양(app/rounds/narrator.py)으로 바꾼다. 그리고 그 모양을 저장하고 다시 읽는다.

서술자에게 주는 것은 셋이다.
  - 이번 라운드에 각자 한 일(moves). 닫기 시작할 때 만들어 라운드에 굳혀 둔다(dump_moves, read_moves).
  - 이야기의 바탕(story). 판의 복사본에서 꺼낸다. 판은 고치지 않으므로 굳힐 필요가 없다.
  - 지난 라운드들(history). 닫힌 라운드는 바뀌지 않으므로 굳힐 필요가 없다.
    한 말은 그 라운드에 굳혀 둔 각자 한 일에서 읽는다(to_past). 서술자가 그때 받은 것과 같은 사람들이다.

각자 한 일을 굳히는 이유. 서술은 저장한 뒤에 따로 돈다(app/rounds/closing.py).
그 사이에 누가 나가거나, 서술이 실패해서 다시 맡기면, 지금의 테이블로 다시 만든 것은 닫힐 때와 다르다.
나간 사람의 판정과 HP 의 변화는 기록에 있는데 장면에서는 빠진다. 굳혀 두면 몇 번을 맡겨도 같은 것을 받는다.

여기의 함수는 DB 도 테이블도 모른다. 이미 읽어 온 라운드, 선언, 판의 복사본을 받아 모양만 바꾼다.
"""

import uuid
from collections.abc import Iterable, Mapping, Set
from dataclasses import asdict

from pydantic import TypeAdapter

from app.assets.models import NpcAttitude
from app.assets.scenarios.snapshot import CurrencySnapshot, Snapshot, person_entries, place_entries, quest_entries
from app.calendar import clock, state
from app.engine.check import find_ability, find_difficulty
from app.engine.injury import known_injuries
from app.engine.resources import band_of
from app.engine.ruleset import Ruleset
from app.rounds.drops import NPC_SOURCE
from app.rounds.models import Declaration, Round
from app.rounds.narrator import (
    AidNote,
    BlowNote,
    ClockNote,
    CoverNote,
    DeathSaveNote,
    DoorNote,
    DownedStrikeNote,
    DropNote,
    DroppedNote,
    HandOverNote,
    HappeningNote,
    Impact,
    ItemActionNote,
    ItemNote,
    LootNote,
    MonsterTurnNote,
    Move,
    NamingNote,
    NpcImpact,
    PastRound,
    PayNote,
    PutDownNote,
    QuestNote,
    RecoveryNote,
    ResourceNote,
    RestNote,
    RevivalNote,
    SearchNote,
    SkillNote,
    StealNote,
    StoryContext,
    TakeNote,
    TargetGoneNote,
    ThrowNote,
    TradeNote,
    TrapNote,
    TrapSetNote,
    TravelNote,
    TreatmentNote,
    TurnNote,
    Verdict,
    WaitNote,
    WakeNote,
    WanderNote,
    WhisperNote,
)
from app.rounds.secret_names import secret_names
from app.rounds.state import (
    cover_of,
    door_of,
    has_outcome,
    item_throw_of,
    loot_of,
    move_of,
    pay_of,
    put_down_of,
    rest_of,
    search_of,
    steal_of,
    take_of,
    trade_of,
    trap_set_of,
    wait_of,
)
from app.tables import money, quests
from app.tables.models import GameTable, QuestStatus, TableHappening, TableNpc, TableQuest
from app.tables.npc_attitudes import ATTITUDE_WORDS
from app.tables.quests import CatalogQuest
from app.whispers.models import Whisper

# 굳혀 둔 행동들을 읽는 법. 모양이 틀리면 ValidationError 를 낸다. 우리가 쓴 문서이니 틀렸으면 버그다
MOVES = TypeAdapter(list[Move])


def find_death_save(round_: Round, user_id: uuid.UUID) -> DeathSaveNote | None:
    """라운드에 적힌 죽음의 굴림 중에서 이 사람의 것을 서술자에게 줄 모양으로 찾는다. 없으면 None."""
    found = next((save for save in round_.death_saves if save['user_id'] == str(user_id)), None)
    if found is None:
        return None
    return DeathSaveNote(
        roll=found['roll'],
        target=found['target'],
        success=found['success'],
        successes=found['successes'],
        failures=found['failures'],
        fate=found['fate'],
    )


def new_injury_name(effect: dict) -> str | None:
    """HP 의 변화를 적은 문서에서 새로 입은 부상의 이름. 표를 굴리지 않았거나 부상이 없었거나 면역이었으면 None."""
    injury_roll = effect.get('injury_roll')
    return injury_roll['name'] if injury_roll and injury_roll['injury'] else None


def resisted_injury_name(effect: dict) -> str | None:
    """HP 의 변화를 적은 문서에서 면역이나 저항으로 막아 입지 않은 부상의 이름(#799, #886 ②). 없으면 None."""
    injury_roll = effect.get('injury_roll')
    return injury_roll['name'] if injury_roll and injury_roll.get('immune') else None


def nature_name(effect: dict) -> str | None:
    """HP 의 변화를 적은 문서에서 피해의 성질의 이름(#886 ③). 없으면 None."""
    nature = effect.get('nature')
    return nature['name'] if nature else None


def nature_level(effect: dict) -> str | None:
    """HP 의 변화를 적은 문서에서 맞은 쪽이 그 성질을 받은 단계(#886 ③). 그대로 받았거나 성질이 없으면 None."""
    nature = effect.get('nature')
    return nature['level'] if nature else None


def spared_injury_name(effect: dict) -> str | None:
    """HP 의 변화를 적은 문서에서 동료의 장난이라 입지 않은 부상의 이름(#803). 없으면 None."""
    injury_roll = effect.get('injury_roll')
    return injury_roll['name'] if injury_roll and injury_roll.get('spared') else None


def to_impact(effect: dict | None) -> Impact | None:
    """선언에 적힌 HP 의 변화를 서술자에게 줄 모양으로 바꾼다. 변화가 없었으면 None."""
    if effect is None:
        return None
    return Impact(
        kind=effect['kind'],
        character_name=effect['character_name'],
        amount=effect['amount'],
        hp=effect['after'],
        max_hp=effect['max_hp'],
        downed=effect['downed'],
        injury=new_injury_name(effect),
        prank=effect.get('prank', False),
        spared=spared_injury_name(effect),
        resisted=resisted_injury_name(effect),
        nature=nature_name(effect),
        level=nature_level(effect),
    )


def to_shift_note(shift: dict) -> ResourceNote:
    """
    바뀐 수치 하나(#804)를 서술자에게 줄 모양으로. 숨긴 수치는 바뀐 뒤를 네 단계의 말로만 준다.

    보이기와 최소가 없는 옛 문서는 모두가 보는 것, 최소 0 으로 읽는다.
    저항으로 막아 낸 것(#886 ②)은 막았다는 것만 준다.
    """
    if shift.get('resisted'):
        return ResourceNote(name=shift['name'], resisted=True)
    if shift.get('visibility', 'everyone') != 'everyone':
        return ResourceNote(name=shift['name'], word=band_of(shift['after'], shift.get('min', 0), shift['max']))
    return ResourceNote(name=shift['name'], value=shift['after'], max=shift['max'], before=shift['before'])


def to_shift_notes(shifts: list[dict] | None) -> list[ResourceNote]:
    """바뀐 수치들(#804)을 서술자에게 줄 모양으로. 쉬기와 물건의 맞추기가 적은 것이다."""
    return [to_shift_note(one) for one in shifts or []]


def spared_names(injured: list[dict]) -> list[str]:
    """물건이 입히려던 부상 중 동료의 장난이라 입지 않은 것의 이름들(#803)."""
    return [one['name'] for one in injured if one.get('spared')]


def other_name(declaration: Declaration, target: dict | None) -> str | None:
    """
    물건을 받거나 회복받은 쪽의 이름. 없거나 선언한 사람 자신이면 None 이다.

    앉은 사람이면 캐릭터 이름, 인물이나 몬스터(#800)면 장면에서 부르는 이름이다.
    """
    if target is None or target.get('user_id') == str(declaration.user_id):
        return None
    return target.get('character_name') or target.get('name')


def to_skill(declaration: Declaration | None) -> SkillNote | None:
    """
    선언에 적힌 기술 쓰기의 결과(#805)를 서술자에게 줄 모양으로 바꾼다. 그런 행동이 아니면 None.

    굴린 기술(#805 ②)이면 HP 의 변화는 판정의 줄이 적는다. 여기서는 싣지 않는다.
    """
    if declaration is None or declaration.outcome is None:
        return None
    used = declaration.outcome.get('skill_use')
    if used is None:
        return None
    injured = used.get('injured') or []
    return SkillNote(
        name=used['name'],
        done=used['used'],
        reason=used['reason'],
        target=other_name(declaration, used['target']),
        cost=to_shift_notes(used.get('cost')),
        impact=None if has_outcome(declaration) else to_impact(declaration.outcome.get('effect')),
        rolled=has_outcome(declaration),
        cured=[one['name'] for one in used.get('cured') or []],
        injured=[one['name'] for one in injured if one['injury'] is not None],
        resisted=[one['name'] for one in injured if one.get('immune')],
        spared=spared_names(injured),
        resources=to_shift_notes(used.get('resources')),
    )


def to_item_action(declaration: Declaration | None) -> ItemActionNote | None:
    """선언에 적힌 물건 쓰기나 건네기의 결과를 서술자에게 줄 모양으로 바꾼다. 그런 행동이 아니면 None."""
    if declaration is None or declaration.outcome is None:
        return None
    used = declaration.outcome.get('item_use')
    if used is not None:
        return ItemActionNote(
            kind='use',
            name=used['name'],
            count=1,
            done=used['used'],
            reason=used['reason'],
            target=other_name(declaration, used['target']),
            impact=to_impact(declaration.outcome.get('effect')),
            cured=[one['name'] for one in used.get('cured') or []],
            injured=[one['name'] for one in used.get('injured') or [] if one['injury'] is not None],
            resisted=[one['name'] for one in used.get('injured') or [] if one.get('immune')],
            spared=spared_names(used.get('injured') or []),
            resources=to_shift_notes(used.get('resources')),
        )
    given = declaration.outcome.get('item_give')
    if given is not None:
        return ItemActionNote(
            kind='give',
            name=given['name'],
            count=given['count'],
            done=given['given'],
            reason=given['reason'],
            target=given['target']['character_name'],
        )
    return None


def to_throw(declaration: Declaration | None) -> ThrowNote | None:
    """선언에 적힌 물건 던지기의 결과를 서술자에게 줄 모양으로 바꾼다(#277). 던지는 행동이 아니면 None."""
    thrown = item_throw_of(declaration)
    if thrown is None:
        return None
    injured = thrown.get('injured') or []
    return ThrowNote(
        name=thrown['name'],
        target=thrown['target']['name'],
        done=thrown['thrown'],
        reason=thrown['reason'],
        cured=[one['name'] for one in thrown.get('cured') or []],
        injured=[one['name'] for one in injured if one['injury'] is not None],
        resisted=[one['name'] for one in injured if one.get('immune')],
        spared=spared_names(injured),
        resources=to_shift_notes(thrown.get('resources')),
    )


def place_name(place: dict | None) -> str | None:
    """결과에 적힌 장소의 이름. 없으면 None."""
    return place['name'] if place else None


def cross_ability_name(ruleset: Ruleset | None, cross: dict | None) -> str | None:
    """길을 넘는 판정의 능력치의 이름(#281). 굴리지 않았으면 None. 규칙에서 찾지 못하면 이름표 그대로다."""
    if cross is None:
        return None
    ability = find_ability(ruleset, cross['ability']) if ruleset is not None else None
    return ability.name if ability is not None else cross['ability']


def to_travel(declaration: Declaration | None, ruleset: Ruleset | None = None) -> TravelNote | None:
    """
    선언에 적힌 가기의 결과를 서술자에게 줄 모양으로 바꾼다. 가는 행동이 아니면 None.

    ruleset 은 길을 넘는 판정의 능력치의 이름을 찾는다(#281).
    """
    move = move_of(declaration)
    if move is None:
        return None
    carry = move.get('carry') or {}
    return TravelNote(
        from_place=place_name(move['from']),
        to_place=move['to']['name'],
        moved=move['moved'],
        reason=move['reason'],
        travel_minutes=move.get('travel_minutes'),
        carried=carry.get('character_name'),
        carry_reason=carry.get('reason'),
        unlocked=move.get('unlocked', False),
        cross=cross_ability_name(ruleset, move.get('cross')),
        hurt=move.get('effect') is not None,
        unbarred=move.get('unbarred', False),
        aid=to_aid(move.get('aid')),
        traps=[to_trap(trap, ruleset) for trap in move.get('traps', [])],
    )


def to_trap(trap: dict, ruleset: Ruleset | None) -> TrapNote:
    """가기의 결과에 적힌 터진 덫 하나를 서술자에게 줄 모양으로 바꾼다(#806)."""
    return TrapNote(
        name=trap['name'],
        check=cross_ability_name(ruleset, trap['avoid']),
        avoided=trap['avoided'],
    )


def to_door(declaration: Declaration | None, ruleset: Ruleset | None = None) -> DoorNote | None:
    """
    선언에 적힌 문 다루기의 결과를 서술자에게 줄 모양으로 바꾼다(#281). 문을 다루는 행동이 아니면 None.

    ruleset 은 따기, 부수기, 고치기의 판정의 능력치의 이름을 찾는다.
    """
    door = door_of(declaration)
    if door is None:
        return None
    return DoorNote(
        act=door['act'],
        other_end=door['to']['name'],
        done=door['done'],
        device=door['device'],
        reason=door['reason'],
        check=cross_ability_name(ruleset, door['check']),
        aid=to_aid(door.get('aid')),
    )


def to_aid(aid: dict | None) -> AidNote | None:
    """행동에 붙여 쓴 물건을 서술자에게 줄 모양으로(#802). 붙이지 않았거나 쓰지 못했으면(굴리지 않음, 더 없음) None."""
    if aid is None or not aid['used']:
        return None
    return AidNote(name=aid['name'], bonus=aid['bonus'], broken=aid.get('broken', False))


def to_rest(declaration: Declaration | None) -> RestNote | None:
    """선언에 적힌 쉬기의 결과를 서술자에게 줄 모양으로 바꾼다. 쉬는 행동이 아니면 None."""
    rest = rest_of(declaration)
    if rest is None:
        return None
    return RestNote(
        length=rest['length'],
        rested=rest['rested'],
        reason=rest['reason'],
        before=rest['before'],
        after=rest['after'],
        max_hp=rest['max_hp'],
        resources=to_shift_notes(rest.get('resources')),
    )


def to_wait(declaration: Declaration | None) -> WaitNote | None:
    """선언에 적힌 기다리기의 결과를 서술자에게 줄 모양으로 바꾼다. 기다리는 행동이 아니면 None."""
    wait = wait_of(declaration)
    if wait is None:
        return None
    return WaitNote(minutes=wait['minutes'], waited=wait['waited'], reason=wait['reason'])


def to_cover(declaration: Declaration | None) -> CoverNote | None:
    """선언에 적힌 엄폐하기의 결과를 서술자에게 줄 모양으로 바꾼다. 엄폐하는 행동이 아니면 None."""
    cover = cover_of(declaration)
    if cover is None:
        return None
    place = cover['place']
    return CoverNote(place=place['name'] if place else None, value=cover['value'])


def find_wander(met: list[dict], place_id: uuid.UUID | None) -> WanderNote | None:
    """
    이 라운드가 닫힐 때 그 장소에 무작위 조우로 나온 무리(app/rounds/wanders.py, #283). 없으면 None.

    한 장소에는 한 라운드에 무리가 하나다. 맵에 서 있지 않으면(place_id 가 None) 없다.
    """
    one = next((one for one in met if place_id is not None and one['place']['entry_id'] == str(place_id)), None)
    if one is None:
        return None
    return WanderNote(monster=one['monster']['name'], count=one['count'], cause=one['cause'])


def find_revival(revivals: list[dict], user_id: uuid.UUID) -> RevivalNote | None:
    """이 라운드가 닫힐 때 그 사람이 굴린 되살아나기(app/rounds/rests.py 의 revive_all). 없으면 None."""
    found = next((one for one in revivals if one['user_id'] == str(user_id)), None)
    return None if found is None else RevivalNote(success=found['success'], hp=found['hp'])


def find_recovery(natural: list[dict], user_id: uuid.UUID) -> RecoveryNote | None:
    """이 라운드가 닫힐 때 그 사람이 저절로 회복한 것(app/rounds/rests.py 의 natural_all). 없으면 None."""
    found = next((one for one in natural if one['user_id'] == str(user_id)), None)
    if found is None:
        return None
    return RecoveryNote(before=found['before'], after=found['after'], max_hp=found['max_hp'])


def find_handed_over(changes: list[dict], user_id: uuid.UUID) -> list[HandOverNote]:
    """
    이 라운드가 닫힐 때 이룬 퀘스트들이 그 사람에게서 가져간 물건들(app/rounds/quest_goals.py). 없으면 빈 목록.

    changes 는 엔진이 바꾼 퀘스트들(quest_changed 의 모양)이다. 바뀐 차례다.
    """
    return [
        HandOverNote(quest=change['name'], name=thing['name'], count=thing['count'])
        for change in changes
        for giver in change.get('consumed', [])
        if giver['user_id'] == str(user_id)
        for thing in giver['items']
    ]


def other_end(route: dict, place: dict | None) -> str:
    """찾은 길에서 찾은 곳의 맞은편 장소의 이름. 길이 어디로 이어지는지다."""
    if place is not None and route['from_place']['entry_id'] == place['entry_id']:
        return route['to_place']['name']
    return route['from_place']['name']


def to_search(declaration: Declaration | None) -> SearchNote | None:
    """
    선언에 적힌 찾기의 결과를 서술자에게 줄 모양으로 바꾼다. 찾는 행동이 아니면 None. 찾은 길과 가진 물건만 있다.

    물건을 찾기 전(#279)에 굳힌 결과에는 items 가 없다. 찾은 물건이 없던 것과 같다.
    """
    search = search_of(declaration)
    if search is None:
        return None
    place = search['place']
    return SearchNote(
        place=place_name(place),
        found=[other_end(route, place) for route in search['found']],
        items=[ItemNote(name=one['name'], count=one['count']) for one in search.get('items', []) if one['count']],
    )


def to_take(declaration: Declaration | None) -> TakeNote | None:
    """선언에 적힌 줍기의 결과를 서술자에게 줄 모양으로 바꾼다. 줍는 행동이 아니면 None."""
    take = take_of(declaration)
    if take is None:
        return None
    return TakeNote(name=take['name'], count=take['count'], taken=take['taken'], reason=take['reason'])


def to_put_down(declaration: Declaration | None) -> PutDownNote | None:
    """선언에 적힌 내려놓기의 결과를 서술자에게 줄 모양으로 바꾼다. 내려놓는 행동이 아니면 None."""
    put_down = put_down_of(declaration)
    if put_down is None:
        return None
    return PutDownNote(name=put_down['name'], count=put_down['count'], put=put_down['put'])


def to_trap_set(declaration: Declaration | None) -> TrapSetNote | None:
    """선언에 적힌 덫 놓기의 결과를 서술자에게 줄 모양으로 바꾼다(#806). 덫을 놓는 행동이 아니면 None."""
    trap_set = trap_set_of(declaration)
    if trap_set is None:
        return None
    return TrapSetNote(name=trap_set['name'], set=trap_set['set'])


def to_steal(declaration: Declaration | None) -> StealNote | None:
    """선언에 적힌 훔치기의 결과를 서술자에게 줄 모양으로 바꾼다. 훔치는 행동이 아니면 None."""
    steal = steal_of(declaration)
    if steal is None:
        return None
    caught = not steal['stolen'] and steal['check'] is not None
    npc = steal.get('npc_id') is not None
    return StealNote(
        victim=steal['npc_name'] if npc else steal['monster_name'],
        name=steal['name'],
        count=steal['count'],
        stolen=steal['stolen'],
        caught=caught,
        npc=npc,
        hostile=steal.get('attitude_change') is not None,
        fight=steal.get('fight', False),
    )


def to_loot(declaration: Declaration | None) -> LootNote | None:
    """선언에 적힌 빼앗기의 결과를 서술자에게 줄 모양으로 바꾼다. 빼앗는 행동이 아니면 None."""
    loot = loot_of(declaration)
    if loot is None:
        return None
    victim = loot['npc_name'] if loot['npc_id'] is not None else loot['monster_name']
    return LootNote(victim=victim, name=loot['name'], count=loot['count'], looted=loot['looted'], reason=loot['reason'])


def to_trade(declaration: Declaration | None, currency: CurrencySnapshot | None) -> TradeNote | None:
    """선언에 적힌 사기나 팔기의 결과를 서술자에게 줄 모양으로 바꾼다. 그런 행동이 아니면 None."""
    trade = trade_of(declaration)
    if trade is None or currency is None:
        return None
    return TradeNote(
        side=trade['side'],
        merchant=trade['npc_name'],
        name=trade['name'],
        count=trade['count'],
        price=money.money_text(currency, trade['price']),
        traded=trade['traded'],
        reason=trade['reason'],
    )


def to_pay(declaration: Declaration | None, currency: CurrencySnapshot | None) -> PayNote | None:
    """선언에 적힌 돈 건네기의 결과를 서술자에게 줄 모양으로 바꾼다. 그런 행동이 아니면 None."""
    paid = pay_of(declaration)
    if paid is None or currency is None:
        return None
    return PayNote(
        amount=money.money_text(currency, paid['amount']),
        target=paid['target']['character_name'],
        paid=paid['paid'],
        reason=paid['reason'],
    )


def to_npc_impact(effect: dict | None) -> NpcImpact | None:
    """
    선언에 적힌 NPC 의 HP 의 변화를 서술자에게 줄 모양으로 바꾼다. 변화가 없었으면 None.

    몸 상태는 바뀐 뒤의 것이다. 바꿀 때 적어 둔 것을 읽는다(app/rounds/checks.py 의 change_cast_member).
    """
    if effect is None:
        return None
    return NpcImpact(
        kind=effect['kind'],
        name=effect['name'],
        amount=effect['amount'],
        condition=effect['condition'],
        injury=new_injury_name(effect),
        resisted=resisted_injury_name(effect),
        nature=nature_name(effect),
        level=nature_level(effect),
    )


def to_drop(drop: dict | None) -> DropNote | None:
    """
    선언에 적힌 드롭을 서술자에게 줄 모양으로 바꾼다. 드롭이 없었으면 None.

    받을 사람이 없어 사라진 드롭도 None 이다. 아무도 얻지 않았으니 장면에 쓸 것이 없다.
    받은 것도 잃은 것도 없는 물건은 뺀다.
    """
    if drop is None or drop['user_id'] is None:
        return None
    things = [DroppedNote(name=one['name'], count=one['count'], lost=one['lost']) for one in drop['items']]
    holder = drop['npc_name'] if drop['source'] == NPC_SOURCE else drop['monster_name']
    return DropNote(holder=holder, receiver=drop['character_name'], items=things)


def to_wake(wake: dict | None) -> WakeNote | None:
    """
    선언에 적힌 깨어날 때의 반응을 서술자에게 줄 모양으로 바꾼다. 태도가 바뀌지 않았으면 None.

    눈치채지 못한 것은 주지 않는다. 그 인물이 모르는 것이라 장면에 쓸 것이 없다.
    """
    if wake is None or wake['attitude_change'] is None:
        return None
    return WakeNote(name=wake['name'], attitude=ATTITUDE_WORDS[NpcAttitude(wake['attitude_change']['attitude'])])


def check_terms(declaration: Declaration) -> tuple[str, str]:
    """
    판정에 쓴 능력과 난이도의 key. 판정하는 행동은 행동에 적혀 있고, 치료는 규칙이 정해 결과에 적혀 있다.
    던지기는 물건에 적혀 결과에 옮겨 적혀 있다(#277). 인물이나 몬스터에게 물건을 쓴 것은 룰북이 정해 결과에
    옮겨 적혀 있다(#800). 굴린 기술도 기술이나 룰북이 정해 결과에 옮겨 적혀 있다(#805 ②).

    결과가 적힌 선언에만 쓴다.
    """
    treatment = declaration.outcome.get('treatment')
    if treatment is not None:
        return treatment['ability'], treatment['difficulty']
    thrown = declaration.outcome.get('item_throw')
    if thrown is not None:
        return thrown['ability'], thrown['difficulty']
    used = declaration.outcome.get('item_use')
    if used is not None:
        return used['ability'], used['difficulty']
    skill = declaration.outcome.get('skill_use')
    if skill is not None:
        return skill['ability'], skill['difficulty']
    return declaration.action['ability'], declaration.action['difficulty']


def patient_name(holder: dict) -> str:
    """치료받은 쪽을 부르는 이름. 캐릭터면 캐릭터 이름, NPC 면 장면의 호칭이다."""
    return holder.get('character_name') or holder.get('name') or ''


def to_treatment(treatment: dict | None) -> TreatmentNote | None:
    """선언에 적힌 치료의 결과를 서술자에게 줄 모양으로 바꾼다. 치료가 아니면 None."""
    if treatment is None:
        return None
    mishap = treatment['mishap']
    aftermath = treatment['aftermath']
    return TreatmentNote(
        injury=treatment['name'],
        patient=patient_name(treatment['patient']),
        treated=treatment['treated'],
        healed=treatment['healed'],
        minutes_left=treatment.get('minutes_left'),
        aftermath=aftermath['name'] if aftermath else None,
        mishap=mishap['kind'] if mishap else None,
        worsened_minutes=mishap.get('delay_minutes') if mishap else None,
        died=treatment['died'],
        aid=to_aid(treatment.get('aid')),
    )


def to_naming(naming: dict | None) -> NamingNote | None:
    """선언에 적힌 지목의 결과를 서술자에게 줄 모양으로 바꾼다. 지목이 아니면 None."""
    if naming is None:
        return None
    return NamingNote(guess=naming['guess'], correct=naming['correct'], name=naming['name'], label=naming['label'])


def to_verdict(ruleset: Ruleset, declaration: Declaration) -> Verdict:
    """
    선언에 적힌 행동과 결과를 서술자에게 줄 모양으로 바꾼다. key 를 규칙에 적힌 이름으로 바꾼다.

    결과가 적힌 선언에만 쓴다.
    """
    ability_key, difficulty_key = check_terms(declaration)
    ability = find_ability(ruleset, ability_key)
    difficulty = find_difficulty(ruleset, difficulty_key)
    outcome = declaration.outcome
    return Verdict(
        ability=ability.name,
        difficulty=difficulty.name,
        roll=outcome['roll'],
        modifier=outcome['modifier'],
        total=outcome['total'],
        target=outcome['target'],
        success=outcome['success'],
        impact=to_impact(outcome.get('effect')),
        npc_impact=to_npc_impact(outcome.get('npc_effect')),
        monster_impact=to_npc_impact(outcome.get('monster_effect')),
        drop=to_drop(outcome.get('drop')),
        wake=to_wake(outcome.get('wake')),
        hindrances=hindrance_names(ruleset, outcome.get('hindrance')),
        aimed=aimed_name(ruleset, outcome.get('called_shot')),
        treatment=to_treatment(outcome.get('treatment')),
        blow=to_blow(outcome.get('blow')),
    )


def to_blow(blow: dict | None) -> BlowNote | None:
    """판정이나 차례에 적힌 장비가 든 것(#276)을 서술자에게 줄 모양으로. 없으면 None."""
    if blow is None:
        return None
    weapon = blow['weapon']
    pierce = blow.get('pierce')
    save = blow.get('save')
    return BlowNote(
        weapon=weapon['name'] if weapon else None,
        weapon_bonus=weapon['bonus'] if weapon else 0,
        location=blow['location_name'],
        aimed=blow['aimed'],
        defense=blow['defense'],
        mode=blow['mode'],
        pierced=pierce['pierced'] if pierce else None,
        save_kind=save['kind'] if save else None,
        save_value=save['value'] if save else 0,
        saved=save['saved'] if save else None,
    )


def aimed_name(ruleset: Ruleset, called_shot: dict | None) -> str | None:
    """노린 부상의 이름. 규칙에 적힌 이름이다. 노려 치지 않았으면 None."""
    if called_shot is None:
        return None
    found = known_injuries(ruleset, [called_shot['aim']])
    return found[0].name if found else None


def hindrance_names(ruleset: Ruleset, hindrance: dict | None) -> list[str]:
    """판정에 영향을 준 부상들의 이름. 규칙에 적힌 이름이다. 영향이 없었으면 비어 있다."""
    if hindrance is None:
        return []
    return [injury.name for injury in known_injuries(ruleset, hindrance['injuries'])]


def to_story(snapshot: Snapshot) -> StoryContext:
    """
    판의 복사본에서 이야기의 바탕을 꺼낸다. 서술자에게만 준다.

    룰북의 진행 지침과 세계관의 GM 메모가 들어간다. 이것들은 AI 가 읽으라고 쓴 글이다. 플레이어에게 내보내지 않는다.
    규칙의 서술 지침(#616)도 함께 간다. 판에 굳은 규칙의 것이라 템플릿이 바뀌어도 그대로다.
    세계관이 없는 시나리오면 설정과 GM 메모는 빈 글이다. 로어북은 넣지 않는다(검색 단계의 일).
    """
    world = snapshot.world
    return StoryContext(
        title=snapshot.title,
        rating=snapshot.rating,
        guide=snapshot.rulebook.gm_guide,
        setting=world.setting if world else '',
        gm_notes=world.gm_notes if world else '',
        narration=snapshot.rulebook.rules.narration,
    )


def said_in_moves(moves: list[dict]) -> list[tuple[str, bool | None]]:
    """
    굳혀 둔 각자 한 일에서 한 말들을 꺼낸다. 하나하나가 ("캐릭터 이름: 글", 판정이 성공했는가)다.

    선언을 내지 않은 사람(글이 없음)은 뺀다. 판정이 없던 선언은 성공 여부가 None 이다.
    문서를 통째로 검사하지 않고(read_moves) 필요한 칸만 읽는다. 오래된 라운드는 나중에 생긴 칸이 없을 수 있다.
    지난 라운드를 읽다가 서술이 멈추면 안 된다.
    """
    return [
        (f'{move["character_name"]}: {move["content"]}', (move.get('verdict') or {}).get('success'))
        for move in moves
        if move.get('content') is not None
    ]


def said_in_declarations(declarations: list[Declaration]) -> list[tuple[str, bool | None]]:
    """
    선언들에서 한 말들을 꺼낸다. 굳혀 둔 것이 없는 옛 라운드에만 쓴다.

    선언에 적어 둔 캐릭터 이름을 쓴다. 판정의 결과가 적혀 있으면 성공 여부를 읽는다.
    """
    return [
        (f'{declaration.character_name}: {declaration.content}', (declaration.outcome or {}).get('success'))
        for declaration in declarations
    ]


def to_past(round_: Round) -> PastRound:
    """
    지난 라운드를 서술자에게 줄 모양으로 바꾼다. 그때의 장면과, 한 말마다 "캐릭터 이름: 글" 한 줄.

    한 말은 닫기 시작할 때 굳혀 둔 각자 한 일(round_.moves)에서 읽는다. 그 라운드의 서술자가 받은 것과 같다.
      - 마감 전에 나간 사람의 선언은 판정도 서술도 받지 않았다. 굳혀 둔 것에 없으므로 여기에도 없다.
        선언 자체는 라운드의 기록에 남는다(GET /rounds/{number}). 서술자에게 주는 지난 일에서만 빠진다.
      - 마감 뒤에 나간 사람의 것은 굳혀 둔 것에 있다. 지금 앉은 사람으로 거르지 않으므로 그대로 남는다.
    굳혀 둔 것이 없는 라운드(그 칸이 생기기 전에 닫힌 옛 라운드, 아직 선언을 받는 라운드)는 선언을 읽는다.
    옛 라운드는 누가 마감 전에 나갔는지 알 수 없어 낸 선언이 모두 들어간다.
    """
    said = said_in_declarations(round_.declarations) if round_.moves is None else said_in_moves(round_.moves)
    return PastRound(
        number=round_.number,
        scene=round_.scene,
        lines=[line for line, _ in said],
        successes=[success for _, success in said],
    )


def to_whisper_note(whisper: Whisper) -> WhisperNote:
    """GM 에게도 보인 쪽지를 서술자에게 줄 모양으로 바꾼다. 보낼 때의 캐릭터 이름과 글이다."""
    return WhisperNote(
        sender=whisper.sender_character_name, recipient=whisper.recipient_character_name, content=whisper.content
    )


class Pace:
    """
    진행 중인 퀘스트의 남은 시간의 감각(#268). 서술자에게 숫자 대신 준다.

    재는 때는 이번 장면이 끝나는 시각(다음 라운드가 열리는 때)이다. 기한이 그 시각에 닿았으면 다음 라운드가 마지막이다.
    다음 라운드가 닫힐 때 실패로 바뀌고(app/tables/quests.py 의 is_overdue), 그 라운드에 이루면 성공이다.
    """

    # 기한의 절반보다 많이 남았다
    AMPLE = 'ample'
    # 절반 이하가 남았다
    TIGHT = 'tight'
    # 이번 장면이 끝날 때 기한이 지난다. 다음 라운드가 마지막이다
    LAST = 'last'


def pace_of(limit_minutes: int | None, due_at: int | None, scene_end: int) -> str | None:
    """남은 시간의 감각. 기한이 없으면 None 이다. scene_end 는 이번 장면이 끝나는 게임 안의 시각(분)이다."""
    if limit_minutes is None or due_at is None:
        return None
    left = due_at - scene_end
    if left <= 0:
        return Pace.LAST
    return Pace.AMPLE if left * 2 > limit_minutes else Pace.TIGHT


def scene_end_of(table: GameTable) -> int | None:
    """이번 장면이 끝나는 게임 안의 시각(분). 지금 시각에 다음 라운드까지 흐를 시간을 더한다. 시계가 없으면 None."""
    if table.clock is None:
        return None
    return table.clock.minutes + state.next_step(table)


def to_quest_note(row: TableQuest, quest: CatalogQuest, scene_end: int | None, expired: set[str]) -> QuestNote:
    """
    퀘스트 하나를 서술자에게 줄 모양으로. 진행 중이면 남은 시간의 감각을, 이번 라운드에 기한을 넘겼으면 그것을 붙인다.

    기한을 넘긴 것은 실패로 끝나 더 바뀌지 않는다(방장도 끝난 퀘스트를 바꾸지 못한다). 그래서 라운드에 적힌 것만 본다.
    """
    active = row.status == QuestStatus.ACTIVE and scene_end is not None
    return QuestNote(
        name=quest.name,
        status=row.status,
        pace=pace_of(quest.time_limit_minutes, row.due_at, scene_end) if active else None,
        missed_deadline=str(row.entry_id) in expired,
    )


def to_quest_notes(table: GameTable, snapshot: Snapshot, expired: list[str] | None = None) -> list[QuestNote]:
    """
    테이블의 퀘스트들을 서술자에게 줄 모양으로 바꾼다. 판의 순서다. 이름과 지금 상태와 기한의 감각이다.

    expired 는 이번 라운드에 기한을 넘겨 실패한 퀘스트들이다(Round.expired_quests).

    끝난 것도 준다. 이미 정해진 결말이라 서술이 그와 어긋나지 않게 한다. 사건의 글은 로어북 검색이 따로 준다.
    """
    catalog = quests.catalog(snapshot)
    scene_end = scene_end_of(table)
    missed = set(expired or [])
    return [
        to_quest_note(row, catalog[row.entry_id], scene_end, missed)
        for row in quests.in_catalog_order(table.quests, catalog)
    ]


def is_seen(move: dict, here: Set[uuid.UUID]) -> bool:
    """
    옮겨진 인물을 일행이 봤는가(#282). 떠난 곳이나 닿은 곳에 살아 있는 캐릭터가 서 있다.
    판의 사건이 다룬 문(#281)도 같이 본다. 그 길의 한 끝에 살아 있는 캐릭터가 서 있다.

    아무도 없는 곳에서 아무도 없는 곳으로 간 인물은 서술자에게 이르지 않는다. 일행이 모르는 일이 장면에 새지 않는다.
    """
    ends = (move['from'], move['to'])
    return any(end is not None and uuid.UUID(end) in here for end in ends)


def describe_npc_move(move: dict, labels: Mapping[uuid.UUID, str], places: Mapping[uuid.UUID, str]) -> str:
    """옮겨진 인물 하나를 "부르는 이름 → 장소"로. 부르는 이름은 장면의 호칭이다(진짜 이름을 맞혔으면 진짜 이름)."""
    return f'{labels[uuid.UUID(move["entry_id"])]} → {places[uuid.UUID(move["to"])]}'


# 판의 사건이 다룬 문(#281)을 서술자에게 이르는 말. (한 일, 장치)마다다
HAPPENING_DOOR_WORDS = {
    ('lock', 'lock'): '자물쇠 잠김',
    ('lock', 'bar'): '빗장 걸림',
    ('unlock', 'lock'): '자물쇠 열림',
    ('unlock', 'bar'): '빗장 풀림',
    ('repair', None): '부서진 문 고쳐짐',
}


def describe_happening_door(change: dict, places: Mapping[uuid.UUID, str]) -> str:
    """판의 사건이 다룬 문 하나를 "장소 ↔ 장소 빗장 걸림"으로(#281). 장소는 효과에 적힌 두 끝의 차례다."""
    ends = f'{places[uuid.UUID(change["from"])]} ↔ {places[uuid.UUID(change["to"])]}'
    return f'{ends} {HAPPENING_DOOR_WORDS[(change["act"], change["device"])]}'


def to_happening_note(
    snapshot: Snapshot, row: TableHappening, labels: Mapping[uuid.UUID, str], here: Set[uuid.UUID]
) -> HappeningNote:
    """
    일어난 사건 하나를 서술자에게 줄 모양으로 바꾼다. 옮겨진 사람마다 "이름 → 장소"다.

    캐릭터 다음에 일행이 본 인물(is_seen)이다. labels 는 인물마다 부르는 이름(app/rounds/cast.py 의 labels_of),
    here 는 살아 있는 캐릭터가 서 있는 장소들이다. 다룬 문(#281)도 그 길의 한 끝에 일행이 있을 때만 준다.
    """
    name = next(entry.name for entry in quest_entries(snapshot) if entry.id == row.entry_id)
    places = {entry.id: entry.name for entry in place_entries(snapshot)}
    moved = [f'{move["character_name"]} → {move["to"]["name"]}' for move in row.moves]
    moved.extend(describe_npc_move(move, labels, places) for move in row.npc_moves if is_seen(move, here))
    doors = [describe_happening_door(change, places) for change in row.doors if is_seen(change, here)]
    return HappeningNote(name=name, moved=moved, doors=doors)


def to_happening_notes(
    table: GameTable,
    snapshot: Snapshot,
    round_number: int,
    labels: Mapping[uuid.UUID, str] | None = None,
    here: Set[uuid.UUID] = frozenset(),
) -> list[HappeningNote]:
    """
    그 라운드가 닫힐 때 일어난 판의 사건들을 서술자에게 줄 모양으로 바꾼다. 판의 순서다(#367).

    일어난 것은 테이블에 적혀 있다(table_happenings). 다시 맡겨도 같은 것을 받는다.
    labels 와 here 는 옮겨진 인물을 이를 때 쓴다(to_happening_note).
    """
    order = {rule.entry_id: index for index, rule in enumerate(snapshot.happenings)}
    rows = [row for row in table.happenings if row.round_number == round_number and row.entry_id in order]
    return [
        to_happening_note(snapshot, row, labels or {}, here)
        for row in sorted(rows, key=lambda row: order[row.entry_id])
    ]


def to_clock_note(table: GameTable) -> ClockNote | None:
    """
    테이블의 시계를 서술자에게 줄 모양으로 바꾼다. 지금 시각, 다음 라운드가 열릴 때까지 흐를 시간, 그때의 시각.

    서술을 맡길 때의 것을 읽는다. 라운드가 닫힐 때 엔진이 늘린 걸음(길, 쉬기, 기다리기)을 그 라운드의 서술이 따른다.
    시계가 없는 테이블이면 None 이다.
    """
    if table.clock is None:
        return None
    passes = state.next_step(table)
    return ClockNote(
        now=clock.read_time(table.clock.minutes),
        ends=clock.read_time(table.clock.minutes + passes),
        passes_minutes=passes,
    )


def dump_moves(moves: list[Move]) -> list[dict]:
    """각자 한 일을 라운드에 굳혀 둘 모양(JSON)으로 바꾼다."""
    return [asdict(move) for move in moves]


def read_moves(data: list[dict]) -> list[Move]:
    """라운드에 굳혀 둔 것을 각자 한 일로 다시 읽는다. 모양이 틀리면 ValidationError."""
    return MOVES.validate_python(data)


def to_target_gone(declaration: Declaration | None) -> TargetGoneNote | None:
    """선언에 적힌 "겨눈 몬스터를 칠 수 없었다"를 서술자에게 줄 모양으로. 아니었으면 None."""
    if declaration is None or declaration.outcome is None:
        return None
    gone = declaration.outcome.get('target_gone')
    if gone is None:
        return None
    return TargetGoneNote(name=gone['name'], reason=gone['reason'])


def to_cost_words(shifts: list[dict] | None) -> list[ResourceNote]:
    """
    몬스터나 인물이 낸 공격의 비용(#805 ③-a)을 서술자에게 줄 모양으로. 바뀐 뒤를 네 단계의 말로만 준다.

    NPC 와 몬스터의 수치는 보이기와 상관없이 숫자를 주지 않는다(#804). 최소가 없는 옛 문서는 0 으로 읽는다.
    """
    return [
        ResourceNote(name=one['name'], word=band_of(one['after'], one.get('min', 0), one['max']))
        for one in shifts or []
    ]


def to_monster_turn(turn: dict) -> MonsterTurnNote | None:
    """
    라운드에 적힌 몬스터나 인물의 차례 하나를 서술자에게 줄 모양으로. 움직이지 못한 차례(skipped)면 None.

    둘의 outcome 은 같은 모양이다. 굴림의 숫자와 부상의 영향은 옮기지 않는다. 그 능력치를 드러낸다.
    고른 공격의 비용이 모자라 하지 못한 차례(#805 ③-a)는 무엇을 하려다 못 했는지를 준다.
    """
    outcome = turn['outcome']
    if outcome.get('skipped') == 'cost_short':
        attack, target = outcome['attack']['name'], outcome['character_name']
        return MonsterTurnNote(name=turn['name'], attack=attack, target=target, hit=False, short=True)
    if 'skipped' in outcome:
        return None
    return MonsterTurnNote(
        name=turn['name'],
        attack=outcome['attack']['name'],
        target=outcome['character_name'],
        hit=outcome['success'],
        impact=to_impact(outcome['effect']),
        downed=to_downed_strike(outcome.get('downed_strike')),
        blow=to_blow(outcome.get('blow')),
        cost=to_cost_words(outcome.get('cost')),
        injured=[one['name'] for one in outcome.get('injured') or [] if one['injury'] is not None],
        resources=to_shift_notes(outcome.get('resources')),
        resisted=[one['name'] for one in outcome.get('injured') or [] if one.get('immune')],
    )


def to_downed_strike(struck: dict | None) -> DownedStrikeNote | None:
    """차례에 적힌 쓰러진 캐릭터를 친 결과를 서술자에게 줄 모양으로. 서 있는 캐릭터를 쳤으면 None."""
    if struck is None:
        return None
    return DownedStrikeNote(
        added=struck['added'], failures=struck['failures'], limit=struck['limit'], fate=struck['fate']
    )


def to_turn_note(turn: dict) -> TurnNote | None:
    """라운드에 적힌 차례 하나를 서술자에게 줄 모양으로. 몬스터나 인물이 움직이지 못한 차례면 None."""
    if turn['kind'] == 'pc':
        return TurnNote(character_name=turn['character_name'])
    attack = to_monster_turn(turn)
    if attack is None:
        return None
    return TurnNote(npc=attack) if turn['kind'] == 'npc' else TurnNote(monster=attack)


def to_turn_notes(turns: list[dict]) -> list[TurnNote]:
    """
    라운드에 적힌 차례들(Round.turns)을 서술자에게 줄 모양으로. 차례 순서다. 움직이지 못한 차례는 뺀다.

    차례는 닫기 시작할 때 굳었다(app/rounds/judging.py). 몇 번을 맡겨도 같은 것을 받는다.
    """
    notes = [to_turn_note(turn) for turn in turns]
    return [note for note in notes if note is not None]


def to_secret_names(snapshot: Snapshot, npcs: Iterable[TableNpc], scene: str) -> dict[str, str]:
    """
    아직 맞히지 않은 인물의 숨길 이름과 대신 부를 호칭(app/rounds/secret_names.py).

    맞힌 인물(named_round 가 있는 NPC 상태)의 이름은 숨기지 않는다. 판의 인물 항목 전부를 본다.
    scene 은 이번 라운드를 연 장면이다. 이미 나온 이름은 숨기지 않는다.
    """
    named = {npc.entry_id for npc in npcs if npc.named_round is not None}
    return secret_names(person_entries(snapshot), named, scene)
