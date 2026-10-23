# trpg-server/app/transcripts/story.py

"""
이벤트와 채팅, 쪽지를 기록의 조각(app/transcripts/blocks.py)으로 바꾼다(#403, #617). DB 와 HTTP 와 파일의 형식을 모른다.

넣고 빼는 규칙.
  - 앉은 사람에게 내보내는 칸(app/events/responses.py 의 visible_payload)만 읽는다. 기록이 화면보다 더 많이 알지 않는다.
  - 이야기에 드는 종류만 쓴다(RENDERERS). 서술, 선언, 판정의 눈과 결과,
    HP·부상·물건·퀘스트·이동·사건 같은 상태의 변화다.
    목록에 없는 종류는 쓰지 않는다. 새 종류가 생겨도 이 목록에 올리기 전에는 기록에 나가지 않는다.
  - 채팅은 그 테이블의 모두가 본 것이라 넣는다. 쪽지는 받는 사람의 쪽지함에 있는 것(보냈거나 받은 것)만 넣는다(#617).
    누가 누구에게 쪽지를 보냈다는 이벤트(whisper_sent)는 쓰지 않는다. 남의 쪽지가 있었다는 것도 드러내지 않는다.
  - 설정과 운영(모델, 문체, 시간 제한, 크레딧, 서술 실패)은 쓰지 않는다. 이야기가 아니다.
  - 숨긴 퀘스트는 쓰지 않는다. 드러난 뒤의 바뀜만 쓴다.
  - 사람은 캐릭터의 이름으로만 쓴다(#617). 계정의 이름과 내부 식별자(사람, 항목, 몬스터의 id)는 쓰지 않는다.
    탈퇴한 사람도 이야기 속 이름은 남는다. 비공개 로어, 모델의 추론, 프롬프트는 처음부터 이벤트에 없다.
  - 능력치, 난이도, 부상은 이 판의 규칙에 적힌 이름으로 쓴다(Labels). 규칙에 없으면 이름표를 그대로 쓴다.

함수는 셋으로 나눈다. 칸에서 값을 읽는 작은 도우미, 종류마다 조각을 만드는 함수(RENDERERS), 차례를 고치는 것.
"""

from collections.abc import AsyncIterator, Callable

from app.chat.models import ChatMessage
from app.events.models import EventType, TableEvent
from app.events.responses import visible_payload
from app.transcripts.blocks import Block, Heading, Note, Paragraph, Speech
from app.transcripts.labels import Labels
from app.whispers.models import Whisper

TIMES_OF_DAY = {'dawn': '새벽', 'morning': '아침', 'day': '낮', 'evening': '저녁', 'night': '밤'}
QUEST_STATUSES = {'active': '진행 중', 'succeeded': '성공', 'failed': '실패'}
ATTITUDES = {'friendly': '우호', 'neutral': '중립', 'wary': '경계', 'hostile': '적대'}
BODY_STATUSES = {'downed': '쓰러짐', 'dead': '죽음'}
HP_KINDS = {'damage': '피해', 'heal': '회복'}
# 이름이 없을 때(캐릭터를 만들기 전에 떠남) 쓰는 말
SOMEONE = '이름 없는 사람'

# 기록에 드는 것. 이벤트, 채팅 한 줄, 받는 사람의 쪽지 한 장이다
Item = TableEvent | ChatMessage | Whisper


# --- 칸에서 값을 읽는 도우미 ---


def text_of(value: object) -> str:
    """글을 한 줄로 쓸 수 있게 한다. 줄 바꿈은 띄어 쓰기로 바꾼다. 비어 있으면 빈 글자다."""
    return ' '.join(str(value or '').split())


def who(payload: dict) -> str:
    """이벤트의 캐릭터 이름. 없으면 이름 없는 사람이다."""
    return text_of(payload.get('character_name')) or SOMEONE


def place_name(place: object) -> str:
    """장소의 칸({entry_id, name})에서 이름만 꺼낸다."""
    return text_of(place.get('name')) if isinstance(place, dict) else ''


def item_count(payload: dict) -> str:
    """물건의 이름과 개수. "밧줄 3개"."""
    return f'{text_of(payload.get("name"))} {payload.get("count")}개'


def outcome(success: object) -> str:
    """판정의 성패."""
    return '성공' if success else '실패'


