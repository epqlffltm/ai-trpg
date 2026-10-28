# trpg-server/app/rounds/schemas.py

"""
라운드 API 가 받는 입력과 내보내는 응답의 모양.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.assets.models import ItemRarity, NpcAttitude
from app.calendar.schemas import ClockTimeOut
from app.engine.action import Action
from app.engine.death import Fate
from app.engine.health import ChangeKind
from app.engine.ruleset import ResistLevel
from app.rounds.models import DECLARATION_MAX_LENGTH, RoundStatus
from app.tables.models import NpcStatus
from app.tables.schemas import ResourceOut

# 선언의 글. 공백이 아닌 글자가 하나는 있어야 한다. 앞뒤 공백은 떼지 않는다
DeclarationContent = Annotated[str, StringConstraints(pattern=r'\S', max_length=DECLARATION_MAX_LENGTH)]


class DeclarationUpdate(BaseModel):
    """
    선언을 낼 때 받는 값. 다시 내면 앞의 것을 통째로 바꾼다. 행동을 빼고 다시 내면 행동도 없어진다.

    행동은 하나만 붙인다. 한 사람이 한 라운드에 주사위를 한 번 굴린다.
    행동은 판정(check), 치료(treat), 지목(name), 물건 쓰기(use), 건네기(give)다. 행동이 없으면 판정이 없는 선언이다.
    """

    model_config = ConfigDict(extra='forbid')

    content: DeclarationContent
    action: Action | None = None


class InjuryRollOut(BaseModel):
    """
    부상이 생긴 일. 큰 타격이나 쓰러짐에 엔진이 부상 표를 굴렸거나, 노려 친 타격이 성공했거나,
    오래 가는 부상이 나을 때 후유증 표를 굴렸다.

    injury 는 나온 부상의 이름표(규칙의 Injury.key)다. 부상이 없는 줄이면 None 이다.
    이름과 사실은 테이블의 rules 에 있다.
    """

    # big_hit(큰 타격), downed(쓰러짐), called_shot(노려 치기), aftermath(후유증)
    trigger: str
    # 부상 표의 눈. 노려 쳤으면 굴리지 않아서 None 이다
    roll: int | None
    injury: str | None
    # 짧은 부상이면 이 라운드가 닫힐 때 풀린다. 아니면 None 이다
    ends_after_round: int | None
    # 오래 가는 부상이면 이 게임 안의 시각이 지나면 낫는다. 아니면 None 이다(결손, 짧은 것, 이 단계 전의 기록)
    heals_at: ClockTimeOut | None = None
    # 나온 부상에 면역이라 입지 않았으면 그 부상의 이름표다(#799, 몬스터). 그때 injury 는 None 이다
    immune: str | None = None
    # 동료의 장난(#803)이라 입지 않은 오래 가는 부상이나 결손의 이름표다. 그때 injury 는 None 이다
    spared: str | None = None


class CalledShotOut(BaseModel):
    """노려 친 것. 무엇을 노렸는지와 판정이 얼마나 어려워졌는지다. 성공했으면 그 부상이 생긴다."""

    # 노린 부상의 이름표
    aim: str
    # target_plus(목표값을 amount 만큼 올림) 또는 disadvantage(두 번 굴려 낮은 눈)
    mode: str
    amount: int


class BlowWeaponOut(BaseModel):
    """타격에 쓴 무기(#276). 판의 물건과 그 이름과 판정의 보정에 더한 공격 보정이다."""

    entry_id: uuid.UUID
    name: str
    bonus: int
    # 관통력. 없으면 0 이다
    ap: int = 0


class PierceOut(BaseModel):
    """관통 굴림(#276). 눈 + 관통력(ap)이 target(그 부위의 방어 + 룰북의 기준값) 이상이면 관통이다."""

    roll: int
    ap: int
    target: int
    pierced: bool


class SaveOut(BaseModel):
    """
    세이브 굴림(#276). kind 는 armor(그 부위의 방어), cover(엄폐한 장소의 커버), ward(불굴) 중 하나다.
    눈 + value 가 target 이상이면 막았다.
    """

    kind: str
    value: int
    roll: int
    target: int
    saved: bool


class BlowOut(BaseModel):
    """
    타격에 장비가 든 것(#276). 엔진이 정했다. 무기, 맞은 부위, 노렸는가, 그 부위의 방어다.

    mode 는 룰북의 방어 방식이다. ac 면 방어가 목표값(target)에 이미 더해졌고, reduce 면 피해에서 빠졌다
    (변화의 rolls 를 더한 값과 amount 의 차이). 방어 방식이 없는 규칙이면 None 이고 부위도 없다.
    """

    weapon: BlowWeaponOut | None
    # 맞은 부위(룰북의 장비의 칸)와 그 이름. 굴리지 않았으면 None 이다
    location: str | None
    location_name: str | None
    # 그 부위를 노렸는가. 노렸으면 노려 치기의 대가가 목표값이나 불리함에 들었다
    aimed: bool
    defense: int
    mode: str | None
    # 관통 굴림. 무기에 관통력이 없거나 그 부위에 방어가 없어 굴리지 않았으면 None 이다
    pierce: PierceOut | None = None
    # 세이브 굴림. 세이브 방식이 아니거나, 빗나갔거나, 막을 값이 없어 굴리지 않았으면 None 이다.
    # 막았으면 아무것도 바뀌지 않았다
    save: SaveOut | None = None


class HindranceOut(BaseModel):
    """입은 부상이 판정에 준 것. 보정을 깎았거나 불리하게 했다. 엔진이 정했다."""

    # 영향을 준 부상들의 이름표
    injuries: list[str]
    # 보정에서 깎은 양. 판정의 modifier 는 이미 깎인 값이다
    penalty: int
    # 불리했는가. 불리하면 주사위를 두 번 굴려 낮은 눈을 썼다
    disadvantage: bool
    # 굴린 눈들. 불리하면 둘이다. 판정의 roll 은 그중 쓴 것이다
    rolls: list[int]


class DamageNatureOut(BaseModel):
    """
    피해의 성질(#886 ③)과 맞은 쪽이 받은 단계. 엔진이 정했다.

    level 이 resist 면 방어구가 깎은 뒤의 양의 반(내림), immune 이면 0, vulnerable 이면 두 배를 받았다(amount 에
    이미 들었다). None 이면 그대로 받았다.
    """

    # 성질의 이름표(rules.natures 의 key)와 이름
    key: str
    name: str
    level: ResistLevel | None = None


class EffectOut(BaseModel):
    """판정의 결과로 HP 가 바뀐 것. 엔진이 정한 것이다."""

    # damage(피해) 또는 recovery(회복)
    kind: ChangeKind
    # 양의 등급. 규칙의 Magnitude.key 다
    magnitude: str
    # HP 가 바뀐 사람과 그 캐릭터. 대가는 행동한 사람, 회복과 동료의 타격(#803)은 행동의 대상이다
    user_id: uuid.UUID
    character_name: str
    # 주사위의 눈들과 그 합
    rolls: list[int]
    amount: int
    # 바뀌기 전과 뒤의 HP. 차이가 amount 보다 작을 수 있다. 0 이나 최대에 닿으면 거기서 멈춘다
    before: int
    after: int
    max_hp: int
    # 바뀐 뒤에 쓰러져 있는가(HP 0)
    downed: bool
    # 이 피해로 부상 표를 굴렸으면 그 결과. 굴리지 않았으면 None 이다
    injury_roll: InjuryRollOut | None = None
    # 동료의 장난(#803)이었으면 참이다. HP 가 1 아래로 내려가지 않았고, 짧은 부상만 입었다
    prank: bool = False
    # 피해의 성질(#886 ③). 성질이 없는 피해와 회복이면 None 이다
    nature: DamageNatureOut | None = None


class NpcEffectOut(BaseModel):
    """
    판정의 결과로 NPC 의 상태가 바뀐 것. 엔진이 정한 것이다.

    HP 의 숫자(바뀌기 전과 뒤, 최대)는 싣지 않는다. GM 만 안다. 주사위의 눈과 양, 바뀐 생사는 보인다.
    """

    # damage(피해) 또는 recovery(회복)
    kind: ChangeKind
    # 양의 등급. 규칙의 Magnitude.key 다
    magnitude: str
    # 바뀐 NPC. 이번 장면의 인물 목록의 id 와, 장면에서 부르는 이름
    entry_id: uuid.UUID
    name: str
    # 주사위의 눈들과 그 합
    rolls: list[int]
    amount: int
    # 죽이려는 타격이었는가
    lethal: bool
    # 바뀐 뒤의 생사
    status: NpcStatus
    # 이 피해로 부상 표를 굴렸으면 그 결과. 굴리지 않았으면 None 이다
    injury_roll: InjuryRollOut | None = None
    # 피해의 성질(#886 ③). 성질이 없는 피해와 회복이면 None 이다
    nature: DamageNatureOut | None = None


class MonsterEffectOut(BaseModel):
    """
    판정의 결과로 몬스터 한 마리의 상태가 바뀐 것. 엔진이 정한 것이다. 피해뿐이다.

    NPC 와 같이 HP 의 숫자는 싣지 않는다. 주사위의 눈과 양, 바뀐 생사는 보인다.
    """

    # 늘 damage(피해)다. 몬스터에게는 회복이 없다
    kind: ChangeKind
    magnitude: str
    # 바뀐 마리. 장면의 몬스터 목록의 id 와, 부르는 이름(수로 쥐 2)
    monster_id: uuid.UUID
    name: str
    rolls: list[int]
    amount: int
    lethal: bool
    # 바뀐 뒤의 생사. 언데드와 구조물은 HP 가 0 이면 제압이어도 죽음(부서짐)이다
    status: NpcStatus
    # 이 피해로 부상 표를 굴렸거나 노려 친 것이 맞았으면 그 결과(#799). 없었으면 None 이다
    injury_roll: InjuryRollOut | None = None
    # 피해의 성질(#886 ③). 성질이 없는 피해와 회복이면 None 이다
    nature: DamageNatureOut | None = None


class DroppedItemOut(BaseModel):
    """드롭으로 나온 물건 하나. 받은 개수, 한 가지의 상한을 넘어 잃은 개수, 받은 뒤의 개수다."""

    entry_id: uuid.UUID
    name: str
    count: int
    lost: int
    # 받은 사람이 없어 사라졌으면 None 이다
    total: int | None


class DropOut(BaseModel):
    """
    몬스터나 NPC 를 처음 쓰러뜨려 나온 물건들. 엔진이 굴리고 엔진이 줬다(app/rounds/drops.py).

    source 가 monster 면 monster_id 와 monster_name 이, npc 면 npc_id(인물 항목의 id)와 npc_name(장면의 호칭)이 있다.
    받는 사람은 그 장소(몬스터는 그 마리가 있던 곳, NPC 는 친 사람이 선 곳)의 죽지 않은 캐릭터 중
    서버의 주사위로 고른 한 명이다. 받을 사람이 없었으면 user_id 가 None 이고 나온 것은 모두 사라졌다(lost).
    """

    source: str
    monster_id: uuid.UUID | None = None
    monster_name: str | None = None
    npc_id: uuid.UUID | None = None
    npc_name: str | None = None
    user_id: uuid.UUID | None
    character_name: str | None
    items: list[DroppedItemOut]


class AttitudeChangeOut(BaseModel):
    """엔진이 바꾼 NPC 의 태도. 앞의 태도, 바뀐 태도, 까닭(caught_stealing 훔치다 들킴)."""

    previous: NpcAttitude
    attitude: NpcAttitude
    reason: str


class WakeOut(BaseModel):
    """
    쓰러진 동안 빼앗겼던 NPC 가 깨어날 때의 반응. 엔진이 굴렸다(app/rounds/wakes.py).

    roll 은 백면체의 눈, reaction 은 그 눈이 정한 반응(hostile 적대, wary 경계, None 눈치채지 못함)이다.
    attitude_change 는 실제로 바뀐 태도다. 이미 그만큼 날 서 있었으면 None 이다.
    """

    entry_id: uuid.UUID
    name: str
    roll: int
    reaction: NpcAttitude | None
    attitude_change: AttitudeChangeOut | None


class MishapOut(BaseModel):
    """치료에 실패해 치료 실패 표를 굴린 것. 엔진이 굴렸다."""

    roll: int
    # nothing(아무 일 없음), pain(좀 아픔), worsen(덧남), fatal(즉사)
    kind: str
    # 덧나서 늦춰진 게임 안의 시간(분). 덧남이 아니면 None 이다
    delay_minutes: int | None = None
    # 피해의 등급. 피해가 없으면 None 이다. 피해는 effect 나 npc_effect 에 있다
    magnitude: str | None


class PatientOut(BaseModel):
    """치료받은 쪽. 캐릭터면 user_id 와 character_name, NPC 면 entry_id 와 장면의 호칭(name)이 채워진다."""

    user_id: uuid.UUID | None = None
    character_name: str | None = None
    entry_id: uuid.UUID | None = None
    name: str | None = None


class AidOut(BaseModel):
    """
    행동의 판정에 붙여 쓴 물건(#277, #802, 거들기). 판정의 보정(modifier)에 bonus 가 이미 들었다.

    치료, 따기, 부수기, 고치기, 넘기에 붙는다.
    """

    entry_id: uuid.UUID
    name: str
    # 거든 행동. treat, pick, repair, force, cross. 치료에 붙여 쓴 것은 예전 결과에 없다(treat)
    act: str = 'treat'
    # 판정에 더한 보정. 쓰지 못했으면 0 이다
    bonus: int
    # 썼는가(판정에 보정을 더했다). 못 했으면 거짓이다. reason 이 not_held 면 차례가 왔을 때 더 가지고 있지 않았고,
    # None 이면 판정을 굴리지 않았다(문이 이미 열렸다, 도구가 있어야 하는데 없었다)
    used: bool
    reason: str | None
    # 굴린 뒤 하나 없어졌는가. 늘 없어지는 물건(붕대)이거나, 실패해서 부러졌다. 예전 치료 결과는 썼으면 없어졌다
    lost: bool = False
    # 실패해서 부러졌는가(실패하면 부러지는 물건, 락픽)
    broken: bool = False
    # 쓴 뒤에 남은 개수
    remaining: int


class TreatmentOut(BaseModel):
    """치료의 결과. 엔진이 정한 것이다. 판정의 능력과 난이도는 규칙이 정한 치료의 것이다."""

    # 치료한 부상의 이름표와 이름
    injury: str
    name: str
    ability: str
    difficulty: str
    patient: PatientOut
    # 치료할 부상이 아직 있었는가. 없었으면(앞사람이 먼저 고쳤다) 아무 일도 없었다
    treated: bool
    # 치료 뒤에 나을 게임 안의 시각. 다 나았거나 치료하지 못했으면 None 이다
    heals_at: ClockTimeOut | None = None
    # 이 장면이 끝난 뒤(다음 라운드가 열린 뒤) 낫기까지 남은 분. 다 나았거나 치료하지 못했으면 None 이다
    minutes_left: int | None = None
    healed: bool
    # 다 나으면서 굴린 후유증 표. 후유증 표가 없는 부상이면 None 이다
    aftermath: InjuryRollOut | None
    # 실패해서 굴린 치료 실패 표. 성공했으면 None 이다
    mishap: MishapOut | None
    # 치료받던 쪽이 즉사했는가
    died: bool
    # 치료에 붙여 쓴 물건(#277). 적지 않았으면 None 이다
    aid: AidOut | None = None


class ThrownAtOut(BaseModel):
    """
    물건을 던진 쪽(#277). 몬스터면 monster_id, 인물이면 entry_id, 앉은 사람(#803)이면 user_id 가 있다.
    이름은 장면에서 부르는 것이다. 앉은 사람이면 캐릭터의 이름이다.
    """

    monster_id: uuid.UUID | None = None
    entry_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    name: str | None


class ItemThrowOut(BaseModel):
    """물건을 던진 결과(#277). 엔진이 정했다(app/rounds/throws.py). 던졌으면 판정의 결과가 함께 있다."""

    # 던진 물건(판의 로어북 물건 항목)과 그 이름
    entry_id: uuid.UUID
    name: str
    # 던졌는가. 못 했으면 reason 이 있다: not_held(가지고 있지 않았다), target_gone(겨눈 몬스터가 없었다)
    thrown: bool
    reason: str | None
    # 던지는 판정의 능력과 난이도(rules 의 key). 물건에 적힌 것이나 rules.item_check 다(#801).
    # 비웠으면 기본 난이도로 채웠다
    ability: str
    difficulty: str
    target: ThrownAtOut
    # 던진 뒤에 남은 개수
    remaining: int
    # 맞힌 대상에게서 푼 부상들과 입힌 부상들(#801, 물건의 효과). 빗나갔거나 그런 효과가 없으면 빈 목록이다
    cured: list['CuredOut'] = []
    injured: list['InjuredOut'] = []
    # 맞힌 동료의 수치를 맞춘 것들(#804, adjust)
    resources: list['ResourceShiftOut'] = []


class CheckOutcome(BaseModel):
    """판정의 결과. 엔진이 정한 것이다(app/engine/check.py 의 Check). 받는 값이 아니라 내보내는 값이다."""

    # 주사위의 눈
    roll: int
    # 능력치의 점수에서 나온 보정
    modifier: int
    # 눈에 보정을 더한 값
    total: int
    # 난이도의 목표값. total 이 이 값 이상이면 성공이다
    target: int
    success: bool
    # 입은 부상이 이 판정에 준 것. 아무 영향도 없었으면 None 이다
    hindrance: HindranceOut | None = None
    # 노려 쳤으면 그 내용. target 은 이미 오른 값이다. 노려 치지 않았으면 None 이다
    called_shot: CalledShotOut | None = None
    # 타격에 장비가 든 것(#276). 무기의 공격 보정은 modifier 에 이미 들었다. 장비가 들지 않았으면 None 이다
    blow: BlowOut | None = None
    # 이 판정으로 HP 가 바뀌었으면 그 내용. 바뀌지 않았으면 None 이다
    effect: EffectOut | None = None
    # 이 판정으로 NPC 의 상태가 바뀌었으면 그 내용. 바뀌지 않았으면 None 이다. effect 와 함께 있지 않다
    npc_effect: NpcEffectOut | None = None
    # 이 판정으로 몬스터 한 마리의 상태가 바뀌었으면 그 내용. 바뀌지 않았으면 None 이다. 위의 둘과 함께 있지 않다
    monster_effect: MonsterEffectOut | None = None
    # 이 판정으로 몬스터나 NPC 를 처음 쓰러뜨려 무엇이 나왔으면 그 드롭. 아니면 None 이다
    drop: DropOut | None = None
    # 이 판정으로 쓰러진 동안 빼앗겼던 NPC 를 일으켰으면 깨어날 때의 반응. 아니면 None 이다
    wake: WakeOut | None = None
    # 치료하는 행동이었으면 그 결과. 아니면 None 이다
    treatment: TreatmentOut | None = None
    # 물건을 던진 행동이었으면 그 물건(#277). 판정은 물건에 적힌 것이다. 아니면 None 이다
    item_throw: ItemThrowOut | None = None
    # 물건을 인물이나 몬스터에게 쓴 행동이었으면 그 물건(#800). 판정은 룰북의 것이다. 아니면 None 이다
    item_use: 'ItemUseOut | None' = None
    # 맞히는 판정을 한 기술이었으면 그 기술(#805 ②). 판정은 기술이나 룰북의 것이다. 아니면 None 이다
    skill_use: 'SkillUseOut | None' = None


class NamingOut(BaseModel):
    """지목의 결과. 엔진이 정한 것이다(app/rounds/naming.py). 주사위를 굴리지 않았다."""

    # 짚은 이름
    guess: str
    correct: bool
    # 겨눈 인물이나 맞힌 인물의 id. 겨누지 않고 틀렸으면 None 이다
    entry_id: uuid.UUID | None
    # 맞힌 인물의 진짜 이름. 틀렸으면 None 이다
    name: str | None
    # 이번 장면에서 그 인물을 부르던 이름. 겨눴거나 맞힌 인물이 장면에 나왔을 때만 있다
    label: str | None
    # 이 지목으로 진짜 이름이 처음 드러났는가. 같은 라운드에 앞사람이 먼저 맞혔으면 False 다
    newly: bool


class NamingOutcome(BaseModel):
    """지목하는 행동의 결과. 판정의 결과(CheckOutcome)와 달리 굴림이 없다."""

    naming: NamingOut


class ItemPersonOut(BaseModel):
    """물건을 받거나 회복받은 사람. 떠난 사람이면 캐릭터 이름이 없다."""

    user_id: uuid.UUID
    character_name: str | None


class CuredOut(BaseModel):
    """소모품이 푼 부상 하나(#277). 룰북의 부상의 이름표와 이름이다. 나으면서 생긴 후유증은 이벤트에 있다."""

    injury: str
    name: str


class InjuredOut(BaseModel):
    """
    소모품이 입힌 부상 하나(#800). 룰북의 부상의 이름표다.

    이미 입고 있었으면 injury 가 None 이다. 몬스터가 그 성질에 면역이면 injury 는 None, immune 이 그 부상이다.
    동료의 장난(#803)이라 입히지 않은 오래 가는 부상이나 결손이면 injury 는 None, spared 가 그 부상이다.
    """

    injury: str | None
    immune: str | None = None
    spared: str | None = None
    # 짧은 부상이면 이 라운드가 닫힐 때 풀린다. 오래 가는 것이면 나을 시각이 있다
    ends_after_round: int | None = None
    heals_at: ClockTimeOut | None = None


class ItemUseOut(BaseModel):
    """
    물건을 쓴 결과. 엔진이 정했다(app/rounds/item_actions.py, item_targets.py).

    자기와 동료에게는 굴리지 않는다. 인물과 몬스터에게 썼으면(#800) 맞히는 판정의 능력과 난이도가 있고,
    판정의 결과(CheckOutcome)에 이 문서가 붙는다.
    """

    # 쓴 물건(판의 로어북 물건 항목)과 그 이름
    entry_id: uuid.UUID
    name: str
    # 썼는가. 못 했으면 reason 이 있다: not_held(가지고 있지 않았다), target_gone(받을 사람이 떠났거나 죽었다,
    # 겨눈 몬스터가 죽었거나 다른 곳에 있다. 해로운 물건을 쓸 동료가 쓰러졌거나 다른 곳에 있다),
    # friendly_fire_off(해로운 물건을 쓸 동료가 받아들이지 않게 바뀌었다, #803)
    used: bool
    reason: str | None
    # 받은 쪽. 앉은 사람이면 user_id, 인물이면 entry_id, 몬스터면 monster_id 가 있다. 누구에게도 들지 않으면 None
    target: ItemPersonOut | ThrownAtOut | None
    # 쓴 뒤에 남은 개수
    remaining: int
    # 대상에게서 푼 부상들(#277). 부상을 푸는 물건이 아니거나, 대상이 그 부상을 입고 있지 않았으면 빈 목록이다
    cured: list[CuredOut] = []
    # 대상의 수치를 맞춘 것들(#804, adjust). 적힌 차례다. 앉은 사람에게 썼을 때만 있다(인물과 몬스터에게는 수치가 없다)
    resources: list['ResourceShiftOut'] = []
    # 대상에게 입힌 부상들(#800). 적힌 차례다. 빗나갔거나 부상을 입히는 물건이 아니면 빈 목록이다
    injured: list[InjuredOut] = []
    # 인물이나 몬스터에게 썼으면 맞히는 판정의 능력과 난이도(rules.item_check 의 key)다. 아니면 None 이다
    ability: str | None = None
    difficulty: str | None = None


class ItemUseOutcome(BaseModel):
    """물건을 쓰는 행동의 결과. 회복했으면 HP 의 변화(effect)가 함께 있다."""

    item_use: ItemUseOut
    effect: EffectOut | None = None
    # 겨눈 몬스터가 없어 쓰지 못했으면 그 까닭(#800)
    target_gone: 'TargetGoneOut | None' = None


class SkillUseOut(BaseModel):
    """
    기술을 쓴 결과(#805). 엔진이 정했다(app/rounds/skill_actions.py).

    상대(인물, 몬스터)에게 쓰거나 판정이 있는 기술을 자기 아닌 동료에게 쓰면 맞히는 판정을 한다(#805 ②). 그때는 판정의
    결과(CheckOutcome)의 skill_use 로 오고, 맞혔을 때만 효과(cured, injured, resources)가 있다.
    비용은 빗나가도 낸다. 쓰지 못했으면 내지 않는다.
    """

    # 쓴 기술(룰북의 rules.skills 의 key)과 그 이름
    skill: str
    name: str
    # 썼는가. 못 했으면 reason 이 있다: not_known(그 기술을 모른다), cost_short(비용이 모자랐다),
    # target_gone(받을 사람이 떠났거나 죽었다. 해로운 기술을 쓸 동료가 쓰러졌거나 다른 곳에 있다.
    # 겨눈 몬스터가 죽었거나 다른 곳에 있다),
    # friendly_fire_off(해로운 기술을 쓸 동료가 받아들이지 않게 바뀌었다, #803)
    used: bool
    reason: str | None
    # 받은 쪽. 굴리지 않았으면 앉은 사람이다(자기 자신도). 굴렸으면 맞을 쪽이다(인물, 몬스터, 동료)
    target: ItemPersonOut | ThrownAtOut | None
    # 굴렸으면 판정의 능력과 난이도. 굴리지 않는 기술이면 None 이다
    ability: str | None = None
    difficulty: str | None = None
    # 낸 비용. 쓴 사람의 수치가 바뀐 것이다. 비용이 없는 기술이거나 쓰지 못했으면 빈 목록이다
    cost: list['ResourceShiftOut'] = []
    # 대상에게서 푼 부상들, 입힌 부상들, 맞춘 수치들. 물건과 같다
    cured: list[CuredOut] = []
    injured: list[InjuredOut] = []
    resources: list['ResourceShiftOut'] = []


class SkillUseOutcome(BaseModel):
    """
    기술을 쓰는 행동의 결과(#805). 회복하거나 다쳤으면 HP 의 변화(effect)가 함께 있다. 굴림이 없다.

    굴리는 기술을 쓰지 못했으면 여기로 온다. 겨눈 몬스터가 없어 못 썼으면 그 까닭(target_gone)도 있다(#805 ②).
    """

    skill_use: SkillUseOut
    effect: EffectOut | None = None
    target_gone: 'TargetGoneOut | None' = None


class ItemGiveOut(BaseModel):
    """물건을 건넨 결과. 엔진이 정했다(app/rounds/item_actions.py)."""

    entry_id: uuid.UUID
    name: str
    count: int
    # 건넸는가. 못 했으면 reason 이 있다:
    # not_held, target_gone(받을 사람이 떠났거나 죽었다), too_many(더 가질 수 없었다)
    given: bool
    reason: str | None
    target: ItemPersonOut
    # 건넨 뒤에 준 사람에게 남은 개수와 받은 사람의 개수. 받은 사람이 떠났으면 None 이다
    remaining: int
    target_total: int | None


class ItemGiveOutcome(BaseModel):
    """물건을 건네는 행동의 결과."""

    item_give: ItemGiveOut


class PlaceRefOut(BaseModel):
    """맵의 장소 하나. 판의 로어북 장소 항목과 그 이름이다. 아는 장소만 실린다."""

    entry_id: uuid.UUID
    name: str


class CarryOut(BaseModel):
    """업고 간 결과(#367). 엔진이 정했다(app/rounds/map_actions.py)."""

    # 업으려던 사람. 그 사람이 테이블을 떠났으면 이름이 None 이다
    user_id: uuid.UUID
    character_name: str | None
    # 업고 갔는가. 못 했으면 reason 이 있다: not_moved(업은 사람이 가지 못했다), standing(그사이 일어났다),
    # dead(그사이 죽었다), elsewhere(같은 곳에 없었다. 누가 먼저 업고 갔다)
    carried: bool
    reason: str | None


class CrossOut(BaseModel):
    """
    판에 적힌 판정 하나(#281). 길을 넘을 때, 자물쇠를 딸 때, 문을 부술 때다.

    판에 적힌 능력과 난이도로 엔진이 굴렸다. 굴림은 공개다.
    """

    # 무엇으로 굴렸는가. 룰북의 능력치와 난이도의 이름표다. 판에 난이도를 비웠으면 규칙의 기본 난이도다
    ability: str
    difficulty: str
    roll: int
    modifier: int
    total: int
    target: int
    success: bool
    # 입은 부상이 이 판정에 준 것. 없었으면 None 이다
    hindrance: HindranceOut | None = None


class MoveOut(BaseModel):
    """한 칸 간 결과. 엔진이 정했다(app/rounds/map_actions.py). 넘기 판정(#281)이 있는 길이 아니면 판정이 없다."""

    user_id: uuid.UUID
    character_name: str
    # 차례가 왔을 때 서 있던 곳과 가려던 곳. 서 있던 곳이 없으면(맵 밖) None 이다
    from_: PlaceRefOut | None = Field(alias='from')
    to: PlaceRefOut
    # 갔는가. 못 갔으면 reason 이 있다: not_adjacent(그사이 다른 곳으로 옮겨져 이어진 길이 없었다),
    # locked(잠겨 있었고 그 열쇠가 없었다, #281), cross_failed(길을 넘는 판정에 실패했다, #281),
    # barred(빗장이 반대쪽에 걸려 있었다, #281)
    moved: bool
    reason: str | None
    # 지나간 길에 걸린 게임 안의 시간(분). 다음 라운드가 열릴 때 적어도 그만큼 흐른다. 안 걸렸거나 못 갔으면 None 이다
    travel_minutes: int | None = None
    # 지닌 열쇠로 잠긴 문을 열었는가(#281). 연 문은 열린 채다
    unlocked: bool = False
    # 빗장 쪽에서 걸린 빗장을 풀었는가(#281). 푼 빗장은 풀린 채다
    unbarred: bool = False
    # 길을 넘는 판정(#281). 넘기 판정이 없는 길이거나 그 앞에서 막혔으면 None 이다
    cross: CrossOut | None = None
    # 넘기에 실패해서 다친 것(#281). 판에 실패의 피해를 적지 않았으면 None 이다
    effect: EffectOut | None = None
    # 쓰러진 동료를 업고 가려 했으면 그 결과. 아니면 None 이다
    carry: CarryOut | None = None
    # 넘기에 붙여 쓴 물건(#802, 밧줄). 붙이지 않았으면 None 이다
    aid: AidOut | None = None

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class MoveOutcome(BaseModel):
    """가는 행동의 결과."""

    move: MoveOut


class FoundRouteOut(BaseModel):
    """찾아낸 숨긴 길 하나. 두 끝과 양쪽으로 다니는지다."""

    from_place: PlaceRefOut
    to_place: PlaceRefOut
    two_way: bool


class FoundItemOut(BaseModel):
    """찾아서 가진 숨긴 물건 한 가지(app/rounds/place_item_actions.py). 찾은 사람이 바로 갖는다."""

    entry_id: uuid.UUID
    name: str
    # 가진 개수. 한 가지의 상한(99)에 닿으면 거기까지다
    count: int
    # 상한을 넘어 그 자리에 보이게 남은 개수
    left: int
    # 가진 뒤의 개수
    total: int


class SearchOut(BaseModel):
    """
    찾은 결과. 엔진이 정했다(app/rounds/map_actions.py, app/rounds/place_item_actions.py).

    찾은 길과 물건만 있다. 굴린 판정과 못 찾은 것은 없다. 숨긴 것이 없는 곳과, 있는데 못 찾은 곳의 결과가 같다.
    """

    # 찾은 곳
    place: PlaceRefOut | None
    found: list[FoundRouteOut]
    # 찾아서 가진 물건들. 물건을 찾기 전(#279)에 정한 결과에는 없다
    items: list[FoundItemOut] = []


class DoorOut(BaseModel):
    """길의 문을 다룬 결과(#281). 엔진이 정했다(app/rounds/door_actions.py)."""

    user_id: uuid.UUID
    character_name: str
    # 차례가 왔을 때 서 있던 곳과, 그 길의 다른 끝
    from_: PlaceRefOut | None = Field(alias='from')
    to: PlaceRefOut
    # lock(잠그기), unlock(열기), pick(따기), force(부수기), repair(고치기), replace(자물쇠 바꾸기)
    act: str
    # 잠그기와 열기가 다룬 장치. lock(자물쇠) 또는 bar(빗장). 따기, 부수기, 고치기, 바꾸기는 None 이다
    device: str | None = None
    # 해냈는가. 못 했으면 reason 이 있다: no_key(열쇠가 없었다), wrong_side(빗장의 반대쪽이었다),
    # broken(부서진 문은 잠그지도 바꾸지도 못한다), already(이미 그렇게 되어 있었다. 고치기는 부서지지 않았다),
    # no_tool(도구가 있어야 하는데 붙인 물건이 없었다, #802), failed(따기, 부수기, 고치기의 판정에 실패했다),
    # no_pick(바꿔 단 자물쇠가 따지 못하는 것이었다), locked(잠긴 자물쇠는 바꾸지 못한다),
    # no_item(달 자물쇠 물건이 없었다), used(그 자물쇠 물건은 이미 달았다)
    done: bool
    reason: str | None
    # 따기, 부수기, 고치기의 판정. 굴리지 않았으면 None 이다
    check: CrossOut | None = None
    # 따기, 부수기, 고치기에 붙여 쓴 물건(#802). 붙이지 않았으면 None 이다
    aid: AidOut | None = None

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class DoorOutcome(BaseModel):
    """문을 다루는 행동의 결과(#281)."""

    door: DoorOut


class SearchOutcome(BaseModel):
    """찾는 행동의 결과."""

    search: SearchOut


class TakeOut(BaseModel):
    """
    주운 결과. 엔진이 정했다(app/rounds/place_item_actions.py). 판정이 없다.

    count 는 부른 개수, taken 은 주운 개수다. 다 줍지 못했으면 reason 이 있다
    (gone: 남은 것이 없었다, not_enough: 남은 만큼 주웠다, full: 한 가지의 상한에 닿았다).
    """

    user_id: uuid.UUID
    character_name: str
    # 주운 곳
    place: PlaceRefOut | None
    entry_id: uuid.UUID
    name: str
    count: int
    taken: int
    # 주운 뒤의 개수
    total: int
    reason: str | None


class TakeOutcome(BaseModel):
    """줍는 행동의 결과."""

    take: TakeOut


class PutDownOut(BaseModel):
    """
    내려놓은 결과. 엔진이 정했다(app/rounds/place_item_actions.py). 판정이 없다.

    put 이 참이면 그 장소에 보이게 놓였다. 차례가 왔을 때 그만큼 가지고 있지 않았으면 놓지 않았다(reason 이 not_held).
    """

    user_id: uuid.UUID
    character_name: str
    # 놓은 곳
    place: PlaceRefOut | None
    entry_id: uuid.UUID
    name: str
    count: int
    put: bool
    reason: str | None
    # 내려놓은 뒤에 가진 개수
    remaining: int


class PutDownOutcome(BaseModel):
    """내려놓는 행동의 결과."""

    put_down: PutDownOut


class RolledOut(BaseModel):
    """굴린 판정 하나. 엔진이 정했다(app/engine/check.py 의 Check)."""

    roll: int
    modifier: int
    total: int
    # 목표값. 훔치기면 물건과 대상에 따라 오르내린 뒤의 값이다
    target: int
    success: bool


class StealOut(BaseModel):
    """
    훔친 결과. 엔진이 정했다(app/rounds/steals.py).

    대상이 몬스터면 monster_id 와 monster_name 이, NPC 면 npc_id(인물 항목의 id)와 npc_name(장면의 호칭)이 있다.
    stolen 이 참이면 훔쳤다(count 는 훔친 개수, left 는 대상에게 남은 개수, total 은 도둑이 가진 개수).
    거짓이고 check 가 있으면 들켰다. 몬스터는 이번 라운드의 차례에 도둑을 친다(fight 가 늘 참이다).
    NPC 는 적대가 되고(attitude_change, 이미 적대였으면 None), 시트가 정했으면 싸움도 붙는다(fight).
    check 가 없으면 굴리지 않았다(reason 이 gone: 앞사람이 먼저 훔쳤다). full 은 상한에 닿아 그만큼만 훔친 것이다.
    factors 는 목표값을 오르내리게 한 것들이다(equipped, rarity, dull_kind, dull, unwary, distracted).
    대상의 눈치(능력치의 보정)는 늘 보지만 대상의 숫자라 따로 적지 않는다. target 에 섞여 있다.
    """

    user_id: uuid.UUID
    character_name: str
    monster_id: uuid.UUID | None = None
    monster_name: str | None = None
    npc_id: uuid.UUID | None = None
    npc_name: str | None = None
    entry_id: uuid.UUID
    name: str
    check: RolledOut | None
    hindrance: HindranceOut | None
    factors: list[str]
    stolen: bool
    count: int
    left: int
    total: int
    reason: str | None
    # 들켜 싸움이 붙었는가. 이 칸이 생기기 전의 결과는 거짓으로 읽는다
    fight: bool = False
    # 들켜 바뀐 NPC 의 태도. 몬스터이거나, 들키지 않았거나, 이미 적대였으면 None 이다
    attitude_change: AttitudeChangeOut | None = None


class StealOutcome(BaseModel):
    """훔치는 행동의 결과."""

    steal: StealOut


class LootOut(BaseModel):
    """
    빼앗은 결과. 엔진이 정했다(app/rounds/loots.py). 판정이 없다.

    대상이 몬스터면 monster_id 와 monster_name 이, NPC 면 npc_id(인물 항목의 id)와 npc_name(장면의 호칭)이 있다.
    looted 가 참이면 가져갔다(count 는 가져간 개수, left 는 대상에게 남은 개수, total 은 도둑이 가진 개수).
    reason: gone(앞사람이 먼저 가져갔다), full(상한에 닿아 그만큼만, 또는 하나도), awake(대상이 깨어 있었다).
    """

    user_id: uuid.UUID
    character_name: str
    monster_id: uuid.UUID | None = None
    monster_name: str | None = None
    npc_id: uuid.UUID | None = None
    npc_name: str | None = None
    entry_id: uuid.UUID
    name: str
    looted: bool
    count: int
    left: int
    total: int
    reason: str | None


class LootOutcome(BaseModel):
    """빼앗는 행동의 결과."""

    loot: LootOut


class TradeOut(BaseModel):
    """
    상인과 사고판 결과(#278). 엔진이 정했다(app/rounds/trades.py). 판정이 없다.

    side 는 buy(샀다)나 sell(팔았다)이다. npc_id 는 상인의 인물 항목의 id, npc_name 은 장면의 호칭이다.
    price 는 오간(오가려던) 돈이다. 살 때는 낸 돈, 팔 때는 받은 돈이다. 다 하거나 하나도 하지 않는다.
    traded 가 거짓이면 reason 이 있다: unavailable(상인이 쓰러졌거나 죽었거나 적대했다), out_of_stock(재고가 모자랐다),
    not_enough_money(돈이 모자랐다), not_held(팔 물건이 모자랐다), full(산 물건을 더 가질 수 없었다),
    too_much_money(받을 돈을 더 가질 수 없었다).
    total 은 그 뒤에 그 물건을 가진 개수, money 는 그 뒤에 가진 돈이다.
    """

    user_id: uuid.UUID
    character_name: str
    side: str
    npc_id: uuid.UUID
    npc_name: str
    entry_id: uuid.UUID
    name: str
    count: int
    price: int
    traded: bool
    reason: str | None
    total: int
    money: int


class TradeOutcome(BaseModel):
    """사거나 파는 행동의 결과."""

    trade: TradeOut


class PayOut(BaseModel):
    """
    돈을 건넨 결과(#278). 엔진이 정했다(app/rounds/trades.py). 판정이 없다.

    paid 가 거짓이면 reason 이 있다: not_enough_money, target_gone(받을 사람이 떠났거나 죽었다),
    too_much_money(받을 사람이 더 가질 수 없었다).
    remaining 은 건넨 뒤에 가진 돈, target_total 은 받은 사람이 가진 돈이다. 받을 사람이 떠났으면 None 이다.
    """

    user_id: uuid.UUID
    character_name: str
    amount: int
    paid: bool
    reason: str | None
    target: ItemPersonOut
    remaining: int
    target_total: int | None


class PayOutcome(BaseModel):
    """돈을 건네는 행동의 결과."""

    pay: PayOut


class ResourceShiftOut(BaseModel):
    """
    수치 하나가 바뀐 것(#804). 쉬기나 물건의 맞추기가 바꿨다. 이름표와 이름, 바뀌기 전과 뒤의 값, 그 캐릭터의 최대다.
    """

    resource: str
    name: str
    before: int
    after: int
    max: int


class RestOut(BaseModel):
    """
    쉰 결과. 엔진이 정했다(app/rounds/rests.py). 판정이 없다.

    쉬는 라운드는 적어도 그 휴식의 시간만큼 이어진다. 그 라운드에 다쳤거나 쓰러졌거나 죽었으면 휴식이 깨져
    회복하지 않는다(rested 가 false, reason 이 hurt, downed, dead, ambushed(무작위 조우의 몬스터가 덮쳤다, #283)).
    """

    # short 또는 long
    length: str
    # 그 휴식에 드는 게임 안의 시간(분). 다음 라운드가 적어도 그만큼 뒤에 열렸다
    minutes: int
    rested: bool
    reason: str | None
    # 짧은 휴식의 회복을 정한 눈들. 긴 휴식(최대 HP 까지)과 깨진 휴식은 빈 목록이다
    rolls: list[int]
    before: int
    after: int
    max_hp: int
    # 그 휴식이 바꾼 수치들(#804). 바뀐 것만, 규칙의 차례다. 깨졌거나 이 칸이 생기기 전의 휴식은 빈 목록이다
    resources: list[ResourceShiftOut] = []


class RestOutcome(BaseModel):
    """쉬는 행동의 결과."""

    rest: RestOut


class WaitOut(BaseModel):
    """
    기다린 결과. 엔진이 정했다(app/rounds/waits.py). 판정이 없다.

    앉은 사람이 모두 기다렸고 아무도 맞지 않았으면 다음 라운드가 적어도 가장 짧게 부른 시간만큼 뒤에 열렸다.
    아니면 기다림이 깨져 시간이 건너뛰지 않았다(waited 가 false, reason 이 hurt 또는 not_all).
    """

    # 이 사람이 부른 게임 안의 시간(분)
    minutes: int
    waited: bool
    reason: str | None


class WaitOutcome(BaseModel):
    """기다리는 행동의 결과."""

    wait: WaitOut


class CoverOut(BaseModel):
    """
    엄폐한 결과(#276 의 커버 세이브). 엔진이 정했다(app/rounds/covers.py). 굴림이 없다.

    place 는 숨은 장소, value 는 그 장소의 커버다. 그 라운드 동안 맞힌 공격에 이 값으로 커버 세이브를 굴렸다
    (판정의 blow.save, 몬스터·인물의 차례의 blow.save 의 kind 가 cover). 0 이면 커버가 없는 곳이라 숨지 못했다.
    """

    place: PlaceRefOut | None
    value: int


class CoverOutcome(BaseModel):
    """엄폐하는 행동의 결과."""

    cover: CoverOut


class TargetGoneOut(BaseModel):
    """판정할 때 겨눈 몬스터(나 훔치려던 NPC, 해치려던 동료)를 겨눌 수 없었던 것. 엔진은 굴리지 않았다."""

    # 몬스터면 monster_id, NPC 면 npc_id, 앉은 사람(#803)이면 user_id 가 있다
    monster_id: uuid.UUID | None = None
    npc_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    # 부르는 이름. 장면에 없는 마리였거나 떠난 사람이면 None 이다
    name: str | None
    # dead(차례가 오기 전에 죽었다) 또는 elsewhere(다른 장소에 있다).
    # 동료(#803)면 left(떠났다), downed(쓰러져 있다), friendly_fire_off(받아들이지 않게 바뀌었다)도 있다
    reason: str


class TargetGoneOutcome(BaseModel):
    """몬스터를 겨눈 판정을 굴리지 못한 결과. 판정의 결과(CheckOutcome)와 달리 굴림이 없다."""

    target_gone: TargetGoneOut


class ItemThrowOutcome(BaseModel):
    """물건을 던지지 못한 결과(#277). 굴림이 없다. 겨눈 몬스터가 없어 못 던졌으면 그 까닭(target_gone)도 있다."""

    item_throw: ItemThrowOut
    target_gone: TargetGoneOut | None = None


class TurnLostOutcome(BaseModel):
    """차례가 오기 전에 캐릭터가 쓰러지거나 죽어 행동하지 못한 결과. 엔진은 굴리지 않았다."""

    # downed(앞 차례에 쓰러졌다) 또는 dead(앞 차례에 죽었다)
    turn_lost: str


class DeclarationOut(BaseModel):
    """선언 하나."""

    user_id: uuid.UUID
    character_name: str
    # 선언의 글. 선언을 받는 동안에는 자기 것만 보인다. 남의 것은 None 이다.
    # 선언을 마감하면(닫는 중부터) 모두의 것이 보인다
    content: str | None
    # 선언에 붙인 행동. 글과 같이 가린다. 행동이 없는 선언이면 보이는 사람에게도 None 이다
    action: Action | None
    # 행동의 결과. 선언을 마감할 때(닫는 중부터) 생긴다. 굴림은 공개라 모두에게 보인다.
    # 행동이 없는 선언과 아직 열려 있는 라운드의 선언은 None 이다. 지목이면 NamingOutcome,
    # 기술을 썼으면 SkillUseOutcome(#805, 굴린 기술은 CheckOutcome),
    # 물건을 쓰거나 건넸으면 ItemUseOutcome, ItemGiveOutcome, 던지지 못했으면 ItemThrowOutcome(던졌으면 CheckOutcome),
    # 맵에서 가거나 찾았으면 MoveOutcome, SearchOutcome,
    # 놓인 물건을 주웠으면 TakeOutcome, 내려놓았으면 PutDownOutcome, 훔쳤으면 StealOutcome, 빼앗았으면 LootOutcome,
    # 쉬었으면 RestOutcome, 기다렸으면 WaitOutcome, 사거나 팔았으면 TradeOutcome, 돈을 건넸으면 PayOutcome,
    # 엄폐했으면 CoverOutcome 이다.
    # 겨눈 몬스터를 칠 수 없어 굴리지 못했으면 TargetGoneOutcome,
    # 차례가 오기 전에 쓰러지거나 죽어 행동하지 못했으면 TurnLostOutcome 이다
    outcome: (
        CheckOutcome
        | NamingOutcome
        | ItemUseOutcome
        | SkillUseOutcome
        | ItemThrowOutcome
        | ItemGiveOutcome
        | MoveOutcome
        | SearchOutcome
        | DoorOutcome
        | TakeOutcome
        | PutDownOutcome
        | StealOutcome
        | LootOutcome
        | RestOutcome
        | WaitOutcome
        | TradeOutcome
        | PayOutcome
        | CoverOutcome
        | TargetGoneOutcome
        | TurnLostOutcome
        | None
    )


class DeathSaveOut(BaseModel):
    """죽음의 굴림 한 번. 엔진이 굴린 것이다(app/engine/death.py 의 DeathSaveRoll)."""

    user_id: uuid.UUID
    character_name: str
    # 주사위의 눈과 넘어야 하는 값. 눈이 이 값 이상이면 성공이다. 능력치의 보정은 없다
    roll: int
    target: int
    success: bool
    # 이 굴림까지 센 성공과 실패
    successes: int
    failures: int
    # 이 굴림 뒤의 갈림길. dying(죽어 가는 중), stable(고비를 넘김), dead(죽음)
    fate: Fate


class ArrivalOut(BaseModel):
    """이 라운드에 새로 들어온 캐릭터 하나. 캐릭터가 죽은 플레이어가 들인 새 캐릭터다."""

    user_id: uuid.UUID
    character_name: str
    # 같은 플레이어의 죽은 캐릭터의 이름
    replaces: str


class RoundPriceOut(BaseModel):
    """라운드에 알린 1인 1라운드의 값. credits 는 결제 서버가 정한 값(글자)이고 tier 가 premium 이면 골드로만 낸다."""

    credits: str
    tier: str | None


class ChargeOut(BaseModel):
    """
    라운드의 서술 값을 내는 사람 하나의 청구(app/billing/charges.py).

    status 는 청구의 상태다(pending, held, short, failed, capture_due, captured, release_due, released).
    credits 는 결제 서버가 실제로 홀드한 값이다. 아직 걸지 못했거나 결제 서버 없이 도는 서버면 null 이다.
    """

    user_id: uuid.UUID
    status: str
    credits: str | None


class RoundOut(BaseModel):
    """앉은 사람이 라운드를 볼 때의 값."""

    number: int
    # 이 라운드를 여는 장면. GM 의 서술이다
    scene: str
    # open: 선언을 받는 중. closing: 선언을 마감했고 GM 이 서술하는 중. closed: 끝났다
    status: RoundStatus
    declarations: list[DeclarationOut]
    # 이 라운드가 닫힐 때 굴린 죽음의 굴림들. 선언을 마감할 때(닫는 중부터) 생긴다. 굴린 것이 없으면 비어 있다
    death_saves: list[DeathSaveOut]
    # 이 라운드에 새로 들어온 캐릭터들. 들어온 순서다. 가리지 않는다. 누가 들어왔는지는 테이블에서도 보인다
    arrivals: list[ArrivalOut]
    # 선언을 내야 하는데 아직 내지 않은 사람들. 쓰러진 사람과 이 라운드에 새 캐릭터를 들인 사람은 들어가지 않는다.
    # 선언을 받는 중이 아니면 비어 있다
    waiting_for: list[uuid.UUID]
    created_at: datetime
    # 선언의 마감. 지나면 서버가 닫기 시작한다. 시간 제한이 없는 테이블이면 None 이다.
    # 화면은 이것과 지금 시각으로 남은 시간을 보여 준다
    deadline_at: datetime | None
    # 이 라운드의 서술 모델(이름표). 열 때 굳은 것이다. 아직 서술하지 않은 라운드는 방장이 바꾸면 함께 바뀐다.
    # 모델을 고르는 규칙 전에 연 라운드만 null 이다(서버의 기본 모델)
    narration_model: str | None
    # 이 라운드의 서술의 입력·출력 단계(#387). 모델과 함께 굳고 함께 바뀐다
    input_step: int
    output_step: int
    # 열 때(또는 모델을 바꿀 때) 알린 1인 1라운드의 값. 결제 서버의 가격 목록의 값이다. 알리지 못했으면 null.
    # 사람마다 실제로 홀드한 값은 GET .../rounds/{number}/charges 에 있다
    price: RoundPriceOut | None
    # 닫기 시작한 시각과 닫힌 시각. 아직이면 None 이다
    closing_at: datetime | None
    closed_at: datetime | None
    # 서술이 끝내 실패한 시각. 있으면 방장이 기다리지 않고 다시 맡길 수 있다. 다시 맡기면 비워진다
    narration_failed_at: datetime | None
    # 서술이 실패로 끝난 횟수. 3 번에 닿으면 서술을 그만두고 엔진의 결과로 다음 라운드를 연다(값은 받지 않는다).
    # 화면은 이것으로 "다시 맡기기 N 번 남음"을 보여 준다
    narration_failures: int


class CarriedOut(BaseModel):
    """몬스터 한 마리나 NPC 하나가 지금 지닌 물건 한 가지(app/tables/carried.py). 무엇을 몇 개, 장비인지 소지품인지."""

    entry_id: uuid.UUID
    name: str
    # 물건의 등급(노말, 레어, 유니크, 에픽, 레전드). 높을수록 훔치기 어렵다
    rarity: ItemRarity
    count: int
    # 몸에 걸치거나 쥔 장비인가. 아니면 품에 넣은 소지품이다
    equipped: bool
    # 물건의 값(#278). 상인의 소지품이고 값이 있으면 이 값에 산다. 비어 있으면 사고팔 수 없다
    price: int | None = None


class PersonOut(BaseModel):
    """
    이번 장면의 인물 하나. 행동으로 겨눌 수 있는 NPC 다(죽은 인물은 겨누지 못한다).

    자리가 있는 인물(place_id)은 같은 장소에 선 캐릭터만 겨눈다(#282). 자리가 없는 인물은 누구나 겨눈다.
    """

    # 행동의 npc 칸에 적는 값. 판의 로어북 인물 항목의 id 다
    id: uuid.UUID
    # 장면에서 부르는 이름. 장면에 나온 낱말이다. 지목으로 진짜 이름이 드러났으면 진짜 이름이다
    name: str
    # 지목으로 진짜 이름이 드러났는가. 드러난 인물은 다시 지목하지 못한다
    named: bool
    # 살아 있음, 쓰러짐, 죽음. HP 의 숫자는 싣지 않는다
    status: NpcStatus
    # 입고 있는 부상들의 이름표. 생긴 순서다. 이름과 사실은 테이블의 rules.injuries 에 있다
    injuries: list[str]
    # 일행을 대하는 태도(friendly 우호, neutral 중립, hostile 적대). 엔진이 정한다
    attitude: NpcAttitude
    # 지금 지닌 물건. 판의 NPC 시트에 적은 것에서 떨어뜨리거나 빼앗긴 것을 뺀 것이다. 장비 다음 소지품의 차례다
    items: list[CarriedOut] = []
    # 상인인가(#278). 상인은 소지품 중 값이 있는 것을 팔고(buy), 값이 있는 물건을 사 준다(sell).
    # 살아 있고 적대하지 않을 때만 거래한다
    merchant: bool = False
    # 있는 장소(#282). 판의 로어북 장소 항목의 id 다. 자기가 선 장소와 같아야 겨눈다.
    # null 이면 자리가 없는 인물이다. 장면의 글에 나와 장면에 들었고, 누구나 겨눈다
    place_id: uuid.UUID | None = None
    # 인물의 수치(#804). 규칙이 NPC 에게 준 것 중 모두가 보는 것만이다. 규칙의 차례다
    resources: list[ResourceOut] = []


class SceneMonsterOut(BaseModel):
    """
    이번 장면의 몬스터 한 마리. 자기가 선 장소의 죽지 않은 마리를 행동으로 칠 수 있다.

    능력치와 HP 의 숫자는 싣지 않는다. 몸 상태를 말로만 싣는다.
    """

    # 행동의 monster 칸에 적는 값. 테이블의 몬스터 한 마리의 id 다
    id: uuid.UUID
    # 부르는 이름. 같은 몬스터가 테이블에 둘 이상이면 번호가 붙는다(수로 쥐 2)
    name: str
    # 있는 장소. 판의 로어북 장소 항목의 id 다. 자기가 선 장소와 같아야 칠 수 있다
    place_id: uuid.UUID
    # 살아 있음, 쓰러짐, 죽음
    status: NpcStatus
    # 멀쩡함, 다침, 크게 다침, 쓰러짐(의식 없음), 죽음
    condition: str
    # 입고 있는 부상들(#799). 규칙의 Injury.key 다. 생긴 순서다. 이름과 효과는 테이블의 rules.injuries 에 있다
    injuries: list[str] = []
    # 지금 지닌 물건들. 장비 다음 소지품의 차례다. 떨어뜨리거나 빼앗긴 것은 없다.
    # 쓰러뜨리면 판에 적은 확률로 떨어진다. 떨어지지 않은 것은 그 마리가 그대로 지닌다
    items: list[CarriedOut] = []
    # 그 마리의 수치(#804). 규칙이 몬스터에게 준 것 중 모두가 보는 것만이다. 규칙의 차례다
    resources: list[ResourceOut] = []


class SceneCastOut(BaseModel):
    """
    가장 최근 라운드의 장면에 나온 인물들과 몬스터들. 인물은 판의 인물 순서, 몬스터는 판의 몬스터 순서와 번호 순서다.

    인물은 자리가 있으면 살아 있는 캐릭터가 서 있는 장소들의 인물, 없으면 장면에 이름이나 호칭이 나온 인물이다(#282).
    로어북의 내용은 싣지 않는다. 몬스터는 살아 있는 캐릭터가 서 있는 장소들의 마리다. 도감의 글은 싣지 않는다.
    """

    # 어느 라운드의 장면인가
    round: int
    people: list[PersonOut]
    monsters: list[SceneMonsterOut] = []


class RoundPage(BaseModel):
    """라운드 목록의 한 쪽."""

    items: list[RoundOut]
    # 전체 개수. 다음 쪽이 있는지 알 수 있다
    total: int = Field(ge=0)
