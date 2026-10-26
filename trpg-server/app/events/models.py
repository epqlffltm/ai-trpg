# trpg-server/app/events/models.py

"""
테이블의 이벤트 기록. 테이블에서 일어난 일을 일어난 순서대로 적어 둔 장부다.

사실의 기준은 현재 상태다(game_tables, table_members, table_rounds). 이벤트는 그 옆에 덧붙이는 기록이다.
"지금 어떤가"는 상태에서 읽고, "어떻게 여기까지 왔나"는 이벤트에서 읽는다.
이벤트만으로 상태를 다시 계산하지 않는다(완전한 event sourcing 이 아니다).

규칙 둘.
  - 덧붙이기만 한다. 적은 이벤트는 고치지 않고 지우지 않는다.
  - 상태를 바꾼 것과 같은 묶음(트랜잭션)으로 저장한다. 상태만 바뀌거나 기록만 남는 일이 없다.

스키마 이름을 적지 않는다. 연결의 search_path 가 정한다(app/core/database.py).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EventType(enum.StrEnum):
    """
    이벤트의 종류. 지금 실제로 일어나는 일만 있다.

    주사위, 판정, 상태 변경, AI 호출은 엔진과 AI 를 붙일 때 더한다.

    DB 에는 CHECK 조건을 걸지 않는다. 종류는 계속 늘어나는데, 걸어 두면 늘릴 때마다 마이그레이션이 필요하다.
    이벤트를 적는 길은 하나뿐이고(app/events/recorder.py), 그 함수가 이 형식만 받는다.
    """

    # --- 자리 ---
    # 테이블이 만들어졌다. 만든 사람이 방장이 되어 앉았다
    TABLE_CREATED = 'table_created'
    # 누가 들어와 앉았다
    MEMBER_JOINED = 'member_joined'
    # 누가 스스로 나갔다
    MEMBER_LEFT = 'member_left'
    # 방장이 누구를 내보냈다
    MEMBER_KICKED = 'member_kicked'
    # 방장이 바뀌었다. 넘겼거나, 방장이 나가서 다음 사람이 됐다
    HOST_CHANGED = 'host_changed'
    # 누가 능력치의 점수를 주사위로 굴렸다. 굴린 것은 서버다. 굴려 달라고 한 사람이 actor 다
    ABILITIES_ROLLED = 'abilities_rolled'
    # 방장이 누구에게 "한 번 더 굴리기"를 줬다
    REROLL_GRANTED = 'reroll_granted'
    # 방장이 GM 의 서술 문체를 바꿨다. 다음 서술부터 그 문체다
    NARRATION_STYLE_CHANGED = 'narration_style_changed'
    # 방장이 라운드의 시간 제한을 바꿨다. 다음 라운드부터 쓴다
    ROUND_TIME_LIMIT_CHANGED = 'round_time_limit_changed'
    # 방장이 서술 등급을 바꿨다. 서술 등급을 없앤 뒤로는 적지 않는다. 그 전에 적은 이벤트를 읽으려고 남긴다
    NARRATION_TIER_CHANGED = 'narration_tier_changed'
    # 방장이 서술 모델을 바꿨다. 다음 라운드부터 그 모델이다
    NARRATION_MODEL_CHANGED = 'narration_model_changed'
    # 방장이 크레딧이 모자란 사람을 기다리는 규칙(시간, 자동으로 빼기)을 바꿨다
    CREDIT_WAIT_CHANGED = 'credit_wait_changed'
    # 방장이 쪽지를 보낸 사실을 알릴지(whisper_notice)를 바꿨다. 바꾼 뒤에 보내는 쪽지부터 따른다
    WHISPER_NOTICE_CHANGED = 'whisper_notice_changed'
    # 방장이 참고 자료를 서술에 넣을지(references_enabled)를 바꿨다. 모집 중에만 바뀐다(#482)
    REFERENCES_CHANGED = 'references_changed'
    # 방장이 장부 초안을 쓸지(ledger_drafts)를 바꿨다. 장부 초안은 없어졌다(#371). 이제 생기지 않는다.
    # 그 전에 적힌 이벤트를 읽을 수 있게 종류만 남긴다
    LEDGER_DRAFTS_CHANGED = 'ledger_drafts_changed'
    # 누가 누구에게 쪽지를 보냈다. 테이블이 알리기로 했을 때만 적는다. 쪽지의 글은 싣지 않는다(app/whispers/)
    WHISPER_SENT = 'whisper_sent'

    # --- 진행 ---
    # 방장이 테이블을 시작했다
    TABLE_STARTED = 'table_started'
    # GM 이 장면을 서술했다. 첫 서술은 스타팅이다
    GM_NARRATION = 'gm_narration'
    # 라운드가 열렸다. 선언을 받기 시작했다
    ROUND_OPENED = 'round_opened'
    # 플레이어가 선언한 행동. 라운드가 닫힐 때 마지막 글만 적는다
    PLAYER_ACTION = 'player_action'
    # 엔진이 행동을 판정했다. 주사위의 눈과 성패가 적힌다. 원인은 그 행동의 이벤트다
    CHECK_ROLLED = 'check_rolled'
    # 엔진이 캐릭터의 HP 를 바꿨다. 피해나 회복이다. 원인은 그 판정의 이벤트다
    HP_CHANGED = 'hp_changed'
    # 엔진이 NPC 의 HP 와 생사를 바꿨다. 피해나 회복이다. 원인은 그 판정의 이벤트다
    NPC_CHANGED = 'npc_changed'
    # 엔진이 NPC 의 태도(우호, 중립, 적대)를 바꿨다(app/tables/npc_attitudes.py). 원인은 그렇게 만든 일의 이벤트다
    NPC_ATTITUDE_CHANGED = 'npc_attitude_changed'
    # 엔진이 몬스터 한 마리의 HP 와 생사를 바꿨다. 피해다. 원인은 그 판정의 이벤트다
    MONSTER_CHANGED = 'monster_changed'
    # 엔진이 몬스터 한 마리의 차례에 캐릭터 하나를 공격으로 쳤다. 공격, 대상, 성패가 적힌다.
    # 맞혔으면 그 캐릭터의 HP 의 변화가 이 이벤트를 원인으로 뒤따른다. 원인은 없다(엔진의 차례다)
    MONSTER_ATTACKED = 'monster_attacked'
    # 엔진이 싸우는 NPC 의 차례에 캐릭터 하나를 공격으로 쳤다(#487). 몬스터의 것과 같은 모양이다.
    # 맞혔으면 그 캐릭터의 HP 의 변화가 이 이벤트를 원인으로 뒤따른다. 원인은 없다(엔진의 차례다)
    NPC_ATTACKED = 'npc_attacked'
    # 캐릭터나 NPC 가 부상을 입었다. 큰 타격이나 쓰러짐에 부상 표를 굴렸거나(원인은 그 HP 의 변화의 이벤트다),
    # 노려 쳤거나, 오래 가는 부상이 나을 때 후유증 표를 굴렸다(원인은 그 부상이 끝난 이벤트다)
    INJURY_GAINED = 'injury_gained'
    # 부상이 끝났다. 정한 라운드가 지나 풀렸거나 나았다(라운드가 닫힐 때), 또는 치료로 나았다
    # (원인은 그 치료의 이벤트다), 또는 소모품으로 풀었다(reason cured, 원인은 그 물건을 쓴 이벤트다, #277)
    INJURY_ENDED = 'injury_ended'
    # 엔진이 치료의 결과를 정했다. 나을 라운드의 변화, 치료 실패 표의 결과가 적힌다. 원인은 그 판정의 이벤트다
    INJURY_TREATED = 'injury_treated'
    # 엔진이 지목의 결과를 정했다. 짚은 이름이 맞았는지와, 맞았으면 진짜 이름이 적힌다. 원인은 그 행동의 이벤트다
    NAMING_RESOLVED = 'naming_resolved'
    # 엔진이 쓰러진 캐릭터의 죽음의 굴림을 굴렸다. 라운드가 닫힐 때다
    DEATH_SAVE_ROLLED = 'death_save_rolled'
    # 캐릭터가 죽었다. 죽음의 굴림으로(원인은 그 굴림의 이벤트다), 치료 실패의 즉사로(원인은 그 치료의 이벤트다),
    # 또는 플레이어가 스스로 보내서
    CHARACTER_DIED = 'character_died'
    # 캐릭터가 죽은 플레이어가 새 캐릭터를 들였다. 새 캐릭터가 받은 시트가 적힌다
    CHARACTER_JOINED = 'character_joined'
    # 캐릭터가 물건을 얻었다. 무엇을 몇 개, 그 뒤에 몇 개가 됐는가. 엔진이 줬다(행한 사람이 없다).
    # 몬스터나 NPC 를 쓰러뜨려(app/rounds/drops.py), 줍거나 찾아서, 훔치거나 빼앗아서다.
    # 방장이 주던 길을 지우기 전(#367)에 적힌 것은 행한 사람이 방장이다
    ITEMS_GAINED = 'items_gained'
    # 방장이 캐릭터에게서 물건을 빼앗았다. 그 길을 지운 뒤로는 적지 않는다(#367). 그 전에 적힌 것을 읽으려고 남긴다
    ITEMS_LOST = 'items_lost'
    # 캐릭터가 소모품을 썼다(또는 쓰려 했지만 못 했다). 원인은 그 행동의 이벤트다. 회복했으면 바로 뒤에 HP 의 변화
    ITEM_USED = 'item_used'
    # 캐릭터가 다른 캐릭터에게 물건을 건넸다(또는 건네려 했지만 못 했다). 원인은 그 행동의 이벤트다
    ITEM_GIVEN = 'item_given'
    # 캐릭터가 소모품을 몬스터나 인물에게 던졌다(또는 던지려 했지만 못 했다, #277). 원인은 그 행동의 이벤트다.
    # 던졌으면 바로 뒤에 그 판정(check_rolled)과 맞은 쪽의 변화가 잇는다
    ITEM_THROWN = 'item_thrown'
    # 캐릭터가 따기, 부수기, 고치기, 넘기의 판정에 물건을 붙여 썼다(#802, 거들기). 그 판정(check_rolled) 바로 뒤에
    # 잇는다. 더한 보정, 하나 없어졌는가, 실패해서 부러졌는가, 남은 개수. 치료에 붙여 쓴 것은 injury_treated 의 aid 다
    AID_USED = 'aid_used'
    # 캐릭터가 가진 물건을 서 있는 장소에 내려놓았다(또는 내려놓으려 했지만 못 했다). 원인은 그 행동의 이벤트다
    ITEM_PUT_DOWN = 'item_put_down'
    # 캐릭터가 장비를 착용하거나 벗었다(#276). 본인이 화면에서 바꿨다(행한 사람이 본인). 무엇을 어느 칸에,
    # 끼우느라 함께 빠진 것. 소지품이 줄어 저절로 벗은 것은 적지 않는다(그 일의 이벤트에 소지품이 있다)
    EQUIPMENT_CHANGED = 'equipment_changed'
    # 캐릭터가 장면의 상인에게서 물건을 샀거나 상인에게 팔았다(또는 하려 했지만 못 했다, #278).
    # 무엇을 몇 개, 오간 돈, 그 뒤에 가진 개수와 돈. 원인은 그 행동의 이벤트다
    ITEM_TRADED = 'item_traded'
    # 캐릭터가 다른 캐릭터에게 돈을 건넸다(또는 건네려 했지만 못 했다, #278). 원인은 그 행동의 이벤트다
    MONEY_PAID = 'money_paid'
    # 캐릭터가 몬스터나 NPC 가 지닌 물건을 훔치려 했다(app/rounds/steals.py). 굴린 판정과 훔쳤는지, 들켰는지.
    # 원인은 그 행동의 이벤트다. NPC 의 태도가 바뀌었으면 npc_attitude_changed 가,
    # 훔쳤으면 items_gained(source 가 steal)가 그 뒤에 잇는다
    STEAL_ATTEMPTED = 'steal_attempted'
    # 엔진이 퀘스트의 상태를 바꿨다(app/rounds/quest_goals.py, app/rounds/deadlines.py).
    # 사람(방장)은 바꾸지 못한다(#367).
    # 무엇에서 무엇으로, 성공이면 누가 무엇을 받았는가, 바꾼 까닭(reason). 숨김으로 바꾸는 일은 없다
    QUEST_CHANGED = 'quest_changed'
    # 방장이 다음 라운드가 열릴 때 흐를 게임 안의 시간을 정했다. 몇 분에서 몇 분으로.
    # 방장이 정하는 길을 없앤 뒤로는 적지 않는다(#367, 기다리기가 대신한다). 그 전에 적은 이벤트를 읽으려고 남긴다.
    # 시각이 흐른 것은 따로 적지 않는다. 라운드가 열린 이벤트에 그때의 시각과 흐른 분이 있다
    CLOCK_STEP_CHANGED = 'clock_step_changed'
    # 캐릭터가 맵의 다른 장소로 옮겨 갔다. 누가, 어디에서, 어디로.
    # 방장이 옮기던 길을 지우기 전(#367)에 적힌 것은 행한 사람이 방장이다. 선언 행동으로 한 칸 갔으면
    # (app/rounds/map_actions.py) 행한 사람이 없고, 그 행동의 이벤트에 이어지며 라운드의 번호가 있다.
    # 쓰러진 동료를 업고 갔으면 업힌 사람의 것이 업은 사람의 것에 이어지고 업은 사람(carried_by)이 적힌다(#367).
    # 판의 사건이 옮겼으면 그 사건(happening_occurred)에 이어지고 사건 항목(happening)이 적힌다.
    # 아는 장소로만 가므로 숨긴 장소는 이 이벤트로 새지 않는다
    CHARACTER_MOVED = 'character_moved'
    # 판의 사건이 일어났다(app/rounds/happenings.py, #367). 조건이 채워져 엔진이 한 번 일으켰다. 행한 사람이 없다.
    # 어느 사건(사건 항목과 이름)이 몇째 라운드에 누구를 어디에서 어디로 옮겼는가. 조건은 적지 않는다
    HAPPENING_OCCURRED = 'happening_occurred'
    # 캐릭터가 서 있는 곳에서 숨긴 길을 찾았다(app/rounds/map_actions.py). 찾은 길만 적는다. 못 찾았으면 빈 목록이다.
    # 굴린 판정은 적지 않는다. 숨긴 길이 있었는지가 드러난다
    PLACE_SEARCHED = 'place_searched'
    # 캐릭터가 길의 문을 잠그거나 열거나 따거나 부수거나 고치거나 자물쇠를 바꿨다(app/rounds/door_actions.py, #281).
    # 해낸 것만 적는다. 누가, 무엇을(act: lock, unlock, pick, force, repair, replace), 무엇으로(device: lock, bar),
    # 어느 길의(from, to). 문은 맵에 보인다
    DOOR_CHANGED = 'door_changed'
    # 무작위 조우(app/rounds/wanders.py, #283). 길을 오거나 길게 쉰 장소에서 엔진이 굴려 몬스터가 나왔다.
    # 행한 사람이 없다. 어디에(place), 무엇이(monster: id, name), 몇 마리(count), 무엇이 불렀나(cause: arrive, rest),
    # 누가 기습하나(surprise). 일행이 서 있는 곳에만 나오므로 드러나도 된다
    MONSTERS_APPEARED = 'monsters_appeared'
    # 캐릭터가 쉬었다(app/rounds/rests.py). 쉬는 행동을 선언했거나(cause: rest), 시간이 흘러 저절로 회복했다
    # (cause: natural). 선언한 휴식이 다쳐서 깨졌으면 rested 가 false 이고 까닭(reason)이 있다
    CHARACTER_RESTED = 'character_rested'
    # 고비를 넘기고 쓰러져 있던 캐릭터가 오래 쉬어 되살아나기를 굴렸다(app/rounds/rests.py). 성공이면 HP 1 로 일어났다
    CHARACTER_REVIVED = 'character_revived'
    # 라운드가 닫혔다
    ROUND_CLOSED = 'round_closed'
    # GM 의 서술이 끝내 실패했다. 라운드는 닫는 중에 머물고, 방장이 다시 맡길 수 있다
    NARRATION_FAILED = 'narration_failed'
    # GM 의 서술이 정해 둔 횟수만큼 실패해 서술을 그만뒀다. 서술 값은 받지 않는다(돌려준다).
    # 엔진이 정한 결과의 줄로 다음 라운드를 연다(app/rounds/service.py 의 abandon_narration)
    NARRATION_ABANDONED = 'narration_abandoned'
    # 이 라운드의 서술 값을 내는 사람 하나(user_id)의 크레딧이 모자란다. 걸어 보고 알았다(app/billing/).
    # 그 사람이 충전하지 않거나 방장이 내보내지 않으면 라운드를 닫을 때 서술이 실패한다(insufficient_credits)
    NARRATION_CREDITS_SHORT = 'narration_credits_short'
    # 라운드의 서술 모델을 결제 서버가 팔지 않는다(판매를 멈췄거나 아직 열지 않았다). 라운드마다 처음 알았을 때 한 번.
    # 방장이 모델을 바꾸면 그 라운드의 청구를 새 가격표로 다시 건다. 바꾸지 않으면 서술이 실패한다(model_not_for_sale)
    NARRATION_MODEL_NOT_FOR_SALE = 'narration_model_not_for_sale'
    # 테이블의 서술 모델이 곧 은퇴한다. 30, 14, 7, 1 일 남았을 때 한 번씩(app/tables/model_retirement.py)
    NARRATION_MODEL_RETIRING = 'narration_model_retiring'
    # 서술 모델이 은퇴해 서버가 같은 회사의 다른 모델로 바꿨다. 아직 서술하지 않은 지금 라운드도 바꿨으면 round 가 있다
    NARRATION_MODEL_REPLACED = 'narration_model_replaced'
    # 서술 모델이 은퇴했는데 같은 회사에 대신할 모델이 없다. 방장이 모델을 골라야 서술한다
    NARRATION_MODEL_UNAVAILABLE = 'narration_model_unavailable'
    # 크레딧이 모자란 사람을 기다리는 시간이 지나 서버가 그 사람을 자리에서 뺐다. 나머지로 다시 서술한다
    MEMBER_DROPPED = 'member_dropped'
    # 크레딧이 모자란 사람을 기다리는 시간이 지나 낼 수 있는 사람의 값을 돌려줬다. 라운드는 멈춘 채로 있다
    NARRATION_CREDITS_RELEASED = 'narration_credits_released'
    # 테이블이 끝났다
    TABLE_ENDED = 'table_ended'


class TableEvent(Base):
    """
    이벤트 하나.

    sequence 는 테이블 안에서의 순서다. 1 부터 빈 번호 없이 올라간다.
    읽는 쪽은 "17 번 뒤의 것을 달라"고 한다. 시각은 같을 수 있지만 번호는 겹치지 않는다.
    """

    __tablename__ = 'table_events'
    __table_args__ = (
        CheckConstraint('sequence >= 1', name='sequence_positive'),
        # 원인은 결과보다 먼저 일어난다
        CheckConstraint('caused_by_sequence < sequence', name='cause_comes_first'),
        # 한 테이블에 같은 번호의 이벤트가 둘일 수 없다. 번호를 잘못 매기면 DB 가 막는다.
        # 이 조건이 만드는 색인이 "이 테이블의 N 번 뒤"를 찾는 데도 쓰인다
        UniqueConstraint('table_id', 'sequence'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 어느 테이블의 이벤트인가. 테이블의 행이 지워지면 함께 지워진다
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('game_tables.id', ondelete='CASCADE'))

    # 테이블 안에서의 순서. 테이블이 센다(game_tables.last_sequence)
    sequence: Mapped[int] = mapped_column(Integer)

    type: Mapped[str] = mapped_column(String(40))

    # 이 일을 한 사람. 인증 서버의 public_id 다. 사람이 한 일이 아니면 비어 있다(GM 의 서술, 저절로 닫힌 라운드)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)

    # 종류마다 다른 내용. 어떤 칸이 들어가는지는 적는 쪽(app/events/recorder.py 를 부르는 곳)이 정한다.
    # 큰 문서를 넣지 않는다. 판의 복사본, GM 전용 글, 초대 코드, 비밀번호는 여기에 적지 않는다
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 이 이벤트를 일으킨 이벤트의 번호. 같은 테이블의 것이다. 없으면 비어 있다.
    # "방장이 나갔다 → 방장이 바뀌었다"처럼 원인과 결과를 잇는다
    caused_by_sequence: Mapped[int | None] = mapped_column(Integer)

    # 요청 하나가 낳은 이벤트들의 묶음. 같은 묶음의 이벤트는 함께 저장됐다.
    # 선언 하나로 라운드가 닫히면 행동, 닫힘, 서술, 열림이 한 묶음이다.
    # 나중에 "마지막 턴 되돌리기"를 만들 때 이 묶음이 단위가 된다
    action_group_id: Mapped[uuid.UUID] = mapped_column(Uuid)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
