# asset-server/app/worlds/publishing.py

"""
세계관을 게시할 수 있는지 보는 규칙(#591, 화면 명세 D7 의 "게시"). DB 를 모르는 순수한 함수다.

막는 것(problems), 알리는 것(warnings), 걸러 낸 것(removed)을 나눈다(2026-10-24 유저 결정).
  - 막는 것: 이야기를 시작할 수 없거나(시작 장소, 시작 시간대, 인물이 없다), 칸끼리 가리키는 것이 없거나,
    남의 그림을 쓰거나, 인물의 캐릭터나 로어북을 판에 복사할 수 없다. 게시가 409 로 돌려준다.
    초안은 고치는 중이라 어긋날 수 있다(장소를 지웠는데 일정이 남았다). 판에는 맞는 것만 들어간다.
  - 알리는 것: 시작 장소에서 길로 닿지 않는 장소, 열릴 수 없는 이벤트, 어디에도 나오지 않는 인물, 고를 일이 없는 엔딩.
    만드는 중에 일부러 남겨 둔 것일 수 있어 게시는 된다.
  - 걸러 낸 것: 소개에서 걸러 낸 태그, 속성, CSS, 링크, 그림(app/content/html.py).
그림이 자기 것인지, 캐릭터와 로어북의 마지막 판은 DB 를 봐야 알아서 서비스가 찾아 넘긴다(app/worlds/service.py).
"""

import enum
import uuid
from collections.abc import Iterator, Mapping, Sequence

from app.characters.documents import LorebookCopyDocument, lorebook_copy
from app.content.html import Cleaned, clean_intro, image_ids
from app.ratings import Rating
from app.worlds.documents import CastCharacterDocument, character_copy, effective_show
from app.worlds.models import ConditionKind, ConfessionFailure, EffectKind, EndingTrigger, MapPresence, Match, World

# 조건의 종류마다 target 이 가리키는 것(장소, 물건, 인물, 시간대). 날짜는 target 이 없다
PLACE_TARGETS = frozenset({ConditionKind.REACH_PLACE})
ITEM_TARGETS = frozenset({ConditionKind.HOLD_ITEM})
CAST_TARGETS = frozenset(
    {
        ConditionKind.GAVE_ITEM,
        ConditionKind.AFFECTION_AT_LEAST,
        ConditionKind.AFFECTION_BELOW,
        ConditionKind.ACCOMPANIED,
    }
)
SLOT_TARGETS = frozenset({ConditionKind.SLOT_IS})
# value 가 호감도 단계의 이름인 종류(그 인물의 단계여야 한다), value 가 물건의 id 인 종류
STAGE_VALUES = frozenset({ConditionKind.AFFECTION_AT_LEAST, ConditionKind.AFFECTION_BELOW})
ITEM_VALUES = frozenset({ConditionKind.GAVE_ITEM})
EVENT_TARGETS = frozenset({ConditionKind.EVENT_SEEN})
ENDING_TARGETS = frozenset({ConditionKind.ENDING_SEEN})
# 효과의 종류마다 target 이 가리키는 것(인물, 물건, 장소)
CAST_EFFECTS = frozenset({EffectKind.AFFECTION, EffectKind.ACCOMPANY_START, EffectKind.ACCOMPANY_END})
ITEM_EFFECTS = frozenset({EffectKind.GIVE_ITEM, EffectKind.TAKE_ITEM})
PLACE_EFFECTS = frozenset({EffectKind.MOVE_TO})
# 엔딩의 시작 가운데 target 이 인물인 것
CONFESS_TRIGGERS = frozenset({EndingTrigger.CONFESS_SUCCESS, EndingTrigger.CONFESS_FAIL})