def clock_text(clock: object) -> str:
    """게임 안의 시각({day, hour, minute, time_of_day})을 "3일째 22:00(밤)"으로."""
    if not isinstance(clock, dict):
        return ''
    part = TIMES_OF_DAY.get(clock.get('time_of_day'), '')
    return f'{clock.get("day")}일째 {clock.get("hour"):02d}:{clock.get("minute"):02d}' + (f'({part})' if part else '')


def lines_of(text: object) -> tuple[str, ...]:
    """여러 줄의 글을 줄마다 앞뒤 공백을 떼어 나눈다. 빈 줄은 문단의 구분으로 남긴다."""
    return tuple(line.strip() for line in str(text or '').strip().splitlines())


# --- 종류마다 조각을 만든다. payload 는 앉은 사람에게 보이는 칸만 있다 ---


def table_started(payload: dict, labels: Labels) -> list[Block]:
    """시작. 함께한 캐릭터의 이름들."""
    names = ', '.join(who(member) for member in payload.get('members') or [])
    return [Heading('시작'), Note(f'함께한 캐릭터: {names}' if names else '함께한 캐릭터가 없다')]


def round_opened(payload: dict, labels: Labels) -> list[Block]:
    """라운드의 구분. 번호와 게임 안의 시각."""
    when = clock_text(payload.get('clock'))
    return [Heading(f'라운드 {payload.get("number")}' + (f' · {when}' if when else ''))]


def gm_narration(payload: dict, labels: Labels) -> list[Block]:
    """GM 의 서술. 글 그대로다."""
    return [Paragraph(lines_of(payload.get('text')))]


def player_action(payload: dict, labels: Labels) -> list[Block]:
    """선언. 캐릭터의 이름과 글."""
    return [Speech(who(payload), lines_of(payload.get('content')))]


def check_rolled(payload: dict, labels: Labels) -> list[Block]:
    """판정. 능력치(난이도), 눈 + 보정 = 합, 목표, 성패."""
    ability = labels.abilities.get(payload.get('ability'), text_of(payload.get('ability')))
    difficulty = labels.difficulties.get(payload.get('difficulty'), text_of(payload.get('difficulty')))
    numbers = f'{payload.get("roll")} + {payload.get("modifier")} = {payload.get("total")}'
    return [
        Note(
            f'판정: {who(payload)} · {ability}({difficulty}) {numbers}, 목표 {payload.get("target")}'
            f' → {outcome(payload.get("success"))}'
        )
    ]


def hp_changed(payload: dict, labels: Labels) -> list[Block]:
    """캐릭터의 HP. 피해나 회복의 양과 그 앞뒤."""
    kind = HP_KINDS.get(payload.get('kind'), '변화')
    line = f'{who(payload)}: {kind} {payload.get("amount")} (HP {payload.get("before")} → {payload.get("after")})'
    return [Note(line + (', 쓰러짐' if payload.get('downed') else ''))]


def death_save_rolled(payload: dict, labels: Labels) -> list[Block]:
    """죽음의 굴림. 눈, 목표, 성패, 쌓인 수."""
    tally = f'성공 {payload.get("successes")}, 실패 {payload.get("failures")}'
    return [
        Note(
            f'죽음의 굴림: {who(payload)} {payload.get("roll")} / {payload.get("target")}'
            f' → {outcome(payload.get("success"))} ({tally})'
        )
    ]


def character_died(payload: dict, labels: Labels) -> list[Block]:
    """캐릭터의 죽음."""
    return [Note(f'{who(payload)} 죽음')]


def character_revived(payload: dict, labels: Labels) -> list[Block]:
    """되살아나기의 굴림."""
    roll = f'{payload.get("roll")} / {payload.get("target")}'
    line = f'되살아나기: {who(payload)} {roll} → {outcome(payload.get("success"))}'
    return [Note(line + (f', HP {payload.get("hp")}' if payload.get('success') else ''))]


def attacked(payload: dict, labels: Labels) -> list[Block]:
    """몬스터나 NPC 의 공격. 누가 무엇으로 누구를 쳤고 맞혔는가."""
    attack = payload.get('attack') or {}
    hit = '맞음' if payload.get('success') else '빗나감'
    return [Note(f'{text_of(payload.get("name"))} → {who(payload)}: {text_of(attack.get("name"))} → {hit}')]


