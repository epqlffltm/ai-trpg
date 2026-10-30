# trpg-server/app/events/responses.py

"""
이벤트를 앉은 사람에게 보여 주는 응답으로 바꾼다. 종류마다 내보내는 칸(VISIBLE)을 여기서 정한다.

HTTP 를 모른다. 이벤트 API(app/events/router.py)와 실시간 스트림(app/realtime/service.py)이 함께 쓴다.
스트림은 라우터를 불러오지 않는다. 같은 이벤트가 두 길에서 같은 모양으로 나간다.
"""

from app.events.models import EventType, TableEvent
from app.events.schemas import EventOut

# 종류마다 앉은 사람에게 내보내는 payload 의 칸.
# 여기에 적지 않은 칸은 나가지 않는다. 여기에 없는 종류는 payload 가 통째로 비어서 나간다.
# 나중에 AI 호출이나 GM 만 아는 판정을 이벤트로 적어도, 이 목록에 올리기 전에는 플레이어에게 보이지 않는다
VISIBLE: dict[EventType, tuple[str, ...]] = {
    EventType.TABLE_CREATED: ('narration_model', 'recommended_model', 'input_step', 'output_step'),
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
    EventType.NARRATION_MODEL_CHANGED: ('narration_model', 'input_step', 'output_step', 'round', 'price'),
    EventType.CREDIT_WAIT_CHANGED: ('credit_wait_seconds', 'remove_short_payers'),
    EventType.WHISPER_NOTICE_CHANGED: ('whisper_notice',),
    EventType.REFERENCES_CHANGED: ('references_enabled',),
    EventType.FRIENDLY_FIRE_CHANGED: ('friendly_fire',),
    EventType.FRIENDLY_FIRE_CONSENT_CHANGED: ('user_id', 'friendly_fire'),
    EventType.LEDGER_DRAFTS_CHANGED: ('ledger_drafts',),
    # 소지품은 공개다. 누가 무엇을 몇 개 받거나 잃었고, 그 뒤에 몇 개인가.
    # 몬스터를 쓰러뜨려 얻었으면 라운드, 출처(source: monster, 그 마리와 장면의 호칭), 상한을 넘어 잃은 개수가 더 있다.
    # NPC 를 쓰러뜨려 얻었으면 출처가 npc 이고 그 인물(npc_id)과 장면의 호칭(npc_name)이 있다.
    # 장소에서 주웠거나 찾았으면 라운드, 출처(source: place, search), 장소(place)가 더 있다
    EventType.ITEMS_GAINED: (
        'round',
        'user_id',
        'character_name',
        'entry_id',
        'name',
        'count',
        'total',
        'lost',
        'source',
        'monster_id',
        'monster_name',
        'npc_id',
        'npc_name',
        'place',
    ),
    EventType.ITEMS_LOST: ('user_id', 'character_name', 'entry_id', 'name', 'count', 'total'),
    # 물건을 쓰고 건넨 것도 공개다. 못 했으면 까닭(reason)이 있다
    # 푼 부상(cured)은 이름표와 이름만 있다. 후유증은 그 뒤의 부상의 이벤트에 있다(#277)
    EventType.ITEM_USED: (
        'round',
        'character_name',
        'entry_id',
        'name',
        'used',
        'reason',
        'target',
        'remaining',
        'cured',
        'injured',
    ),
    # 기술을 쓴 것도 공개다(#805). 낸 비용과 맞춘 수치는 뒤의 resource_changed 에 있다(숨긴 수치는 숫자가 없다)
    EventType.SKILL_USED: ('round', 'character_name', 'skill', 'name', 'used', 'reason', 'target', 'cured', 'injured'),
    # 던진 것도 공개다(#277). 판정의 숫자는 뒤의 check_rolled 에, 맞은 쪽의 변화는 그 뒤의 이벤트에 있다
    EventType.ITEM_THROWN: (
        'round',
        'character_name',
        'entry_id',
        'name',
        'thrown',
        'reason',
        'target',
        'remaining',
        'cured',
        'injured',
    ),
    # 붙여 쓴 물건도 공개다(#802). 판정과 같이 보인다
    EventType.AID_USED: (
        'round',
        'character_name',
        'act',
        'entry_id',
        'name',
        'bonus',
        'lost',
        'broken',
        'remaining',
    ),
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
    # 내려놓은 것도 공개다. 놓은 곳이 있고, 못 했으면 까닭(reason)이 있다
    EventType.ITEM_PUT_DOWN: (
        'round',
        'character_name',
        'place',
        'entry_id',
        'name',
        'count',
        'put',
        'reason',
        'remaining',
    ),
    # 덫을 놓은 것도 공개다(#806). 선언이 모두에게 보이듯이. 놓은 곳이 있고, 못 했으면 까닭(reason)이 있다
    EventType.TRAP_SET: (
        'round',
        'character_name',
        'place',
        'entry_id',
        'name',
        'set',
        'reason',
        'remaining',
    ),
    # 덫이 터진 것도 공개다(#806). 누가 어디서 무엇을 터뜨렸고, 피하는 판정과 피했는가. 효과는 뒤의 이벤트에 있다
    EventType.TRAP_SPRUNG: (
        'round',
        'user_id',
        'character_name',
        'place',
        'entry_id',
        'name',
        'set_by',
        'avoid',
        'avoided',
    ),
    # 착용도 공개다(#276). 소지품처럼 모두에게 보인다
    EventType.EQUIPMENT_CHANGED: ('user_id', 'character_name', 'change', 'entry_id', 'name', 'slots', 'removed'),
    # 사고판 것과 돈을 건넨 것도 공개다(#278). 소지품과 돈은 모두에게 보인다. 못 했으면 까닭(reason)이 있다
    EventType.ITEM_TRADED: (
        'round',
        'user_id',
        'character_name',
        'side',
        'npc_id',
        'npc_name',
        'entry_id',
        'name',
        'count',
        'price',
        'traded',
        'reason',
        'total',
        'money',
    ),
    EventType.MONEY_PAID: (
        'round',
        'user_id',
        'character_name',
        'amount',
        'paid',
        'reason',
        'target',
        'remaining',
        'target_total',
    ),
    # 훔치기의 판정은 다른 판정처럼 공개다. 대상의 능력치는 적지 않는다(목표값에 섞여 있다).
    # 대상이 몬스터면 monster_id·monster_name, NPC 면 npc_id·npc_name 이 있다. 들켜 싸움이 붙었으면 fight 가 참이다
    EventType.STEAL_ATTEMPTED: (
        'round',
        'character_name',
        'monster_id',
        'monster_name',
        'npc_id',
        'npc_name',
        'entry_id',
        'name',
        'check',
        'hindrance',
        'factors',
        'stolen',
        'count',
        'left',
        'total',
        'reason',
        'fight',
    ),
    # 퀘스트의 이름과 상태, 보상, 기한, 서버가 바꾼 까닭(기한을 넘김)은 공개다. 사건의 글(로어북)은 적지 않는다.
    # 숨긴 퀘스트에는 기한을 적지 않는다(드러날 때 정한다). 숨김에서 바로 끝낸 것도 기한이 비어 있다
    EventType.QUEST_CHANGED: ('entry_id', 'name', 'previous', 'status', 'rewards', 'consumed', 'due_at', 'reason'),
    EventType.CLOCK_STEP_CHANGED: ('previous', 'next_step_minutes', 'default'),
    # 캐릭터의 위치는 공개다. 아는 장소만 적히므로 숨긴 장소는 새지 않는다
    # 업혀 갔으면 업은 사람(carried_by)이 더 있다(#367)
    # 판의 사건이 옮겼으면 그 사건 항목(happening)이 더 있다
    # 지닌 열쇠로 잠긴 문을 열고 갔으면 unlocked, 빗장 쪽에서 빗장을 풀고 갔으면 unbarred 가 더 있다(#281).
    # 문이 열린 것은 맵에 보이므로 공개다
    EventType.CHARACTER_MOVED: (
        'round',
        'user_id',
        'character_name',
        'from',
        'to',
        'travel_minutes',
        'carried_by',
        'happening',
        'unlocked',
        'unbarred',
    ),
    # 판의 사건은 공개다. 일어난 것과 옮긴 것만 적는다. 조건은 적지 않는다(아직 일어나지 않은 사건이 드러나지 않게)
    EventType.HAPPENING_OCCURRED: ('round', 'entry_id', 'name', 'moves'),
    # 찾은 길은 공개다. 찾았으니 이제 모두가 아는 길이다. 굴린 판정은 처음부터 적지 않는다
    EventType.PLACE_SEARCHED: ('round', 'character_name', 'place', 'found', 'items'),
    # 문은 맵에 보이는 것이다. 무슨 열쇠로 했는지는 적지 않는다(#281)
    EventType.DOOR_CHANGED: ('round', 'user_id', 'character_name', 'act', 'device', 'from', 'to'),
    # 무작위 조우로 나온 무리는 일행이 서 있는 곳에 나오므로 공개다. 마리의 숫자(HP, 능력치)는 적지 않는다(#283)
    EventType.MONSTERS_APPEARED: ('round', 'place', 'monster', 'count', 'cause', 'surprise'),
    # 쉰 것과 그 회복, 깨진 까닭은 공개다. HP 는 다른 회복과 같이 보인다
    EventType.CHARACTER_RESTED: (
        'round',
        'user_id',
        'character_name',
        'cause',
        'length',
        'rested',
        'reason',
        'rolls',
        'before',
        'after',
        'max_hp',
    ),
    # 수치(#804)는 HP 처럼 공개다. 숨긴 수치는 아직 없다
    # 누구의 수치인지는 캐릭터(user_id), NPC(entry_id), 몬스터(monster_id) 중 하나와 그 이름(character_name)이다(#804)
    EventType.RESOURCE_CHANGED: (
        'round',
        'user_id',
        'entry_id',
        'monster_id',
        'character_name',
        'resource',
        'name',
        'before',
        'after',
        'max',
        'source',
        'visibility',
    ),
    # 되살아나기의 굴림은 죽음의 굴림처럼 공개다
    EventType.CHARACTER_REVIVED: ('round', 'user_id', 'character_name', 'roll', 'target', 'success', 'hp'),
    # 누가 누구에게 보냈는지만 보인다. 쪽지의 글은 처음부터 적지 않는다
    EventType.WHISPER_SENT: ('user_id', 'character_name', 'recipient_id', 'recipient_character_name'),
    EventType.TABLE_STARTED: ('members',),
    EventType.GM_NARRATION: ('text',),
    # 게임 안의 시각은 공개다. 모두 같은 때에 있다
    EventType.ROUND_OPENED: (
        'number',
        'deadline_at',
        'narration_model',
        'input_step',
        'output_step',
        'price',
        'clock',
        'passed_minutes',
    ),
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
        # 타격에 장비가 든 것(#276). 무기, 맞은 부위, 그 부위의 방어다. 착용은 모두에게 보인다
        'blow',
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
        # 동료의 장난(#803)이었으면 참이다. 장난이 아니면 칸이 없다
        'prank',
        # 피해의 성질과 받은 단계(#886 ③). 성질이 없으면 칸이 없다
        'nature',
    ),
    # NPC 의 변화는 주사위의 눈, 양, 바뀐 생사만 보인다. HP 의 숫자(before, after, max_hp)는 GM 만 안다.
    # 몸 상태(condition)도 서술자에게 주는 말이라 내보내지 않는다. 이름은 장면에서 부르는 이름이다
    # 태도는 공개다. 이름은 장면의 호칭이다(진짜 이름이 드러나기 전이면 진짜 이름이 아니다)
    EventType.NPC_ATTITUDE_CHANGED: ('round', 'entry_id', 'name', 'previous', 'attitude', 'reason'),
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
        'nature',
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
        'injury_roll',
        'nature',
    ),
    # 몬스터의 공격은 무엇으로 누구를 쳤고 맞혔는지만 보인다.
    # 굴림의 보정과 합은 몬스터의 능력치를 드러내서 싣지 않는다. 맞은 캐릭터의 HP 는 뒤따르는 hp_changed 에 있다.
    # 쓰러진 캐릭터를 쳤으면 쌓인 죽음의 굴림 실패(downed_strike)가 있다. 죽음의 굴림처럼 공개다(#369)
    EventType.MONSTER_ATTACKED: (
        'round',
        'monster_id',
        'name',
        'attack',
        'user_id',
        'character_name',
        'success',
        'downed_strike',
        # 공격에 장비가 든 것(#276). 무기와 그 공격 보정, 맞은 부위, 그 부위의 방어다
        'blow',
    ),
    # NPC 의 공격도 몬스터와 같다. 무엇으로 누구를 쳤고 맞혔는지만 보인다. 굴림과 부상의 영향은 싣지 않는다.
    # 이름은 장면에서 부르는 이름이다
    EventType.NPC_ATTACKED: (
        'round',
        'entry_id',
        'name',
        'attack',
        'user_id',
        'character_name',
        'success',
        'downed_strike',
        'blow',
    ),
    # 부상은 공개다. 누가 무엇을 입었고 언제 풀리는지(짧은 것은 라운드, 오래 가는 것은 게임 안의 시각).
    # 캐릭터면 user_id 와 이름, NPC 면 항목의 id 와 장면의 호칭이다
    # 누구인지는 캐릭터(user_id, character_name), NPC(entry_id, name), 몬스터(monster_id, name, #799) 중 하나다
    EventType.INJURY_GAINED: (
        'round',
        'user_id',
        'character_name',
        'entry_id',
        'monster_id',
        'name',
        'injury',
        'source',
        'ends_after_round',
        'heals_at',
    ),
    EventType.INJURY_ENDED: (
        'round',
        'user_id',
        'character_name',
        'entry_id',
        'monster_id',
        'name',
        'injury',
        'reason',
    ),
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
        # 치료에 붙여 쓴 물건(#277). 적지 않았으면 없다
        'aid',
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
    EventType.NARRATION_ABANDONED: ('round', 'reason', 'failures'),
    EventType.NARRATION_CREDITS_SHORT: ('round', 'user_id', 'reason'),
    EventType.NARRATION_MODEL_NOT_FOR_SALE: ('round', 'narration_model'),
    EventType.NARRATION_MODEL_RETIRING: ('narration_model', 'retires_on', 'days_left'),
    EventType.NARRATION_MODEL_REPLACED: ('from', 'narration_model', 'reason', 'round', 'price'),
    EventType.NARRATION_MODEL_UNAVAILABLE: ('narration_model', 'reason'),
    EventType.MEMBER_DROPPED: ('round', 'user_id', 'character_name'),
    EventType.NARRATION_CREDITS_RELEASED: ('round',),
    # 누가 끝냈는가. 운영자가 끝냈으면 'operator' 다(#392). 방장이 끝냈으면 없다(actor_id 가 방장). 사유는 싣지 않는다
    EventType.TABLE_ENDED: ('by',),
}


# 가진 사람만 보는 수치(#804)의 바뀐 것은 숫자를 빼고 내보낸다. 이벤트는 앉은 사람 모두가 읽는다.
# 엔진만 보는 수치는 처음부터 적지 않는다(app/rounds/records.py)
HIDDEN_NUMBERS = ('before', 'after', 'max')


def visible_payload(event: TableEvent) -> dict:
    """이벤트의 payload 에서 앉은 사람에게 내보내는 칸만 고른다."""
    type_ = EventType(event.type)
    fields = VISIBLE.get(type_, ())
    if type_ == EventType.RESOURCE_CHANGED and event.payload.get('visibility', 'everyone') != 'everyone':
        fields = tuple(field for field in fields if field not in HIDDEN_NUMBERS)
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