class Problem(enum.StrEnum):
    """게시할 수 없는 이유."""

    # 장소가 없거나 시작 장소를 고르지 않았다. 이야기가 어디서 시작하는지 모른다
    START_PLACE_MISSING = 'start_place_missing'
    # 시작 시간대가 없는 시간대를 가리킨다
    START_SLOT_MISSING = 'start_slot_missing'
    # 인물이 하나도 없다
    CAST_EMPTY = 'cast_empty'
    # 길, 시작 장소, 인물의 기본 장소, 일정, 조건이 없는 장소를 가리킨다
    PLACE_MISSING = 'place_missing'
    # 장소의 배경, 일정, 조건이 없는 시간대를 가리킨다
    SLOT_MISSING = 'slot_missing'
    # 시작 소지품, 선물의 규칙, 조건이 없는 물건을 가리킨다
    ITEM_MISSING = 'item_missing'
    # 조건, 효과, 장면이 없는 인물을 가리킨다
    CAST_TARGET_MISSING = 'cast_target_missing'
    # 조건(event_seen)이 없는 이벤트를 가리킨다
    EVENT_MISSING = 'event_missing'
    # 조건(ending_seen, 회차 혜택)이 이 세계관에 없는 엔딩을 가리킨다
    ENDING_TARGET_MISSING = 'ending_target_missing'
    # 조건이나 지도에 보이는 단계(map_stage)가 그 인물에 없는 호감도의 단계를 가리키거나,
    # 지도가 stage 인 인물에 단계를 고르지 않았다
    STAGE_MISSING = 'stage_missing'
    # 인물이 가리킨 캐릭터가 없다(지웠거나 자기 것이 아니다)
    CHARACTER_MISSING = 'character_missing'
    # 인물이 가리킨 캐릭터를 게시한 적이 없다. 판에 복사할 것이 없다
    CHARACTER_UNPUBLISHED = 'character_unpublished'
    # 전체이용가 세계관에 성인 등급 캐릭터(그 마지막 판)가 있다
    CHARACTER_RATING_TOO_HIGH = 'character_rating_too_high'
    # 가리킨 로어북이 없다(지웠다)
    LOREBOOK_MISSING = 'lorebook_missing'
    # 가리킨 로어북을 게시한 적이 없다
    LOREBOOK_UNPUBLISHED = 'lorebook_unpublished'
    # 쓰일 수 있는 엔딩의 시작(고백 성공, 끝내는 고백 실패, 기한, 엔딩에 적은 시작)마다 조건이 빈 엔딩이 하나는 없다.
    # 고백에 성공했는데 맞는 엔딩이 없는 일을 막는다(story.md 의 "빠짐이 없게")
    ENDING_MISSING = 'ending_missing'
    # 대표 그림이나 소개 글, 장소, 물건, 인물의 그림 가운데 자기가 올린 것이 아닌(또는 없는) 그림이 있다
    IMAGE_NOT_OWNED = 'image_not_owned'


class WorldWarning(enum.StrEnum):
    """알리기만 하는 것. 게시는 된다."""

    # 시작 장소에서 길로 닿지 않는 장소가 있다
    PLACE_UNREACHABLE = 'place_unreachable'
    # 열릴 수 없는 이벤트가 있다. 자기를 봐야 열리거나, 열릴 수 없는 이벤트를 봐야 열리거나, 기한 뒤의 날을 기다린다
    EVENT_UNREACHABLE = 'event_unreachable'
    # 기본 장소도 일정도 없고, 어느 이벤트의 장면에도 동행에도 나오지 않는 인물이 있다
    CAST_NEVER_PRESENT = 'cast_never_present'
    # 고를 일이 없는 엔딩이 있다. 기한이 없는데 기한의 엔딩, 고백할 수 없는 인물의 고백 엔딩,
    # 실패해도 계속하는 인물의 실패 엔딩, 열릴 수 없는 이벤트의 엔딩, 같은 시작의 조건이 빈 엔딩 뒤에 적은 엔딩
    ENDING_UNREACHABLE = 'ending_unreachable'


class WorldNotReadyError(Exception):
    """게시할 조건을 갖추지 못했다. problems 는 갖추지 못한 것 전부다(한 번에 알린다)."""

    def __init__(self, problems: list[Problem]) -> None:
        super().__init__(', '.join(problems))
        self.problems = problems


def place_ids(world: World) -> set[str]:
    return {place['id'] for place in world.places}


def slot_ids(world: World) -> set[str]:
    return {slot['id'] for slot in world.slots}


def item_ids(world: World) -> set[str]:
    return {item['id'] for item in world.items}


def cast_stages(world: World) -> dict[str, set[str]]:
    """인물마다 호감도의 단계 이름들."""
    return {member['id']: {stage['name'] for stage in member['affection']['stages']} for member in world.cast}


def event_ids(world: World) -> set[str]:
    return {event['id'] for event in world.events}


def all_conditions(world: World) -> Iterator[dict]:
    """초안의 조건 전부. 인물의 일정과 이벤트가 열리는 조건이다(엔딩의 조건은 다음 조각에서 더한다)."""
    for member in world.cast:
        for line in member.get('schedule', []):
            yield from line['when']['items']
    for event in world.events:
        yield from event['when']['items']
    for member in world.cast:
        if member.get('confession'):
            yield from member['confession']['when']['items']
    for ending in world.endings:
        yield from ending['when']['items']


