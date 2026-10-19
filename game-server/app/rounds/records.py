# game-server/app/rounds/records.py

"""
닫히는 라운드에서 일어난 일을 이벤트로 적는다(app/events/recorder.py).

선언은 낼 때가 아니라 라운드가 닫힐 때 이벤트로 적는다. 마지막 글만 적는다.
열려 있는 동안에는 남의 선언이 보이지 않아야 하는데, 이벤트는 앉은 사람 모두가 읽기 때문이다.
판정, HP 의 변화, 부상, 치료, 지목, 죽음의 굴림은 이미 끝나 있다(app/rounds/judging.py). 여기서는 적기만 한다.
일은 원인으로 잇는다(cause). 행동 → 판정 → 치료 → HP 의 변화 → 부상의 차례다. 지목은 행동 → 지목의 결과다.
몬스터의 차례는 몬스터의 공격 → HP 의 변화 → 부상이다. 맞붙은 몬스터가 있던 라운드는 차례 순서로 적는다.
엔진이 한 일은 행한 사람(actor_id)을 적지 않는다. 주사위를 굴리고 상태를 바꾼 것은 플레이어가 아니라 엔진이다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine import death
from app.engine.injury import Trigger
from app.events import recorder
from app.events.models import EventType, TableEvent
from app.rounds import injuries as round_injuries
from app.rounds import narration_request
from app.rounds.drops import NPC_SOURCE
from app.rounds.models import Declaration, Round
from app.rounds.place_item_actions import Source
from app.rounds.rests import Cause, Recovered
from app.rounds.state import (
    find_declaration,
    has_outcome,
    item_give_of,
    item_use_of,
    move_of,
    naming_of,
    put_down_of,
    rest_of,
    search_of,
    steal_of,
    take_of,
)
from app.rounds.steals import STEAL_SOURCE
from app.tables.models import DeathCause, GameTable, InjurySource, TableMember


def record_check(session: AsyncSession, table: GameTable, declaration: Declaration, cause: TableEvent) -> None:
    """
    판정의 결과를 이벤트로 적는다. 그 판정을 부른 행동의 이벤트(cause)에 잇는다.
    판정으로 HP 가 바뀌었으면(앉은 사람이든 NPC 든) 바로 뒤에 그것도 적는다.

    행한 사람(actor_id)을 적지 않는다. 주사위를 굴린 것은 플레이어가 아니라 엔진이다.
    누구의 판정인지는 원인으로 이은 행동의 이벤트와 캐릭터 이름으로 안다.
    """
    outcome = declaration.outcome
    ability, difficulty = narration_request.check_terms(declaration)
    payload = {
        'round': cause.payload['round'],
        'character_name': declaration.character_name,
        'ability': ability,
        'difficulty': difficulty,
        'roll': outcome['roll'],
        'modifier': outcome['modifier'],
        'total': outcome['total'],
        'target': outcome['target'],
        'success': outcome['success'],
        'hindrance': outcome.get('hindrance'),
        'called_shot': outcome.get('called_shot'),
    }
    rolled = recorder.record(session, table, EventType.CHECK_ROLLED, payload=payload, cause=cause)
    # 치료였으면 치료의 결과를 판정 바로 뒤에 적는다. HP 의 변화(덧남, 좀 아픔)는 치료의 결과에 잇는다
    treated = outcome.get('treatment')
    after = rolled if treated is None else record_treatment(session, table, treated, cause=rolled)
    effect = outcome.get('effect')
    if effect is not None:
        changed = record_hp_change(session, table, effect, cause=after)
        holder = {'user_id': effect['user_id'], 'character_name': effect['character_name']}
        record_injury(session, table, effect.get('injury_roll'), holder, cause=changed)
    npc_effect_ = outcome.get('npc_effect')
    if npc_effect_ is not None:
        changed = record_npc_change(session, table, npc_effect_, cause=after)
        holder = {'entry_id': npc_effect_['entry_id'], 'name': npc_effect_['name']}
        record_injury(session, table, npc_effect_.get('injury_roll'), holder, cause=changed)
        record_drop(session, table, outcome.get('drop'), cause=changed)
    monster_effect = outcome.get('monster_effect')
    if monster_effect is not None:
        changed = record_monster_change(session, table, monster_effect, cause=after)
        record_drop(session, table, outcome.get('drop'), cause=changed)


def record_treatment(session: AsyncSession, table: GameTable, treated: dict, cause: TableEvent) -> TableEvent:
    """
    치료의 결과를 이벤트로 적는다. 그 치료의 판정의 이벤트(cause)에 잇는다. 적은 이벤트를 돌려준다.

    다 나았으면 부상이 끝난 것(치료로)과 후유증을, 즉사였으면 캐릭터의 죽음을 바로 뒤에 적는다.
    행한 사람(actor_id)을 적지 않는다. 결과를 정한 것은 엔진이다.
    """
    round_number = cause.payload['round']
    patient = treated['patient']
    payload = {
        'round': round_number,
        **patient,
        'injury': treated['injury'],
        'treated': treated['treated'],
        'heals_at': treated['heals_at'],
        'healed': treated['healed'],
        'mishap': treated['mishap'],
        'died': treated['died'],
    }
    event = recorder.record(session, table, EventType.INJURY_TREATED, payload=payload, cause=cause)
    if treated['healed']:
        ended_payload = {'round': round_number, **patient, 'injury': treated['injury'], 'reason': 'treated'}
        ended = recorder.record(session, table, EventType.INJURY_ENDED, payload=ended_payload, cause=event)
        record_injury(session, table, treated['aftermath'], patient, cause=ended)
    if treated['died'] and 'user_id' in patient:
        died = {**patient, 'round': round_number, 'cause': DeathCause.TREATMENT}
        recorder.record(session, table, EventType.CHARACTER_DIED, payload=died, cause=event)
    return event


def record_injury(
    session: AsyncSession, table: GameTable, injury_roll: dict | None, holder: dict, cause: TableEvent
) -> None:
    """
    새 부상이 생겼으면 이벤트로 적는다. 그 부상을 부른 HP 의 변화의 이벤트(cause)에 잇는다.

    부상 표로 생겼거나(큰 타격, 쓰러짐), 노려 쳐서 생겼거나, 오래 가는 부상이 나을 때 후유증으로 생겼다.
    어느 쪽인지는 source 로 적는다.
    표를 굴리지 않았거나 부상이 없는 줄이 나왔으면 적지 않는다. 굴린 것은 HP 의 변화의 이벤트에 이미 있다.
    holder 는 누가 입었는지다. 캐릭터면 user_id 와 캐릭터 이름, NPC 면 항목의 id 와 장면의 호칭이다.
    """
    if injury_roll is None or injury_roll['injury'] is None:
        return
    payload = {
        'round': cause.payload['round'],
        **holder,
        'injury': injury_roll['injury'],
        'source': source_of(injury_roll),
        'ends_after_round': injury_roll['ends_after_round'],
        'heals_at': injury_roll.get('heals_at'),
    }
    recorder.record(session, table, EventType.INJURY_GAINED, payload=payload, cause=cause)


def source_of(injury_roll: dict) -> InjurySource:
    """부상이 생긴 일의 문서에서 그 부상이 어떻게 생겼는지."""
    if injury_roll['trigger'] == Trigger.CALLED_SHOT:
        return InjurySource.CALLED_SHOT
    if injury_roll['trigger'] == Trigger.AFTERMATH:
        return InjurySource.AFTERMATH
    return InjurySource.INJURY_TABLE


def record_npc_change(session: AsyncSession, table: GameTable, effect: dict, cause: TableEvent) -> TableEvent:
    """
    NPC 의 상태가 바뀐 것을 이벤트로 적는다. 그 변화를 부른 판정의 이벤트(cause)에 잇는다.

    HP 의 숫자까지 다 적는다. 앉은 사람에게 내보낼 칸은 이벤트 API 가 고른다(app/events/responses.py 의 VISIBLE).
    행한 사람(actor_id)을 적지 않는다. 상태를 바꾼 것은 엔진이다.
    """
    payload = {'round': cause.payload['round'], **effect}
    return recorder.record(session, table, EventType.NPC_CHANGED, payload=payload, cause=cause)


def record_attitude_change(
    session: AsyncSession, table: GameTable, change: dict, name: str, cause: TableEvent
) -> TableEvent:
    """
    NPC 의 태도가 바뀐 것을 이벤트로 적는다(npc_attitude_changed). 그렇게 만든 일의 이벤트(cause)에 잇는다.

    change 는 app/tables/npc_attitudes.py 의 change_attitude 가 돌려준 것이다. name 은 장면의 호칭이다.
    행한 사람(actor_id)을 적지 않는다. 바꾼 것은 엔진이다.
    """
    payload = {'round': cause.payload['round'], **change, 'name': name}
    return recorder.record(session, table, EventType.NPC_ATTITUDE_CHANGED, payload=payload, cause=cause)


def record_monster_change(session: AsyncSession, table: GameTable, effect: dict, cause: TableEvent) -> TableEvent:
    """
    몬스터 한 마리의 상태가 바뀐 것을 이벤트로 적는다. 그 변화를 부른 판정의 이벤트(cause)에 잇는다.

    NPC 의 변화와 같다. HP 의 숫자까지 다 적고, 앉은 사람에게 내보낼 칸은 이벤트 API 가 고른다.
    """
    payload = {'round': cause.payload['round'], **effect}
    return recorder.record(session, table, EventType.MONSTER_CHANGED, payload=payload, cause=cause)


def drop_origin(drop: dict) -> dict:
    """드롭이 나온 곳. 출처(source)와, 몬스터면 그 마리(monster_id, monster_name), NPC 면 그 인물(npc_id, npc_name)."""
    keys = ('npc_id', 'npc_name') if drop['source'] == NPC_SOURCE else ('monster_id', 'monster_name')
    return {'source': drop['source'], **{key: drop[key] for key in keys}}


def record_drop(session: AsyncSession, table: GameTable, drop: dict | None, cause: TableEvent) -> None:
    """
    몬스터나 NPC 를 쓰러뜨려 얻은 물건을 이벤트로 적는다. 그 대상이 쓰러진 변화의 이벤트(cause)에 잇는다.

    방장이 줄 때와 같은 종류(items_gained)를 물건마다 하나씩 적는다. 나온 곳(drop_origin)과
    상한을 넘어 잃은 개수(lost)가 더 붙는다. 받을 사람이 없어 사라졌으면 아무도 얻지 않아 적지 않는다.
    행한 사람(actor_id)을 적지 않는다. 굴리고 준 것은 엔진이다.
    """
    if drop is None or drop['user_id'] is None:
        return
    for thing in drop['items']:
        payload = {
            'round': cause.payload['round'],
            'user_id': drop['user_id'],
            'character_name': drop['character_name'],
            **thing,
            **drop_origin(drop),
        }
        recorder.record(session, table, EventType.ITEMS_GAINED, payload=payload, cause=cause)


def record_hp_change(session: AsyncSession, table: GameTable, effect: dict, cause: TableEvent) -> TableEvent:
    """
    HP 가 바뀐 것을 이벤트로 적는다. 그 변화를 부른 판정의 이벤트(cause)에 잇는다.

    행한 사람(actor_id)을 적지 않는다. HP 를 바꾼 것은 엔진이다. 누구의 HP 인지는 payload 의 user_id 다.
    """
    payload = {'round': cause.payload['round'], **effect}
    return recorder.record(session, table, EventType.HP_CHANGED, payload=payload, cause=cause)


def record_naming(session: AsyncSession, table: GameTable, declaration: Declaration, cause: TableEvent) -> None:
    """
    지목의 결과를 이벤트로 적는다. 그 지목을 부른 행동의 이벤트(cause)에 잇는다.

    행한 사람(actor_id)을 적지 않는다. 맞았는지를 정한 것은 엔진이다.
    """
    naming = naming_of(declaration)
    payload = {'round': cause.payload['round'], 'character_name': declaration.character_name, **naming}
    recorder.record(session, table, EventType.NAMING_RESOLVED, payload=payload, cause=cause)


def record_item_use(session: AsyncSession, table: GameTable, declaration: Declaration, cause: TableEvent) -> None:
    """
    물건을 쓴 결과를 이벤트로 적는다. 그 행동의 이벤트(cause)에 잇는다. 회복했으면 바로 뒤에 HP 의 변화를 적는다.

    행한 사람(actor_id)을 적지 않는다. 소지품과 HP 를 바꾼 것은 엔진이다.
    """
    payload = {
        'round': cause.payload['round'],
        'character_name': declaration.character_name,
        **item_use_of(declaration),
    }
    used = recorder.record(session, table, EventType.ITEM_USED, payload=payload, cause=cause)
    effect = declaration.outcome.get('effect')
    if effect is not None:
        record_hp_change(session, table, effect, cause=used)


def record_item_give(session: AsyncSession, table: GameTable, declaration: Declaration, cause: TableEvent) -> None:
    """물건을 건넨 결과를 이벤트로 적는다. 그 행동의 이벤트(cause)에 잇는다. 행한 사람을 적지 않는다."""
    payload = {
        'round': cause.payload['round'],
        'character_name': declaration.character_name,
        **item_give_of(declaration),
    }
    recorder.record(session, table, EventType.ITEM_GIVEN, payload=payload, cause=cause)


def record_move(session: AsyncSession, table: GameTable, declaration: Declaration, cause: TableEvent) -> None:
    """
    한 칸 간 것을 이벤트로 적는다. 그 행동의 이벤트(cause)에 잇는다. 방장이 옮길 때와 같은 종류(character_moved)다.

    가지 못했으면 적지 않는다. 위치가 바뀌지 않았다. 못 간 까닭은 라운드의 선언 결과에 있다.
    행한 사람(actor_id)을 적지 않는다. 위치를 바꾼 것은 엔진이다.
    """
    move = move_of(declaration)
    if not move['moved']:
        return
    payload = {
        'round': cause.payload['round'],
        **{key: move[key] for key in ('user_id', 'character_name', 'from', 'to')},
        'travel_minutes': move.get('travel_minutes'),
    }
    recorder.record(session, table, EventType.CHARACTER_MOVED, payload=payload, cause=cause)


def record_search(session: AsyncSession, table: GameTable, declaration: Declaration, cause: TableEvent) -> None:
    """
    찾기의 결과를 이벤트로 적는다. 그 행동의 이벤트(cause)에 잇는다. 행한 사람을 적지 않는다.

    찾은 길과 물건만 있다. 굴린 판정은 결과에도 없다(app/rounds/map_actions.py). 숨긴 것이 있었는지 드러나지 않는다.
    찾은 물건은 찾은 사람이 가졌으므로 그 뒤에 물건마다 items_gained 를 잇는다(source 는 search).
    """
    search = search_of(declaration)
    payload = {'round': cause.payload['round'], 'character_name': declaration.character_name, **search}
    searched = recorder.record(session, table, EventType.PLACE_SEARCHED, payload=payload, cause=cause)
    for thing in search.get('items', []):
        if thing['count']:
            record_gained(session, table, declaration, thing, Source.SEARCH, search['place'], searched)


def record_take(session: AsyncSession, table: GameTable, declaration: Declaration, cause: TableEvent) -> None:
    """
    줍기의 결과를 이벤트로 적는다. 하나라도 주웠으면 items_gained 하나다(source 는 place). 그 행동의 이벤트에 잇는다.

    못 주웠으면(남은 것이 없었다, 가득 찼다) 적지 않는다. 바뀐 것이 없다. 까닭은 라운드의 선언 결과에 있다.
    행한 사람을 적지 않는다. 판의 물건을 준 것은 엔진이다.
    """
    take = take_of(declaration)
    if not take['taken']:
        return
    thing = {key: take[key] for key in ('entry_id', 'name', 'total')} | {'count': take['taken']}
    record_gained(session, table, declaration, thing, Source.PLACE, take['place'], cause)


def record_put_down(session: AsyncSession, table: GameTable, declaration: Declaration, cause: TableEvent) -> None:
    """
    내려놓은 결과를 이벤트로 적는다(item_put_down). 그 행동의 이벤트(cause)에 잇는다. 행한 사람을 적지 않는다.

    못 놓았어도 적는다. 건네기와 같다. 까닭(reason)이 있다.
    """
    payload = {
        'round': cause.payload['round'],
        'character_name': declaration.character_name,
        **put_down_of(declaration),
    }
    recorder.record(session, table, EventType.ITEM_PUT_DOWN, payload=payload, cause=cause)


def record_steal(session: AsyncSession, table: GameTable, declaration: Declaration, cause: TableEvent) -> None:
    """
    훔치기의 결과를 이벤트로 적는다(steal_attempted). 그 행동의 이벤트(cause)에 잇는다. 들켰어도 적는다.

    훔쳤으면 items_gained(source 는 steal, 그 마리)를 그 뒤에 잇는다. 행한 사람을 적지 않는다. 정한 것은 엔진이다.
    """
    steal = steal_of(declaration)
    payload = {'round': cause.payload['round'], **steal}
    attempted = recorder.record(session, table, EventType.STEAL_ATTEMPTED, payload=payload, cause=cause)
    if not steal['count']:
        return
    gained = {
        'round': cause.payload['round'],
        'user_id': str(declaration.user_id),
        'character_name': declaration.character_name,
        'entry_id': steal['entry_id'],
        'name': steal['name'],
        'count': steal['count'],
        'total': steal['total'],
        'source': STEAL_SOURCE,
        'monster_id': steal['monster_id'],
        'monster_name': steal['monster_name'],
    }
    recorder.record(session, table, EventType.ITEMS_GAINED, payload=gained, cause=attempted)


def record_gained(
    session: AsyncSession,
    table: GameTable,
    declaration: Declaration,
    thing: dict,
    source: str,
    place: dict | None,
    cause: TableEvent,
) -> None:
    """장소에서 얻은 물건 한 가지를 items_gained 로 적는다. 방장이 줄 때와 같은 종류에 출처와 장소가 붙는다."""
    payload = {
        'round': cause.payload['round'],
        'user_id': str(declaration.user_id),
        'character_name': declaration.character_name,
        'entry_id': thing['entry_id'],
        'name': thing['name'],
        'count': thing['count'],
        'total': thing['total'],
        'source': source,
        'place': place,
    }
    recorder.record(session, table, EventType.ITEMS_GAINED, payload=payload, cause=cause)


def record_rest(
    session: AsyncSession, table: GameTable, member: TableMember, declaration: Declaration, cause: TableEvent
) -> None:
    """
    선언한 휴식의 결과를 이벤트로 적는다. 그 행동의 이벤트(cause)에 잇는다. 깨졌어도 적는다(rested 가 false).

    행한 사람(actor_id)을 적지 않는다. 회복을 정한 것은 엔진이다.
    """
    rest = rest_of(declaration)
    payload = {
        'round': cause.payload['round'],
        'user_id': str(member.user_id),
        'character_name': member.character_name,
        'cause': Cause.REST,
        **{key: rest.get(key) for key in ('length', 'rested', 'reason', 'rolls', 'before', 'after', 'max_hp')},
    }
    recorder.record(session, table, EventType.CHARACTER_RESTED, payload=payload, cause=cause)


def record_recoveries(session: AsyncSession, table: GameTable, recovered: Recovered, group: uuid.UUID) -> None:
    """
    라운드가 닫힐 때의 되살아나기와 저절로 회복을 이벤트로 적는다. 굴림은 이미 끝나 있다(app/rounds/rests.py).

    행한 사람(actor_id)을 적지 않는다. 시간이 흘러 엔진이 정한 것이다.
    """
    for payload in recovered.revivals:
        recorder.record(session, table, EventType.CHARACTER_REVIVED, payload=payload, group=group)
    for payload in recovered.natural:
        recorder.record(session, table, EventType.CHARACTER_RESTED, payload=payload, group=group)


def record_declaration(
    session: AsyncSession, table: GameTable, round_: Round, member: TableMember, group: uuid.UUID
) -> None:
    """
    한 사람의 선언을 이벤트로 적는다.
    판정, 지목, 물건 쓰기와 건네기, 가기와 찾기, 줍기와 내려놓기, 훔치기, 쉬기가 있었으면
    행동 바로 뒤에 그 결과를 적는다.

    선언을 내지 않았으면 적지 않는다. 판정은 이미 끝나 있다(roll_checks). 여기서는 적기만 한다.
    차례가 오기 전에 쓰러지거나 죽어 행동하지 못했으면(turn_lost) 행동만 적는다. 굴린 것이 없다.
    """
    declaration = find_declaration(round_, member.user_id)
    if declaration is None:
        return
    payload = {
        'round': round_.number,
        'character_name': member.character_name,
        'content': declaration.content,
        'action': declaration.action,
    }
    acted = recorder.record(
        session, table, EventType.PLAYER_ACTION, actor_id=member.user_id, payload=payload, group=group
    )
    if has_outcome(declaration):
        record_check(session, table, declaration, cause=acted)
    elif naming_of(declaration) is not None:
        record_naming(session, table, declaration, cause=acted)
    elif item_use_of(declaration) is not None:
        record_item_use(session, table, declaration, cause=acted)
    elif item_give_of(declaration) is not None:
        record_item_give(session, table, declaration, cause=acted)
    elif move_of(declaration) is not None:
        record_move(session, table, declaration, cause=acted)
    elif search_of(declaration) is not None:
        record_search(session, table, declaration, cause=acted)
    elif take_of(declaration) is not None:
        record_take(session, table, declaration, cause=acted)
    elif put_down_of(declaration) is not None:
        record_put_down(session, table, declaration, cause=acted)
    elif steal_of(declaration) is not None:
        record_steal(session, table, declaration, cause=acted)
    elif rest_of(declaration) is not None:
        record_rest(session, table, member, declaration, cause=acted)


def record_monster_turn(
    session: AsyncSession, table: GameTable, round_number: int, turn: dict, group: uuid.UUID
) -> None:
    """
    몬스터 한 마리의 차례를 이벤트로 적는다. 공격했으면 monster_attacked, 맞혔으면 그 뒤에 HP 의 변화와 부상이다.

    움직이지 못한 차례(skipped)는 적지 않는다. 굴린 것도 바뀐 것도 없다. 까닭은 라운드의 turns 에 있다.
    행한 사람(actor_id)을 적지 않는다. 몬스터를 움직인 것은 엔진이다.
    """
    outcome = turn['outcome']
    if 'skipped' in outcome:
        return
    payload = {
        'round': round_number,
        'monster_id': turn['monster_id'],
        'name': turn['name'],
        **{key: value for key, value in outcome.items() if key != 'effect'},
    }
    attacked = recorder.record(session, table, EventType.MONSTER_ATTACKED, payload=payload, group=group)
    effect = outcome['effect']
    if effect is not None:
        changed = record_hp_change(session, table, effect, cause=attacked)
        holder = {'user_id': effect['user_id'], 'character_name': effect['character_name']}
        record_injury(session, table, effect.get('injury_roll'), holder, cause=changed)


def record_actions(session: AsyncSession, table: GameTable, round_: Round, group: uuid.UUID) -> None:
    """
    닫히는 라운드의 선언과 몬스터의 차례를 이벤트로 적는다. 지금 앉아 있는 사람이 낸 것만 적는다.

    차례가 있었으면(round_.turns) 차례 순서로 적는다. 다시 볼 때 일어난 순서대로 읽혀야 한다.
    행동이 없는 선언은 차례가 없다. 차례들 뒤에 앉은 순서로 적는다.
    차례가 없었으면(맞붙은 몬스터가 없었으면) 앉은 순서로 적는다.
    선언을 내지 않은 사람은 적지 않는다. 누가 안 냈는지는 라운드가 닫힌 이벤트에 적힌다.
    """
    members = {str(member.user_id): member for member in table.members}
    done: set[str] = set()
    for turn in round_.turns:
        if turn['kind'] == 'monster':
            record_monster_turn(session, table, round_.number, turn, group)
            continue
        member = members.get(turn['user_id'])
        if member is not None:
            record_declaration(session, table, round_, member, group)
            done.add(turn['user_id'])
    for member in table.members:
        if str(member.user_id) not in done:
            record_declaration(session, table, round_, member, group)


def record_death(
    session: AsyncSession,
    table: GameTable,
    save: dict,
    round_number: int,
    cause: TableEvent,
) -> None:
    """
    죽음의 굴림으로 캐릭터가 죽은 것을 이벤트로 적는다. 그 굴림의 이벤트(cause)에 잇는다.

    행한 사람(actor_id)을 적지 않는다. 규칙이 정한 죽음이다.
    """
    payload = {
        'round': round_number,
        'user_id': save['user_id'],
        'character_name': save['character_name'],
        'cause': DeathCause.DEATH_SAVE,
    }
    recorder.record(session, table, EventType.CHARACTER_DIED, payload=payload, cause=cause)


def record_death_saves(session: AsyncSession, table: GameTable, round_: Round, group: uuid.UUID) -> None:
    """
    닫히는 라운드에 굴린 죽음의 굴림을 이벤트로 적는다. 굴림은 이미 끝나 있다(roll_death_saves). 여기서는 적기만 한다.
    그 굴림으로 죽었으면 바로 뒤에 그것도 적는다.

    행한 사람(actor_id)을 적지 않는다. 주사위를 굴린 것은 엔진이다. 누구의 굴림인지는 payload 의 user_id 다.
    """
    for save in round_.death_saves:
        payload = {'round': round_.number, **save}
        rolled = recorder.record(session, table, EventType.DEATH_SAVE_ROLLED, payload=payload, group=group)
        if save['fate'] == death.Fate.DEAD:
            record_death(session, table, save, round_.number, cause=rolled)


def record_injury_endings(
    session: AsyncSession, table: GameTable, ended: list[round_injuries.Ended], round_number: int, group: uuid.UUID
) -> None:
    """
    이 라운드가 닫힐 때 풀리거나 나은 부상들을 이벤트로 적는다. 끝내는 일은 이미 끝나 있다(expire_all).
    여기서는 적기만 한다. 나으면서 후유증이 생겼으면 바로 뒤에 그것도 적는다.

    행한 사람(actor_id)을 적지 않는다. 정한 라운드가 지나 엔진이 끝낸 것이다.
    """
    for one in ended:
        payload = {'round': round_number, **one.holder, 'injury': one.injury.injury, 'reason': one.reason.value}
        event = recorder.record(session, table, EventType.INJURY_ENDED, payload=payload, group=group)
        record_injury(session, table, one.aftermath, one.holder, cause=event)
