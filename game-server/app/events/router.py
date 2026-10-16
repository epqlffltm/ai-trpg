# game-server/app/events/router.py

"""
이벤트 API. 요청을 받아 서비스에 넘기고, 결과를 응답의 모양으로 바꾼다.

주소는 테이블 아래에 둔다(/tables/{table_id}/events). 이벤트는 테이블에 딸린 것이다.
읽기만 있다. 이벤트는 테이블을 바꾸는 API 들이 일하면서 적는다.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.assets.routing import MAX_PAGE_SIZE, Session
from app.auth.dependencies import CurrentUser
from app.events import service
from app.events.models import EventType, TableEvent
from app.events.schemas import EventOut, EventPage

router = APIRouter(prefix='/tables/{table_id}/events', tags=['events'])

# 한 번에 읽는 이벤트의 개수
DEFAULT_EVENT_LIMIT = 50

# 종류마다 앉은 사람에게 내보내는 payload 의 칸.
# 여기에 적지 않은 칸은 나가지 않는다. 여기에 없는 종류는 payload 가 통째로 비어서 나간다.
# 나중에 AI 호출이나 GM 만 아는 판정을 이벤트로 적어도, 이 목록에 올리기 전에는 플레이어에게 보이지 않는다
VISIBLE: dict[EventType, tuple[str, ...]] = {
    EventType.TABLE_CREATED: (),
    EventType.MEMBER_JOINED: ('via',),
    EventType.MEMBER_LEFT: ('character_name',),
    EventType.MEMBER_KICKED: ('user_id', 'character_name'),
    EventType.HOST_CHANGED: ('user_id',),
    # 능력치의 굴림도 공개다. 버린 눈까지 모두에게 보인다
    EventType.ABILITIES_ROLLED: ('dice', 'scores', 'times_rolled', 'character_number'),
    EventType.REROLL_GRANTED: ('user_id',),
    EventType.NARRATION_STYLE_CHANGED: ('narration_style',),
    EventType.ROUND_TIME_LIMIT_CHANGED: ('round_time_limit',),
    EventType.NARRATION_TIER_CHANGED: ('narration_tier',),
    EventType.CREDIT_WAIT_CHANGED: ('credit_wait_seconds', 'remove_short_payers'),
    EventType.WHISPER_NOTICE_CHANGED: ('whisper_notice',),
    EventType.LEDGER_DRAFTS_CHANGED: ('ledger_drafts',),
    # 소지품은 공개다. 누가 무엇을 몇 개 받거나 잃었고, 그 뒤에 몇 개인가
    EventType.ITEMS_GAINED: ('user_id', 'character_name', 'entry_id', 'name', 'count', 'total'),
    EventType.ITEMS_LOST: ('user_id', 'character_name', 'entry_id', 'name', 'count', 'total'),
    # 물건을 쓰고 건넨 것도 공개다. 못 했으면 까닭(reason)이 있다
    EventType.ITEM_USED: ('round', 'character_name', 'entry_id', 'name', 'used', 'reason', 'target', 'remaining'),
    EventType.ITEM_GIVEN: (
        'round',
        'character_name',
        'entry_id',
        'name',
        'count',
        'given',
        'reason',
        'target',
        'remaining',
        'target_total',
    ),
    # 퀘스트의 이름과 상태, 보상, 기한, 서버가 바꾼 까닭(기한을 넘김)은 공개다. 사건의 글(로어북)은 적지 않는다.
    # 숨긴 퀘스트에는 기한을 적지 않는다(드러날 때 정한다). 숨김에서 바로 끝낸 것도 기한이 비어 있다
    EventType.QUEST_CHANGED: ('entry_id', 'name', 'previous', 'status', 'rewards', 'due_at', 'reason'),
    EventType.CLOCK_STEP_CHANGED: ('previous', 'next_step_minutes', 'default'),
    # 캐릭터의 위치는 공개다. 아는 장소만 적히므로 숨긴 장소는 새지 않는다
    EventType.CHARACTER_MOVED: ('round', 'user_id', 'character_name', 'from', 'to', 'travel_minutes'),
    # 찾은 길은 공개다. 찾았으니 이제 모두가 아는 길이다. 굴린 판정은 처음부터 적지 않는다
    EventType.PLACE_SEARCHED: ('round', 'character_name', 'place', 'found'),
    # 누가 누구에게 보냈는지만 보인다. 쪽지의 글은 처음부터 적지 않는다
    EventType.WHISPER_SENT: ('user_id', 'character_name', 'recipient_id', 'recipient_character_name'),
    EventType.TABLE_STARTED: ('members',),
    EventType.GM_NARRATION: ('text',),
    # 게임 안의 시각은 공개다. 모두 같은 때에 있다
    EventType.ROUND_OPENED: ('number', 'deadline_at', 'narration_tier', 'clock', 'passed_minutes'),
    EventType.PLAYER_ACTION: ('round', 'character_name', 'content', 'action'),
    # 굴림은 공개다. 숫자까지 모두에게 보인다
    EventType.CHECK_ROLLED: (
        'round',
        'character_name',
        'ability',
        'difficulty',
        'roll',
        'modifier',
        'total',
        'target',
        'success',
        'hindrance',
        'called_shot',
    ),
    # HP 도 공개다. 앉은 사람은 서로의 시트를 본다
    EventType.HP_CHANGED: (
        'round',
        'user_id',
        'character_name',
        'kind',
        'magnitude',
        'rolls',
        'amount',
        'before',
        'after',
        'max_hp',
        'downed',
        'injury_roll',
    ),
    # NPC 의 변화는 주사위의 눈, 양, 바뀐 생사만 보인다. HP 의 숫자(before, after, max_hp)는 GM 만 안다.
    # 몸 상태(condition)도 서술자에게 주는 말이라 내보내지 않는다. 이름은 장면에서 부르는 이름이다
    EventType.NPC_CHANGED: (
        'round',
        'entry_id',
        'name',
        'kind',
        'magnitude',
        'rolls',
        'amount',
        'lethal',
        'status',
        'injury_roll',
    ),
    # 몬스터의 변화도 NPC 와 같다. 주사위의 눈, 양, 바뀐 생사만 보인다. 이름은 장면에서 부르는 이름이다(수로 쥐 2)
    EventType.MONSTER_CHANGED: (
        'round',
        'monster_id',
        'name',
        'kind',
        'magnitude',
        'rolls',
        'amount',
        'lethal',
        'status',
    ),
    # 몬스터의 공격은 무엇으로 누구를 쳤고 맞혔는지만 보인다.
    # 굴림의 보정과 합은 몬스터의 능력치를 드러내서 싣지 않는다. 맞은 캐릭터의 HP 는 뒤따르는 hp_changed 에 있다
    EventType.MONSTER_ATTACKED: (
        'round',
        'monster_id',
        'name',
        'attack',
        'user_id',
        'character_name',
        'success',
    ),
    # 부상은 공개다. 누가 무엇을 입었고 언제 풀리는지(짧은 것은 라운드, 오래 가는 것은 게임 안의 시각).
    # 캐릭터면 user_id 와 이름, NPC 면 항목의 id 와 장면의 호칭이다
    EventType.INJURY_GAINED: (
        'round',
        'user_id',
        'character_name',
        'entry_id',
        'name',
        'injury',
        'source',
        'ends_after_round',
        'heals_at',
    ),
    EventType.INJURY_ENDED: ('round', 'user_id', 'character_name', 'entry_id', 'name', 'injury', 'reason'),
    # 치료의 결과도 공개다. 나을 시각과 치료 실패 표의 눈까지 보인다. HP 의 변화는 따로 적힌다
    EventType.INJURY_TREATED: (
        'round',
        'user_id',
        'character_name',
        'entry_id',
        'name',
        'injury',
        'treated',
        'heals_at',
        'healed',
        'mishap',
        'died',
    ),
    # 지목의 결과도 공개다. 맞았으면 진짜 이름이 보인다. 틀렸으면 정답의 흔적이 없다(name 이 null)
    EventType.NAMING_RESOLVED: ('round', 'character_name', 'guess', 'correct', 'entry_id', 'name', 'label', 'newly'),
    # 죽음의 굴림도 공개다
    EventType.DEATH_SAVE_ROLLED: (
        'round',
        'user_id',
        'character_name',
        'roll',
        'target',
        'success',
        'successes',
        'failures',
        'fate',
    ),
    EventType.CHARACTER_DIED: ('round', 'user_id', 'character_name', 'cause'),
    # 새 캐릭터의 숫자도 공개다. 시작할 때의 시트를 적는 것과 같다
    EventType.CHARACTER_JOINED: (
        'round',
        'user_id',
        'character_name',
        'replaces',
        'mode',
        'pregen_index',
        'number',
        'sheet',
        'place',
    ),
    EventType.ROUND_CLOSED: ('number', 'idle', 'reason'),
    # 실패의 이유도 보인다(timeout, cut_off …). 모델이 쓴 글이나 보낸 프롬프트는 싣지 않는다
    EventType.NARRATION_FAILED: ('round', 'reason'),
    EventType.NARRATION_CREDITS_SHORT: ('round', 'user_id'),
    EventType.MEMBER_DROPPED: ('round', 'user_id', 'character_name'),
    EventType.NARRATION_CREDITS_RELEASED: ('round',),
    EventType.TABLE_ENDED: (),
}


def visible_payload(event: TableEvent) -> dict:
    """이벤트의 payload 에서 앉은 사람에게 내보내는 칸만 고른다."""
    fields = VISIBLE.get(EventType(event.type), ())
    return {field: event.payload[field] for field in fields if field in event.payload}


def to_event(event: TableEvent) -> EventOut:
    """이벤트를 앉은 사람에게 보여 주는 응답으로 바꾼다. 칸을 하나씩 적어 옮긴다."""
    return EventOut(
        sequence=event.sequence,
        type=event.type,
        actor_id=event.actor_id,
        payload=visible_payload(event),
        caused_by_sequence=event.caused_by_sequence,
        action_group_id=event.action_group_id,
        created_at=event.created_at,
    )


@router.get('', response_model=EventPage, status_code=status.HTTP_200_OK)
async def list_events(
    table_id: uuid.UUID,
    user: CurrentUser,
    session: Session,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_EVENT_LIMIT,
) -> EventPage:
    """
    테이블의 이벤트를 일어난 순서대로 돌려준다. after 를 주면 그 번호 뒤의 것만 온다.

    처음에는 after 없이 읽고, 그 뒤로는 마지막으로 받은 번호를 after 로 준다. 못 본 것만 받는다.
    """
    table, events = await service.list_events(session, user.user_id, table_id, after, limit)
    return EventPage(items=[to_event(event) for event in events], last_sequence=table.last_sequence)