def all_effects(world: World) -> Iterator[dict]:
    """초안의 효과 전부. 이벤트가 열릴 때의 것과 선택지의 것이다."""
    for event in world.events:
        yield from event.get('on_open', [])
        for choice in event.get('choices', []):
            yield from choice.get('effects', [])


def effect_targets(world: World, kinds: frozenset[EffectKind]) -> list[str]:
    """그 종류들의 효과가 가리키는 것들."""
    return [effect['target'] for effect in all_effects(world) if effect['kind'] in kinds]


def start_problems(world: World) -> list[Problem]:
    """이야기를 시작할 수 없는 것들. 시작 장소, 시작 시간대, 인물."""
    problems = [] if world.places and world.start_place is not None else [Problem.START_PLACE_MISSING]
    if world.start_slot not in slot_ids(world):
        problems.append(Problem.START_SLOT_MISSING)
    if not world.cast:
        problems.append(Problem.CAST_EMPTY)
    return problems


def pointed_places(world: World) -> list[str]:
    """장소를 가리키는 것 전부. 길의 양쪽, 시작 장소, 인물의 기본 장소, 일정, 장소의 조건, 옮기는 효과."""
    pointed = [end for path in world.paths for end in (path['a'], path['b'])]
    pointed += [world.start_place] if world.start_place is not None else []
    for member in world.cast:
        pointed += [member['home']] if member.get('home') is not None else []
        pointed += [line['place'] for line in member.get('schedule', [])]
    pointed += [item['target'] for item in all_conditions(world) if item['kind'] in PLACE_TARGETS]
    return pointed + effect_targets(world, PLACE_EFFECTS)


def pointed_slots(world: World) -> list[str]:
    """시간대를 가리키는 것 전부. 장소의 시간대 배경, 일정, 시간대의 조건."""
    pointed = [slot for place in world.places for slot in place.get('backgrounds', {})]
    pointed += [line['slot'] for member in world.cast for line in member.get('schedule', [])]
    return pointed + [item['target'] for item in all_conditions(world) if item['kind'] in SLOT_TARGETS]


def pointed_items(world: World) -> list[str]:
    """물건을 가리키는 것 전부. 시작 소지품, 선물의 규칙, 물건의 조건(가졌다, 건넸다), 주고 가져가는 효과."""
    pointed = [start['item'] for start in world.start_items]
    pointed += [gift['item'] for member in world.cast for gift in member['affection'].get('gifts', [])]
    for item in all_conditions(world):
        if item['kind'] in ITEM_TARGETS:
            pointed.append(item['target'])
        elif item['kind'] in ITEM_VALUES:
            pointed.append(item['value'])
    return pointed + effect_targets(world, ITEM_EFFECTS)


def pointed_cast(world: World) -> list[str]:
    """인물을 가리키는 것 전부. 인물의 조건, 호감도와 동행의 효과, 이벤트의 장면에 부르는 인물."""
    pointed = [item['target'] for item in all_conditions(world) if item['kind'] in CAST_TARGETS]
    scenes = [event['scene'] for event in world.events] + [ending['scene'] for ending in world.endings]
    pointed += [member for scene in scenes for member in scene.get('cast', [])]
    pointed += [
        ending['trigger']['target'] for ending in world.endings if ending['trigger']['kind'] in CONFESS_TRIGGERS
    ]
    return pointed + effect_targets(world, CAST_EFFECTS)


def stage_pointers(world: World) -> list[tuple[str, str]]:
    """(인물, 단계 이름) 가운데 있어야 하는 것들. 호감도의 조건과, 지도가 stage 인 인물의 단계."""
    pointers = [(item['target'], item['value']) for item in all_conditions(world) if item['kind'] in STAGE_VALUES]
    default_map = effective_show(world.show)['map']
    for member in world.cast:
        if (member.get('map') or default_map) == MapPresence.STAGE or member.get('map_stage') is not None:
            pointers.append((member['id'], member.get('map_stage') or ''))
        if member.get('confession'):
            pointers.append((member['id'], member['confession']['stage']))
    return pointers


def ending_ids(world: World) -> set[str]:
    return {ending['id'] for ending in world.endings}


def recorded_endings(world: World) -> set[str]:
    """계정에 남는 엔딩들(unlock). 회차 혜택의 조건(ending_seen)은 이것만 맞출 수 있다."""
    return {ending['id'] for ending in world.endings if ending.get('unlock', True)}