def body_changed(payload: dict, labels: Labels) -> list[Block]:
    """몬스터나 NPC 의 몸. 양과 바뀐 생사만이다. HP 의 숫자는 GM 만 안다."""
    kind = HP_KINDS.get(payload.get('kind'), '변화')
    status = BODY_STATUSES.get(payload.get('status'))
    return [Note(f'{text_of(payload.get("name"))}: {kind} {payload.get("amount")}' + (f', {status}' if status else ''))]


def injured_name(payload: dict) -> str:
    """부상을 입은 쪽의 이름. 캐릭터면 캐릭터의 이름, NPC 면 장면의 호칭이다."""
    return text_of(payload.get('character_name')) or text_of(payload.get('name')) or SOMEONE


def injury_name(payload: dict, labels: Labels) -> str:
    """부상의 이름. 규칙에 적힌 이름이다."""
    return labels.injuries.get(payload.get('injury'), text_of(payload.get('injury')))


def injury_gained(payload: dict, labels: Labels) -> list[Block]:
    """부상을 입음."""
    return [Note(f'부상: {injured_name(payload)} · {injury_name(payload, labels)}')]


def injury_ended(payload: dict, labels: Labels) -> list[Block]:
    """부상이 풀리거나 나음."""
    return [Note(f'부상이 끝남: {injured_name(payload)} · {injury_name(payload, labels)}')]


def injury_treated(payload: dict, labels: Labels) -> list[Block]:
    """치료."""
    result = '나음' if payload.get('healed') else outcome(payload.get('treated'))
    return [Note(f'치료: {injured_name(payload)} · {injury_name(payload, labels)} → {result}')]


def items_gained(payload: dict, labels: Labels) -> list[Block]:
    """물건을 얻음."""
    return [Note(f'{who(payload)}: {item_count(payload)} 얻음 (모두 {payload.get("total")}개)')]


def items_lost(payload: dict, labels: Labels) -> list[Block]:
    """물건을 잃음."""
    return [Note(f'{who(payload)}: {item_count(payload)} 잃음 (남은 {payload.get("total")}개)')]


def item_used(payload: dict, labels: Labels) -> list[Block]:
    """물건을 씀. 대상이 있으면 대상의 이름."""
    item = text_of(payload.get('name'))
    if not payload.get('used'):
        return [Note(f'{who(payload)}: {item} 쓰지 못함')]
    target = payload.get('target')
    return [Note(f'{who(payload)}: {item} 씀' + (f' → {who(target)}' if isinstance(target, dict) else ''))]


def item_given(payload: dict, labels: Labels) -> list[Block]:
    """물건을 건넴."""
    target = payload.get('target') if isinstance(payload.get('target'), dict) else {}
    done = '' if payload.get('given') else ' (건네지 못함)'
    return [Note(f'{who(payload)} → {who(target)}: {item_count(payload)}{done}')]


def item_put_down(payload: dict, labels: Labels) -> list[Block]:
    """물건을 내려놓음."""
    item = item_count(payload)
    if not payload.get('put'):
        return [Note(f'{who(payload)}: {item} 내려놓지 못함')]
    return [Note(f'{who(payload)}: {item}를 {place_name(payload.get("place"))}에 내려놓음')]


def steal_attempted(payload: dict, labels: Labels) -> list[Block]:
    """훔치기. 누구에게서 무엇을, 판정의 눈과 성패, 들켰는가."""
    victim = text_of(payload.get('npc_name')) or text_of(payload.get('monster_name'))
    check = payload.get('check') or {}
    numbers = f'{check.get("roll")} + {check.get("modifier")} = {check.get("total")}, 목표 {check.get("target")}'
    result = f'{payload.get("count")}개 훔침' if payload.get('stolen') else '실패'
    caught = ', 들켜 싸움이 붙음' if payload.get('fight') else ''
    return [Note(f'훔치기: {who(payload)} → {victim} · {text_of(payload.get("name"))} {numbers} → {result}{caught}')]


def quest_changed(payload: dict, labels: Labels) -> list[Block]:
    """퀘스트의 상태. 숨긴 퀘스트는 쓰지 않는다(빈 목록)."""
    status = QUEST_STATUSES.get(payload.get('status'))
    if status is None:
        return []
    return [Note(f'퀘스트: {text_of(payload.get("name"))} → {status}')]