def endings_pointed(world: World) -> list[str]:
    """조건(ending_seen)이 가리키는 엔딩들."""
    return [item['target'] for item in all_conditions(world) if item['kind'] in ENDING_TARGETS]


def missing(pointed: Sequence[str], known: set[str], problem: Problem) -> list[Problem]:
    """가리킨 것 가운데 없는 것이 있으면 그 문제 하나."""
    return [problem] if any(name not in known for name in pointed) else []


def reference_problems(world: World) -> list[Problem]:
    """칸끼리 가리키는 것이 없는 것들. 장소, 시간대, 물건, 인물, 이벤트, 호감도의 단계."""
    cast = {member['id'] for member in world.cast}
    stages = cast_stages(world)
    events_pointed = [item['target'] for item in all_conditions(world) if item['kind'] in EVENT_TARGETS]
    events_pointed += [
        ending['trigger']['target'] for ending in world.endings if ending['trigger']['kind'] == EndingTrigger.EVENT
    ]
    stage_missing = any(stage not in stages.get(member, set()) for member, stage in stage_pointers(world))
    return [
        *missing(pointed_places(world), place_ids(world), Problem.PLACE_MISSING),
        *missing(pointed_slots(world), slot_ids(world), Problem.SLOT_MISSING),
        *missing(pointed_items(world), item_ids(world), Problem.ITEM_MISSING),
        *missing(pointed_cast(world), cast, Problem.CAST_TARGET_MISSING),
        *missing(events_pointed, event_ids(world), Problem.EVENT_MISSING),
        *missing(endings_pointed(world), ending_ids(world), Problem.ENDING_TARGET_MISSING),
        *([Problem.STAGE_MISSING] if stage_missing else []),
    ]


def trigger_key(trigger: dict) -> tuple[str, str | None]:
    """같은 시작인지 가르는 열쇠(종류, 대상)."""
    return (trigger['kind'], trigger.get('target'))


def needed_triggers(world: World) -> set[tuple[str, str | None]]:
    """
    조건이 빈 엔딩이 있어야 하는 시작들. 고백할 수 있는 인물의 고백 성공, 실패하면 끝내는 인물의 고백 실패,
    기한이 있으면 기한, 그리고 엔딩에 적힌 시작 전부다.
    """
    needed = {trigger_key(ending['trigger']) for ending in world.endings}
    for member in world.cast:
        confession = member.get('confession')
        if confession:
            needed.add((EndingTrigger.CONFESS_SUCCESS, member['id']))
            if confession['on_fail'] == ConfessionFailure.END:
                needed.add((EndingTrigger.CONFESS_FAIL, member['id']))
    if world.deadline_days is not None:
        needed.add((EndingTrigger.DEADLINE, None))
    return needed


def covered_triggers(world: World) -> set[tuple[str, str | None]]:
    """조건이 빈 엔딩이 있는 시작들. 그 시작이 일어나면 반드시 고를 엔딩이 있다."""
    return {trigger_key(ending['trigger']) for ending in world.endings if not ending['when']['items']}


def ending_problems(world: World) -> list[Problem]:
    """엔딩의 빠짐. 쓰일 수 있는 시작마다 조건이 빈 엔딩이 하나는 있어야 한다."""
    return [Problem.ENDING_MISSING] if needed_triggers(world) - covered_triggers(world) else []


def find_problems(world: World) -> list[Problem]:
    """초안만 보고 아는, 게시를 막는 것들. 없으면 빈 목록이다."""
    return start_problems(world) + reference_problems(world) + ending_problems(world)


def reachable_places(world: World, start: str) -> set[str]:
    """start 에서 길로 닿는 장소들(start 포함). 길은 양쪽으로 다닌다."""
    neighbours: dict[str, set[str]] = {}
    for path in world.paths:
        neighbours.setdefault(path['a'], set()).add(path['b'])
        neighbours.setdefault(path['b'], set()).add(path['a'])
    reached, frontier = {start}, [start]
    while frontier:
        for nxt in neighbours.get(frontier.pop(), set()) - reached:
            reached.add(nxt)
            frontier.append(nxt)
    return reached


def possible_item(item: dict, event_id: str, opened: set[str], deadline: int | None, recorded: set[str]) -> bool:
    """
    조건 하나가 언젠가 맞을 수 있는가.
    이벤트를 봤다는 열릴 수 있는 다른 이벤트여야 하고(처음 열릴 때 자기는 아직 안 봤다),
    n일째 이상은 기한 안이어야 한다. 엔딩을 봤다(회차 혜택)는 계정에 남는 엔딩이어야 한다(recorded).
    나머지는 사용자의 행동으로 맞출 수 있는 것으로 본다.
    """
    if item['kind'] == ConditionKind.EVENT_SEEN:
        return item['target'] != event_id and item['target'] in opened
    if item['kind'] == ConditionKind.ENDING_SEEN:
        return item['target'] in recorded
    if item['kind'] == ConditionKind.DAY_AT_LEAST:
        return deadline is None or item['count'] <= deadline
    return True


def days_overlap(items: list[dict]) -> bool:
    """모두 맞아야 하는 날짜의 조건들이 겹치는 날이 있는가(n일째 이상의 가장 큰 것 ≤ 이하의 가장 작은 것)."""
    least = [item['count'] for item in items if item['kind'] == ConditionKind.DAY_AT_LEAST]
    most = [item['count'] for item in items if item['kind'] == ConditionKind.DAY_AT_MOST]
    return not least or not most or max(least) <= min(most)


def possible_event(event: dict, opened: set[str], deadline: int | None, recorded: set[str]) -> bool:
    """
    그 이벤트가 열릴 수 있는가. opened 는 지금까지 열릴 수 있다고 본 이벤트들이고,
    recorded 는 계정에 남는 엔딩들이다. 조건이 비면 늘 열린다.
    """
    items = event['when']['items']
    checks = [possible_item(item, event['id'], opened, deadline, recorded) for item in items]
    if not items:
        return True
    if event['when']['match'] == Match.ANY:
        return any(checks)
    return all(checks) and days_overlap(items)


def openable_events(world: World) -> set[str]:
    """열릴 수 있는 이벤트들. 더 늘지 않을 때까지 되풀이한다(이벤트가 다른 이벤트를 봐야 열리는 사슬을 따라간다)."""
    opened: set[str] = set()
    while True:
        more = {
            event['id']
            for event in world.events
            if possible_event(event, opened, world.deadline_days, recorded_endings(world))
        } - opened
        if not more:
            return opened
        opened |= more


def present_cast(world: World) -> set[str]:
    """어딘가에 나올 수 있는 인물들. 기본 장소나 일정이 있거나, 이벤트의 장면에 불리거나, 동행을 시작한다."""
    placed = {member['id'] for member in world.cast if member.get('home') is not None or member.get('schedule')}
    called = {member for event in world.events for member in event['scene'].get('cast', [])}
    return placed | called | set(effect_targets(world, frozenset({EffectKind.ACCOMPANY_START})))


def can_start(trigger: dict, world: World, opened: set[str]) -> bool:
    """그 시작이 일어날 수 있는가. 기한은 기한이 있어야, 고백은 고백할 수 있는 인물이어야(실패는 끝내는 인물이어야),
    이벤트는 열릴 수 있어야 한다."""
    confessions = {member['id']: member.get('confession') for member in world.cast}
    if trigger['kind'] == EndingTrigger.DEADLINE:
        return world.deadline_days is not None
    if trigger['kind'] == EndingTrigger.EVENT:
        return trigger['target'] in opened
    confession = confessions.get(trigger['target'])
    if trigger['kind'] == EndingTrigger.CONFESS_FAIL:
        return bool(confession) and confession['on_fail'] == ConfessionFailure.END
    return bool(confession)


def shadowed_endings(world: World) -> list[str]:
    """같은 시작의 조건이 빈 엔딩 뒤에 적어 고를 일이 없는 엔딩들. 판정은 적은 차례로 처음 맞는 것을 고른다."""
    closed: set[tuple[str, str | None]] = set()
    shadowed = []
    for ending in world.endings:
        key = trigger_key(ending['trigger'])
        if key in closed:
            shadowed.append(ending['id'])
        elif not ending['when']['items']:
            closed.add(key)
    return shadowed


def unreachable_endings(world: World) -> list[str]:
    """고를 일이 없는 엔딩들. 시작이 일어날 수 없거나, 앞의 엔딩에 가려졌다."""
    opened = openable_events(world)
    never = [ending['id'] for ending in world.endings if not can_start(ending['trigger'], world, opened)]
    return never + shadowed_endings(world)