def character_moved(payload: dict, labels: Labels) -> list[Block]:
    """이동. 어디서 어디로. 업혀 갔거나 판의 사건이 옮겼으면 그렇게 적는다(#367)."""
    way = ' (업혀 감)' if payload.get('carried_by') else ' (사건)' if payload.get('happening') else ''
    return [Note(f'이동: {who(payload)} · {place_name(payload.get("from"))} → {place_name(payload.get("to"))}{way}')]


def happening_occurred(payload: dict, labels: Labels) -> list[Block]:
    """판의 사건(#367). 이름만 쓴다. 누가 어디로 옮겨졌는지는 뒤의 이동이 쓴다."""
    return [Note(f'사건: {text_of(payload.get("name"))}')]


def place_searched(payload: dict, labels: Labels) -> list[Block]:
    """찾기. 찾은 길과 물건."""
    routes = [
        f'{place_name(route.get("from_place"))} → {place_name(route.get("to_place"))}'
        for route in payload.get('found') or []
        if isinstance(route, dict)
    ]
    items = [text_of(item.get('name')) for item in payload.get('items') or [] if isinstance(item, dict)]
    found = ', '.join([*(f'길 {route}' for route in routes), *items]) or '찾은 것 없음'
    return [Note(f'찾기: {who(payload)} · {place_name(payload.get("place"))} → {found}')]


def character_rested(payload: dict, labels: Labels) -> list[Block]:
    """쉬기. 쉬었으면 HP 의 앞뒤."""
    if not payload.get('rested'):
        return [Note(f'쉬기: {who(payload)} → 쉬지 못함')]
    return [Note(f'쉬기: {who(payload)} · HP {payload.get("before")} → {payload.get("after")}')]


def member_left(payload: dict, labels: Labels) -> list[Block]:
    """스스로 나감."""
    return [Note(f'{who(payload)}: 테이블을 나감')]


def member_kicked(payload: dict, labels: Labels) -> list[Block]:
    """방장이 내보냄."""
    return [Note(f'{who(payload)}: 방장이 내보냄')]


def member_dropped(payload: dict, labels: Labels) -> list[Block]:
    """크레딧이 모자라 서버가 뺌."""
    return [Note(f'{who(payload)}: 크레딧이 모자라 빠짐')]


def character_joined(payload: dict, labels: Labels) -> list[Block]:
    """죽은 캐릭터의 뒤를 잇는 새 캐릭터."""
    replaces = text_of(payload.get('replaces'))
    return [Note(f'새 캐릭터: {who(payload)}' + (f' ({replaces}의 뒤를 이음)' if replaces else ''))]


def naming_resolved(payload: dict, labels: Labels) -> list[Block]:
    """이름 맞히기. 맞았으면 진짜 이름이 드러난다."""
    guess = text_of(payload.get('guess'))
    if payload.get('correct'):
        label = text_of(payload.get('label'))
        return [Note(f'이름 맞히기: {who(payload)} · "{guess}" → 맞음, {label}의 이름은 {guess}')]
    return [Note(f'이름 맞히기: {who(payload)} · "{guess}" → 틀림')]


def npc_attitude_changed(payload: dict, labels: Labels) -> list[Block]:
    """NPC 의 태도."""
    before = ATTITUDES.get(payload.get('previous'), text_of(payload.get('previous')))
    after = ATTITUDES.get(payload.get('attitude'), text_of(payload.get('attitude')))
    return [Note(f'태도: {text_of(payload.get("name"))} · {before} → {after}')]


def table_ended(payload: dict, labels: Labels) -> list[Block]:
    """테이블이 끝남."""
    return [Heading('끝')]


Renderer = Callable[[dict, Labels], list[Block]]

# 기록에 쓰는 종류. 여기 없는 종류는 쓰지 않는다
RENDERERS: dict[EventType, Renderer] = {
    EventType.TABLE_STARTED: table_started,
    EventType.ROUND_OPENED: round_opened,
    EventType.GM_NARRATION: gm_narration,
    EventType.PLAYER_ACTION: player_action,
    EventType.CHECK_ROLLED: check_rolled,
    EventType.HP_CHANGED: hp_changed,
    EventType.DEATH_SAVE_ROLLED: death_save_rolled,
    EventType.CHARACTER_DIED: character_died,
    EventType.CHARACTER_REVIVED: character_revived,
    EventType.MONSTER_ATTACKED: attacked,
    EventType.NPC_ATTACKED: attacked,
    EventType.MONSTER_CHANGED: body_changed,
    EventType.NPC_CHANGED: body_changed,
    EventType.INJURY_GAINED: injury_gained,
    EventType.INJURY_ENDED: injury_ended,
    EventType.INJURY_TREATED: injury_treated,
    EventType.ITEMS_GAINED: items_gained,
    EventType.ITEMS_LOST: items_lost,
    EventType.ITEM_USED: item_used,
    EventType.ITEM_GIVEN: item_given,
    EventType.ITEM_PUT_DOWN: item_put_down,
    EventType.STEAL_ATTEMPTED: steal_attempted,
    EventType.QUEST_CHANGED: quest_changed,
    EventType.CHARACTER_MOVED: character_moved,
    EventType.HAPPENING_OCCURRED: happening_occurred,
    EventType.PLACE_SEARCHED: place_searched,
    EventType.CHARACTER_RESTED: character_rested,
    EventType.MEMBER_LEFT: member_left,
    EventType.MEMBER_KICKED: member_kicked,
    EventType.MEMBER_DROPPED: member_dropped,
    EventType.CHARACTER_JOINED: character_joined,
    EventType.NAMING_RESOLVED: naming_resolved,
    EventType.NPC_ATTITUDE_CHANGED: npc_attitude_changed,
    EventType.TABLE_ENDED: table_ended,
}


def event_blocks(event: TableEvent, labels: Labels) -> list[Block]:
    """이벤트 하나의 조각들. 쓰지 않는 종류면 빈 목록이다. 앉은 사람에게 보이는 칸만 읽는다."""
    renderer = RENDERERS.get(EventType(event.type))
    if renderer is None:
        return []
    return renderer(visible_payload(event), labels)


def chat_blocks(message: ChatMessage) -> list[Block]:
    """채팅 한 줄. 쓴 사람의 캐릭터 이름과 글이다."""
    return [Note(f'채팅 · {text_of(message.character_name) or SOMEONE}: {text_of(message.content)}')]


def whisper_blocks(whisper: Whisper) -> list[Block]:
    """받는 사람의 쪽지 한 장. 보낸 사람과 받은 사람의 캐릭터 이름과 글이다."""
    sender = text_of(whisper.sender_character_name) or SOMEONE
    recipient = text_of(whisper.recipient_character_name) or SOMEONE
    return [Note(f'쪽지 · {sender} → {recipient}: {text_of(whisper.content)}')]


def blocks_of(item: Item, labels: Labels) -> list[Block]:
    """기록에 드는 것 하나의 조각들."""
    if isinstance(item, ChatMessage):
        return chat_blocks(item)
    if isinstance(item, Whisper):
        return whisper_blocks(item)
    return event_blocks(item, labels)


def is_event(item: Item, type_: EventType) -> bool:
    """그 종류의 이벤트인가."""
    return isinstance(item, TableEvent) and item.type == type_


async def scenes_under_rounds(items: AsyncIterator[Item]) -> AsyncIterator[Item]:
    """
    라운드의 구분을 그 라운드를 여는 서술 앞으로 옮긴다. 나머지 차례는 그대로다.

    이벤트에는 서술(gm_narration)이 먼저, 그 서술로 여는 라운드(round_opened)가 뒤에 적힌다.
    그대로 쓰면 "라운드 2" 가 2 라운드의 장면 뒤에 붙는다. 서술부터 다음 라운드가 열릴 때까지를 잡아 두었다가
    라운드를 먼저 내보낸다. 잡아 두는 것은 서술 하나와 그 사이의 몇 줄(채팅, 쪽지 포함)뿐이라 메모리에 쌓이지 않는다.
    """
    held: list[Item] = []
    async for item in items:
        if is_event(item, EventType.GM_NARRATION):
            for waiting in held:
                yield waiting
            held = [item]
        elif is_event(item, EventType.ROUND_OPENED) and held:
            yield item
            for waiting in held:
                yield waiting
            held = []
        elif held:
            held.append(item)
        else:
            yield item
    for waiting in held:
        yield waiting