def find_warnings(world: World) -> list[WorldWarning]:
    """알리기만 하는 것들. 닿지 않는 장소, 열릴 수 없는 이벤트, 어디에도 나오지 않는 인물, 고를 일이 없는 엔딩."""
    warnings = []
    if world.start_place is not None and place_ids(world) - reachable_places(world, world.start_place):
        warnings.append(WorldWarning.PLACE_UNREACHABLE)
    if event_ids(world) - openable_events(world):
        warnings.append(WorldWarning.EVENT_UNREACHABLE)
    if {member['id'] for member in world.cast} - present_cast(world):
        warnings.append(WorldWarning.CAST_NEVER_PRESENT)
    if unreachable_endings(world):
        warnings.append(WorldWarning.ENDING_UNREACHABLE)
    return warnings


def character_copies(
    world: World, found: Mapping[uuid.UUID, tuple[int, dict] | None]
) -> tuple[dict[uuid.UUID, CastCharacterDocument], list[Problem]]:
    """
    인물들이 가리킨 캐릭터를 판에 넣을 것과 막는 것들로 가른다.
    found 는 자기 캐릭터의 마지막 판(번호와 문서, 게시한 적이 없으면 None)이다. 없으면 지운(또는 남의) 캐릭터다.
    전체이용가 세계관에는 성인 등급 판을 넣지 않는다.
    """
    copies: dict[uuid.UUID, CastCharacterDocument] = {}
    problems: list[Problem] = []
    for member in world.cast:
        character_id = uuid.UUID(member['character_id'])
        if character_id not in found:
            problems.append(Problem.CHARACTER_MISSING)
        elif found[character_id] is None:
            problems.append(Problem.CHARACTER_UNPUBLISHED)
        else:
            number, document = found[character_id]
            if document['rating'] == Rating.ADULT and world.rating == Rating.ALL:
                problems.append(Problem.CHARACTER_RATING_TOO_HIGH)
            copies[character_id] = character_copy(character_id, number, document)
    return copies, list(dict.fromkeys(problems))


def lorebook_copies(
    world: World, found: Mapping[uuid.UUID, tuple[int, dict] | None]
) -> tuple[list[LorebookCopyDocument], list[Problem]]:
    """가리킨 로어북들(차례대로)을 판에 넣을 것과 막는 것들로 가른다. found 는 character_copies 와 같은 모양이다."""
    copies: list[LorebookCopyDocument] = []
    problems: list[Problem] = []
    for lorebook_id in world.lorebooks:
        if lorebook_id not in found:
            problems.append(Problem.LOREBOOK_MISSING)
        elif found[lorebook_id] is None:
            problems.append(Problem.LOREBOOK_UNPUBLISHED)
        else:
            number, document = found[lorebook_id]
            copies.append(lorebook_copy(lorebook_id, number, document))
    return copies, list(dict.fromkeys(problems))


def cleaned_intro(world: World) -> Cleaned:
    """초안의 소개를 거른 것과 걸러 낸 것들."""
    return clean_intro(world.intro_html)


def world_image_ids(world: World) -> list[uuid.UUID]:
    """장소의 배경(기본과 시간대마다), 물건의 그림, 이벤트의 일러스트. 초안에는 글로 적혀 있다."""
    scenes = [event['scene'] for event in world.events] + [ending['scene'] for ending in world.endings]
    found = [uuid.UUID(entry['image_id']) for entry in [*world.places, *world.items, *scenes] if entry.get('image_id')]
    backgrounds = [image for place in world.places for image in place.get('backgrounds', {}).values()]
    return found + [uuid.UUID(image) for image in backgrounds]


def character_image_ids(characters: Sequence[CastCharacterDocument]) -> list[uuid.UUID]:
    """복사한 캐릭터들의 그림(대표 그림, 캐릭터 그림)."""
    found = [character.image_id for character in characters if character.image_id is not None]
    return found + [sprite.image_id for character in characters for sprite in character.sprites]


def used_image_ids(world: World, intro_html: str, characters: Sequence[CastCharacterDocument]) -> list[uuid.UUID]:
    """
    판에 쓰이는 그림들. 대표 그림, 거른 소개 글의 그림, 장소와 물건의 그림, 인물의 그림이다.
    처음 나온 차례로, 같은 것은 한 번만이다. 인물의 그림도 적어 두어야 공개 세계관에서 남이 본다.
    """
    found = [world.image_id] if world.image_id else []
    every = [*found, *image_ids(intro_html), *world_image_ids(world), *character_image_ids(characters)]
    return list(dict.fromkeys(every))
