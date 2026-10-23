# trpg-server/app/rounds/narrator.py

"""
GM 의 서술을 만드는 것(서술자)의 모양과, 서술자에게 주는 것(NarrationRequest)의 모양.

라운드가 닫히면 서술자가 선언들을 받아 결과를 글로 쓴다. 그 글이 다음 라운드의 장면이 된다.

서술자는 글만 쓴다. 테이블의 상태를 바꾸지 않고, 선언이 성공했는지를 정하지 않는다.
엔진이 먼저 결과를 정하고(app/engine), 서술자는 정해진 결과(Verdict)를 받아 글로 옮긴다.

모양(Narrator)과 구현을 나눈다. 라운드의 코드는 모양만 안다.
구현은 따로 있다. 언어 모델로 쓰는 것(app/rounds/llm_narrator.py)과, AI 를 부르지 않는 가짜
(app/rounds/fake_narrator.py).
각자 한 일을 한 줄로 적는 법은 app/rounds/move_lines.py 에 있다. 가짜 서술자와 프롬프트가 함께 쓴다.

서술은 수십 초가 걸린다. 쓰는 동안의 글을 미리 보기(Preview)로 흘려보낼 수 있다.
미리 보기는 버려질 수 있는 글이다. 시도가 실패하면 다음 시도가 처음부터 다시 쓴다. 남는 장면은 서술자가 돌려준 글뿐이다.
"""

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from app.assets.models import LoreKind, NarrationStyle
from app.calendar.clock import ClockTime
from app.catalog.steps import BASE_STEPS, NarrationSteps
from app.engine.ruleset import NarrationGuide


@dataclass(frozen=True)
class InjuryNote:
    """
    입은 부상 하나. 규칙에 적힌 이름과, 서술자가 지켜야 할 사실이다(예: "오른손이 없다. 오른손을 쓸 수 없다.").

    엔진이 정한 것이다. 서술자는 이 부상으로 못 하는 일을 하게 쓰지 않는다.
    """

    name: str
    fact: str


@dataclass(frozen=True)
class Impact:
    """판정의 결과로 HP 가 바뀐 것. 엔진이 정한 것이다."""

    # damage(피해) 또는 recovery(회복)
    kind: str
    # HP 가 바뀐 캐릭터. 피해는 행동한 캐릭터, 회복은 행동의 대상이다
    character_name: str
    # 주사위가 정한 양
    amount: int
    # 바뀐 뒤의 HP 와 최대 HP
    hp: int
    max_hp: int
    # 바뀐 뒤에 쓰러져 있는가
    downed: bool
    # 이 피해로 새로 입은 부상의 이름. 없으면 None 이다
    injury: str | None = None


@dataclass(frozen=True)
class NpcImpact:
    """
    판정의 결과로 NPC 의 HP 가 바뀐 것. 엔진이 정한 것이다.

    HP 의 숫자는 주지 않는다. 몸 상태를 말로 준다(app/rounds/cast.py 의 condition_of).
    숫자를 주면 모델이 "HP 3 남은" 같은 것을 장면에 쓴다. 플레이어에게도 NPC 의 HP 는 보이지 않는다.
    """

    # damage(피해) 또는 recovery(회복)
    kind: str
    # 장면에서 부르는 이름
    name: str
    # 주사위가 정한 양
    amount: int
    # 바뀐 뒤의 몸 상태. 멀쩡함, 다침, 크게 다침, 쓰러짐(의식 없음), 죽음
    condition: str
    # 이 피해로 새로 입은 부상의 이름. 없으면 None 이다
    injury: str | None = None


@dataclass(frozen=True)
class DroppedNote:
    """드롭으로 나온 물건 하나. 이름과 받은 개수, 더 들 수 없어 잃은 개수다."""

    name: str
    count: int
    lost: int = 0


@dataclass(frozen=True)
class WakeNote:
    """
    쓰러진 동안 빼앗겼던 NPC 가 깨어나 그것을 알아챈 것(app/rounds/wakes.py). 엔진이 굴리고 정한 것이다.

    attitude 는 바뀐 태도의 말(경계, 적대)이다. 눈치채지 못했거나 태도가 바뀌지 않았으면 서술자에게 주지 않는다.
    """

    name: str
    attitude: str


@dataclass(frozen=True)
class DropNote:
    """
    몬스터나 NPC 를 쓰러뜨려 얻은 물건. 엔진이 굴리고 엔진이 줬다. 서술자는 이것을 사실로 받아 쓰기만 한다.

    holder 는 지녔던 몬스터나 NPC 의 장면의 호칭, receiver 는 받은 캐릭터의 이름이다.
    받을 사람이 없어 사라진 드롭은 서술자에게 주지 않는다.
    """

    holder: str
    receiver: str
    items: list[DroppedNote]


@dataclass(frozen=True)
class TreatmentNote:
    """
    치료의 결과. 엔진이 정한 것이다. 서술자는 이것을 바꾸지 못하고 글로 옮기기만 한다.

    부상과 치료받는 쪽은 규칙의 이름과 장면의 호칭이다. 숫자는 남은 시간만 준다(HP 는 Impact 에 있다).
    """

    # 치료한 부상의 이름과 치료받은 쪽
    injury: str
    patient: str
    # 치료할 부상이 아직 있었는가. 앞사람이 먼저 고쳤거나 그사이에 나았으면 False 다. 그러면 아무 일도 없었다
    treated: bool = True
    # 치료로 다 나았는가
    healed: bool = False
    # 이 장면이 끝난 뒤 낫기까지 남은 게임 안의 분. 다 나았거나 치료하지 못했으면 None 이다
    minutes_left: int | None = None
    # 나으면서 남은 후유증의 이름. 없으면 None 이다
    aftermath: str | None = None
    # 실패했을 때 치료 실패 표에서 나온 일. nothing, pain, worsen, fatal. 성공했거나 치료하지 못했으면 None 이다
    mishap: str | None = None
    # 덧나서 늦춰진 게임 안의 분. 덧나지 않았으면 None 이다
    worsened_minutes: int | None = None
    # 치료받던 쪽이 죽었는가(즉사)
    died: bool = False


@dataclass(frozen=True)
class HealNote:
    """이번 라운드에 시간이 지나 나은 오래 가는 부상 하나. 나으면서 남은 후유증이 있으면 그 이름이다."""

    name: str
    aftermath: str | None = None


@dataclass(frozen=True)
class BlowNote:
    """
    타격에 장비가 든 것(#276). 엔진이 정했다. 무기와 그 공격 보정, 맞은 부위의 이름, 노렸는가, 그 부위의 방어다.

    mode 는 규칙의 방어 방식이다. ac 면 방어가 맞히는 목표값에 더해졌고, reduce 면 맞은 피해에서 빠졌고,
    save 면 맞은 뒤 세이브로 막으려 했다. 방어 방식이 없는 규칙이면 None 이고 부위도 방어도 없다.
    pierced 는 관통 굴림의 결과다. 굴리지 않았으면 None 이다. 관통했으면 방어구가 막지 않았다.
    save_kind 는 굴린 세이브(armor 아머, ward 불굴)이고 saved 는 막았는가다. 굴리지 않았으면 둘 다 None 이다.
    """

    weapon: str | None = None
    weapon_bonus: int = 0
    location: str | None = None
    aimed: bool = False
    defense: int = 0
    mode: str | None = None
    pierced: bool | None = None
    save_kind: str | None = None
    save_value: int = 0
    saved: bool | None = None


@dataclass(frozen=True)
class Verdict:
    """
    판정의 결과. 엔진이 정한 것이다. 서술자는 이것을 바꾸지 못하고 글로 옮기기만 한다.

    능력과 난이도는 규칙에 적힌 이름이다("근력", "어려움"). 글을 쓰는 쪽이 읽는 것이라 key 가 아니다.
    """

    ability: str
    difficulty: str
    # 주사위의 눈, 능력치의 보정, 둘을 더한 값, 넘어야 하는 값
    roll: int
    modifier: int
    total: int
    target: int
    success: bool
    # 이 판정으로 HP 가 바뀌었으면 그 내용. 없으면 None 이다
    impact: Impact | None = None
    # 이 판정으로 NPC 의 HP 가 바뀌었으면 그 내용. 없으면 None 이다. impact 와 함께 있지 않다
    npc_impact: NpcImpact | None = None
    # 이 판정으로 몬스터 한 마리의 HP 가 바뀌었으면 그 내용. NPC 와 같은 모양이다(숫자 없이 몸 상태).
    # 없으면 None 이다. 이 칸이 생기기 전에 굳힌 것도 None 이다
    monster_impact: NpcImpact | None = None
    # 이 판정으로 몬스터를 처음 쓰러뜨려 얻은 물건. 없으면 None 이다. 이 칸이 생기기 전에 굳힌 것도 None 이다
    drop: DropNote | None = None
    # 이 판정으로 쓰러진 동안 빼앗겼던 인물을 일으켰고 그 인물이 그것을 알아챘으면 그 반응. 아니면 None 이다
    wake: WakeNote | None = None
    # 이 판정에 영향을 준 부상들의 이름(보정이 깎였거나 불리했다). 없으면 비어 있다
    hindrances: list[str] = field(default_factory=list)
    # 노려 쳤으면 노린 부상의 이름. 판정이 그만큼 어려웠다. 성공했으면 그 부상이 생겼다(impact 에 적힌다)
    aimed: str | None = None
    # 치료하는 행동이면 그 결과. 판정의 능력과 난이도는 규칙이 정한 치료의 것이다. 치료가 아니면 None 이다
    treatment: TreatmentNote | None = None
    # 타격에 장비가 든 것(#276). 무기도 방어 방식도 없었거나 이 칸이 생기기 전에 굳힌 것은 None 이다
    blow: BlowNote | None = None


@dataclass(frozen=True)
class NamingNote:
    """
    지목의 결과. 엔진이 정한 것이다. 주사위를 굴리지 않았다.

    맞았으면 진짜 이름(name)이 있다. 틀렸으면 None 이다. 틀린 결과로 정답을 흘리지 않는다.
    label 은 이번 장면에서 그 인물을 부르던 이름이다. 겨눴거나, 맞힌 인물이 장면에 나왔을 때만 있다.
    """

    guess: str
    correct: bool
    name: str | None = None
    label: str | None = None


@dataclass(frozen=True)
class DeathSaveNote:
    """죽음의 굴림 한 번. 엔진이 굴린 것이다. 쓰러진 캐릭터가 죽어 가는지, 고비를 넘겼는지, 죽었는지를 알려 준다."""

    # 주사위의 눈과 넘어야 하는 값
    roll: int
    target: int
    success: bool
    # 지금까지 센 성공과 실패
    successes: int
    failures: int
    # dying(죽어 가는 중), stable(고비를 넘김), dead(죽음)
    fate: str


@dataclass(frozen=True)
class ItemNote:
    """캐릭터가 가진 물건 한 가지. 판의 로어북 물건 항목의 이름과 개수다."""

    name: str
    count: int


@dataclass(frozen=True)
class ItemActionNote:
    """
    물건을 쓰거나 건넨 결과. 엔진이 정한 것이다. 판정이 없다.

    kind 는 use(쓰기)나 give(건네기)다. done 이 거짓이면 하지 못했다. 까닭은 reason 이다
    (not_held 가지고 있지 않았다, target_gone 받을 사람이 없었다, too_many 받는 쪽이 더 가질 수 없었다).
    target 은 회복받거나 받은 사람의 캐릭터 이름이다. 자기 자신에게 썼거나 대상이 없는 물건이면 None 이다.
    """

    kind: str
    name: str
    count: int
    done: bool
    reason: str | None = None
    target: str | None = None
    # 회복하는 소모품을 썼으면 HP 의 변화
    impact: Impact | None = None


@dataclass(frozen=True)
class PlaceNote:
    """
    캐릭터가 서 있는 맵의 장소. 이 라운드의 행동까지 반영한 뒤의 것이다(app/tables/places.py).

    exits 는 아는 길로 한 칸에 갈 수 있는 장소들의 이름이다. 판의 길 순서다.
    hidden 은 그 장소에 닿은, 아직 찾지 않은 숨긴 길의 다른 끝의 이름이다. GM 만 안다. 플레이어도 방장도 모른다.
    hidden 은 언어 모델의 맵 절(app/rounds/prompt.py)에만 싣는다. 한 일의 줄(describe_move)에는 싣지 않는다.
    가짜 서술자는 그 줄을 장면으로 내보내므로, 거기 실으면 숨긴 길이 모두에게 새어 나간다.
    items 는 그 장소에 보이게 놓인 물건들(이름과 개수), hidden_items 는 아직 찾지 않은
    숨긴 물건의 이름이다. hidden_items 도 GM 만 안다. hidden 과 같이 맵 절에만 싣는다(#279).
    """

    name: str
    exits: list[str] = field(default_factory=list)
    hidden: list[str] = field(default_factory=list)
    items: list[ItemNote] = field(default_factory=list)
    hidden_items: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TravelNote:
    """
    맵에서 한 칸 간 결과(app/rounds/map_actions.py). 엔진이 정한 것이다. 판정이 없다.

    moved 가 거짓이면 가지 못했다. 까닭은 reason 이다(not_adjacent: 차례가 왔을 때 이어진 길이 없었다).
    from_place 는 차례가 왔을 때 서 있던 곳이다. 맵 밖에 있었으면 None 이다.
    travel_minutes 는 지나간 길에 걸린 게임 안의 시간(분)이다. 안 걸렸으면 None 이다.
    carried 는 업고 가려던 쓰러진 동료의 이름이다(#367). 업지 않았으면 None 이다.
    carry_reason 은 업고 가지 못한 까닭이다(standing, dead, elsewhere, not_moved). 업고 갔으면 None 이다.
    """

    from_place: str | None
    to_place: str
    moved: bool
    reason: str | None = None
    travel_minutes: int | None = None
    carried: str | None = None
    carry_reason: str | None = None


@dataclass(frozen=True)
class WaitNote:
    """
    기다리는 행동의 결과(app/rounds/waits.py). 엔진이 정한 것이다. 판정이 없다.

    minutes 는 이 사람이 부른 시간이다. waited 가 거짓이면 시간이 건너뛰지 않았다.
    까닭은 reason 이다(hurt: 그 라운드에 누가 맞았다, not_all: 모두가 기다리지 않았다).
    실제로 흐르는 시간은 [시각]의 흐르는 시간이다(모두 부른 것 중 가장 짧은 것, 적어도 판의 기본).
    """

    minutes: int
    waited: bool
    reason: str | None = None


@dataclass(frozen=True)
class RestNote:
    """
    쉬는 행동의 결과(app/rounds/rests.py). 엔진이 정한 것이다. 판정이 없다.

    length 는 short(짧은 휴식) 또는 long(긴 휴식)이다. rested 가 거짓이면 휴식이 깨져 회복하지 않았다.
    까닭은 reason 이다(hurt: 그 라운드에 맞았다, downed: 쓰러졌다, dead: 죽었다). HP 는 쉬기 전과 뒤다.
    """

    length: str
    rested: bool
    reason: str | None = None
    before: int = 0
    after: int = 0
    max_hp: int = 0


@dataclass(frozen=True)
class RevivalNote:
    """
    고비를 넘기고 쓰러져 있던 캐릭터가 오래 쉬어 굴린 되살아나기(app/rounds/rests.py). 엔진이 정한 것이다.

    success 가 참이면 HP 1 로 정신이 돌아왔다. 거짓이면 아직 의식이 없다(고비는 넘긴 채다).
    """

    success: bool
    hp: int


@dataclass(frozen=True)
class RecoveryNote:
    """시간이 흘러 저절로 회복한 것(app/rounds/rests.py). 규칙이 켰을 때만 있다. HP 는 회복 전과 뒤다."""

    before: int
    after: int
    max_hp: int


@dataclass(frozen=True)
class SearchNote:
    """
    숨긴 길과 숨긴 물건을 찾은 결과(app/rounds/map_actions.py, app/rounds/place_item_actions.py).

    found 는 찾은 길이 이어지는 장소들의 이름, items 는 찾아서 가진 물건들(이름과 가진 개수)이다.
    못 찾았으면 비어 있다.
    숨긴 것이 없는 곳과, 있는데 못 찾은 곳의 결과가 같다. 굴린 판정은 적혀 있지 않다.
    """

    place: str | None
    found: list[str] = field(default_factory=list)
    items: list[ItemNote] = field(default_factory=list)


@dataclass(frozen=True)
class TakeNote:
    """
    장소에 놓인 물건을 주운 결과(app/rounds/place_item_actions.py). 엔진이 정한 것이다. 판정이 없다.

    taken 은 주운 개수다. 0 이면 줍지 못했다. reason 은 부른 것보다 적게 주운 까닭이다
    (gone: 남은 것이 없었다, not_enough: 남은 만큼만, full: 더 가질 수 없다). 다 주웠으면 None 이다.
    """

    name: str
    count: int
    taken: int
    reason: str | None = None


@dataclass(frozen=True)
class PutDownNote:
    """
    가진 물건을 서 있는 장소에 내려놓은 결과(app/rounds/place_item_actions.py). 엔진이 정한 것이다. 판정이 없다.

    put 이 참이면 그 자리에 보이게 놓였다. 거짓이면 차례가 왔을 때 그만큼 가지고 있지 않아 놓지 못했다.
    """

    name: str
    count: int
    put: bool


@dataclass(frozen=True)
class StealNote:
    """
    몬스터나 NPC 가 지닌 물건을 훔친 결과(app/rounds/steals.py). 엔진이 정한 것이다.

    victim 은 대상의 장면의 호칭, npc 는 대상이 NPC 인지다.
    stolen 이 참이면 훔쳤다(count 개). 거짓이고 caught 가 참이면 들켰다. 몬스터는 도둑을 노린다.
    NPC 는 적대한다(hostile 은 이번에 적대로 바뀌었는지). fight 면 싸움이 붙었다.
    stolen 과 caught 가 둘 다 거짓이면 차례가 왔을 때 그 물건이 이미 없었다(앞사람이 먼저 훔쳤다).
    """

    victim: str
    name: str
    count: int
    stolen: bool
    caught: bool
    npc: bool = False
    hostile: bool = False
    fight: bool = False


@dataclass(frozen=True)
class LootNote:
    """
    쓰러졌거나 죽은 대상에게서 물건을 빼앗은 결과(app/rounds/loots.py). 엔진이 정한 것이다. 판정이 없다.

    victim 은 대상의 장면의 호칭이다. looted 가 참이면 count 개를 가져갔다.
    reason 은 다 가져가지 못한 까닭이다(gone: 이미 없었다, full: 더 들 수 없다, awake: 대상이 깨어 있었다).
    """

    victim: str
    name: str
    count: int
    looted: bool
    reason: str | None = None


@dataclass(frozen=True)
class WornNote:
    """착용한 물건 하나(#276). 이름과 차지한 칸의 이름들(주손, 보조손)이다."""

    name: str
    slots: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TradeNote:
    """
    상인과 사고판 결과(app/rounds/trades.py, #278). 엔진이 정한 것이다. 판정이 없다.

    side 는 buy(샀다)나 sell(팔았다)이다. merchant 는 상인의 장면의 호칭, price 는 오간 돈의 글(금화 20닢)이다.
    traded 가 거짓이면 하지 못했다. 까닭은 reason 이다(app/rounds/trades.py 의 Reason).
    """

    side: str
    merchant: str
    name: str
    count: int
    price: str
    traded: bool
    reason: str | None = None


@dataclass(frozen=True)
class PayNote:
    """
    돈을 건넨 결과(app/rounds/trades.py, #278). 엔진이 정한 것이다.

    amount 는 건넨(건네려던) 돈의 글(금화 10닢), target 은 받는 사람의 캐릭터 이름이다(떠났으면 None).
    paid 가 거짓이면 하지 못했다. 까닭은 reason 이다.
    """

    amount: str
    target: str | None
    paid: bool
    reason: str | None = None


@dataclass(frozen=True)
class HandOverNote:
    """
    이룬 퀘스트가 이 캐릭터에게서 가져간 물건 한 가지(app/rounds/quest_handover.py). 엔진이 정한 것이다.

    quest 는 퀘스트(사건)의 이름, name 은 물건의 이름, count 는 낸 개수다. 배달을 마친 것이다.
    """

    quest: str
    name: str
    count: int


@dataclass(frozen=True)
class TargetGoneNote:
    """
    겨눈 몬스터를 판정할 때 칠 수 없어 굴리지 않은 것(app/rounds/checks.py 의 target_gone).

    name 은 부르는 이름이다. 장면에 없는 마리였으면 None 이다.
    reason 은 dead(차례가 오기 전에 죽었다) 또는 elsewhere(다른 장소에 있다)다.
    """

    name: str | None
    reason: str


@dataclass(frozen=True)
class Move:
    """한 캐릭터가 이번 라운드에 하겠다고 한 일과, 판정이 있었으면 그 결과."""

    character_name: str
    # 선언의 글. 선언을 내지 않았으면 None 이다. 아무것도 하지 않은 것으로 본다
    content: str | None
    # 판정의 결과. 판정이 없는 선언이면 None 이다
    verdict: Verdict | None = None
    # 이 라운드의 결과까지 반영한 뒤에 이 캐릭터가 쓰러져 있는가
    downed: bool = False
    # 이 라운드가 닫힐 때 굴린 죽음의 굴림. 굴리지 않았으면 None 이다
    death_save: DeathSaveNote | None = None
    # 이 캐릭터가 죽었는가. 이번 라운드에 죽었을 수도, 그 전에 죽었을 수도 있다
    dead: bool = False
    # 선언을 냈지만 차례가 오기 전에 쓰러지거나 죽어 하지 못했으면 그 까닭(downed, dead). 아니면 None 이다
    # (app/rounds/judging.py 의 lost_turn). 이 칸이 생기기 전에 굳힌 것은 None 이다
    lost_turn: str | None = None
    # 이 캐릭터가 이번 라운드에 새로 들어왔으면, 같은 플레이어의 죽은 캐릭터의 이름. 아니면 None 이다.
    # 새로 들어온 캐릭터는 이번 라운드에 아무것도 하지 않았다. 다음 라운드부터 행동한다
    replaces: str | None = None
    # 이 라운드의 결과까지 반영한 뒤에 이 캐릭터가 입고 있는 부상들. 생긴 순서다.
    # 목록으로 둔다. 라운드에 굳힐 때 JSON 으로 적고 다시 읽어도 같은 값이어야 한다
    injuries: list[InjuryNote] = field(default_factory=list)
    # 이 라운드가 닫힐 때 시간이 지나 나은 오래 가는 부상들. 치료로 나은 것은 verdict 의 treatment 에 있다
    healed: list[HealNote] = field(default_factory=list)
    # 지목하는 행동이면 그 결과. 지목은 판정이 아니라 verdict 와 함께 있지 않다
    naming: NamingNote | None = None
    # 물건을 쓰거나 건네는 행동이면 그 결과. 판정이 아니라 verdict 와 함께 있지 않다
    item_action: ItemActionNote | None = None
    # 이 라운드의 행동까지 반영한 뒤에 이 캐릭터가 가진 물건들. 판의 물건 순서다.
    # 서술자는 없는 물건을 쓰는 장면을 쓰지 않는다. 소지품을 바꾸는 것은 서버뿐이다
    items: list[ItemNote] = field(default_factory=list)
    # 맵에서 가는 행동이면 그 결과, 찾는 행동이면 그 결과. 판정이 아니라 verdict 와 함께 있지 않다
    travel: TravelNote | None = None
    search: SearchNote | None = None
    # 놓인 물건을 줍는 행동이면 그 결과. 판정이 아니라 verdict 와 함께 있지 않다
    take: TakeNote | None = None
    # 가진 물건을 내려놓는 행동이면 그 결과. 판정이 아니라 verdict 와 함께 있지 않다
    put_down: PutDownNote | None = None
    # 몬스터나 NPC 가 지닌 물건을 훔치는 행동이면 그 결과. verdict 와 함께 있지 않다(판정은 엔진이 따로 굴렸다)
    steal: StealNote | None = None
    # 쓰러졌거나 죽은 대상에게서 빼앗는 행동이면 그 결과. 판정이 아니라 verdict 와 함께 있지 않다
    loot: LootNote | None = None
    # 상인과 사고판 행동이면 그 결과, 돈을 건넨 행동이면 그 결과(#278). 판정이 아니라 verdict 와 함께 있지 않다
    trade: TradeNote | None = None
    pay: PayNote | None = None
    # 이 라운드의 행동까지 반영한 뒤에 이 캐릭터가 가진 돈의 글(금화 30닢). 돈이 없는 판이면 None 이다(#278).
    # 서술자는 돈을 주거나 받는 장면을 지어내지 않는다. 돈을 바꾸는 것은 서버뿐이다
    money: str | None = None
    # 이 라운드의 행동까지 반영한 뒤에 이 캐릭터가 착용한 물건들(#276). 규칙의 칸의 차례다.
    # 착용은 서버가 관리한다. 서술자는 착용하지 않은 갑옷이나 쥐지 않은 무기를 그리지 않는다
    worn: list[WornNote] = field(default_factory=list)
    # 이 라운드가 닫힐 때 이룬 퀘스트가 이 캐릭터에게서 가져간 물건들. 퀘스트마다, 물건마다 한 줄이다
    handed_over: list[HandOverNote] = field(default_factory=list)
    # 겨눈 몬스터를 칠 수 없어 굴리지 않았으면 그 까닭. 아니면 None 이다. verdict 와 함께 있지 않다
    target_gone: TargetGoneNote | None = None
    # 쉬는 행동이면 그 결과. 판정이 아니라 verdict 와 함께 있지 않다
    rest: RestNote | None = None
    # 기다리는 행동이면 그 결과. 판정이 아니라 verdict 와 함께 있지 않다. 이 칸이 생기기 전에 굳힌 것은 None 이다
    wait: WaitNote | None = None
    # 이 라운드가 닫힐 때 굴린 되살아나기와 저절로 회복. 없었으면 None 이다(app/rounds/rests.py)
    revival: RevivalNote | None = None
    recovery: RecoveryNote | None = None
    # 이 라운드의 행동까지 반영한 뒤에 이 캐릭터가 서 있는 맵의 장소. 맵이 없는 테이블이면 None 이다.
    # 위치를 바꾸는 것은 서버뿐이다. 서술자는 다른 곳으로 옮기지 않는다
    place: PlaceNote | None = None


@dataclass(frozen=True)
class StoryContext:
    """
    이 테이블의 이야기의 바탕. 판의 복사본에서 꺼낸다. 라운드마다 같다.

    GM 이 읽는 글이 들어 있다(진행 지침, GM 메모). 서술자에게만 준다. 플레이어에게 내보내지 않는다.
    """

    title: str
    # 이용 등급(all, adult). 서술의 수위를 정한다
    rating: str
    # 룰북의 진행 지침. AI 가 GM 으로서 따를 글이다
    guide: str
    # 세계관의 설정과 GM 메모. 세계관이 없는 시나리오면 빈 글이다
    setting: str = ''
    gm_notes: str = ''
    # 규칙의 서술 지침(#616). 분위기, 판정 결과 단계마다의 묘사, 하지 말 것. 없으면 공통의 지시만으로 서술한다
    narration: NarrationGuide | None = None


@dataclass(frozen=True)
class PastRound:
    """
    지난 라운드 하나. 그때의 장면과 플레이어들이 한 말이다.

    lines 는 "캐릭터 이름: 선언의 글" 한 줄씩이다. 그 라운드를 닫을 때 서술자가 받은 사람들의 것이다
    (app/rounds/narration_request.py 의 to_past).
    successes 는 줄마다 판정이 성공했는가다. lines 와 같은 차례다. 판정이 없던 줄은 None 이다.
    비어 있으면 판정을 모르는 것이다(평가 도구의 데이터처럼 글만 있는 라운드).
    지난 기록(대화)에는 lines 만 쓴다. 판정의 결과는 그다음 장면의 서술에 이미 녹아 있다.
    검색한 지난 일은 서술을 잘라 넣으므로 성공과 실패를 줄에 붙인다(app/memory/texts.py).
    """

    number: int
    scene: str
    lines: list[str] = field(default_factory=list)
    successes: list[bool | None] = field(default_factory=list)


@dataclass(frozen=True)
class LoreNote:
    """
    서술에 참고로 넣는 로어북 항목 하나. 검색이 골랐다(app/lore/retrieval.py).

    AI 가 읽는 글이다. 플레이어에게 내보내지 않는다. entry_id 는 판의 복사본 안의 id 로, 무엇을 넣었는지 기록할 때 쓴다.
    kind 는 항목의 종류다. 종류마다 프롬프트가 다르게 다룬다(app/rounds/prompt.py).
    """

    entry_id: uuid.UUID
    name: str
    content: str
    kind: LoreKind = LoreKind.OTHER


@dataclass(frozen=True)
class ReferenceNote:
    """
    서술에 참고로 넣는 바깥 자료 한 줄(#482). 검색이 골랐다(app/references/retrieval.py).

    AI 가 읽는 글이다. 플레이어에게 내보내지 않는다. 글에는 수치가 없다(app/references/srd.py).
    reference_id 는 참고 자료의 줄(reference_entries)의 id 로, 무엇을 넣었는지 기록할 때 쓴다.
    kind 는 종류(monster, item)다. 프롬프트가 앞에 붙여 보인다.
    """

    reference_id: uuid.UUID
    name: str
    content: str
    kind: str


@dataclass(frozen=True)
class MemoryNote:
    """
    서술에 넣는 지난 일 하나. 검색이 골랐다(app/memory/retrieval.py).

    지난 기록(history)보다 앞의 라운드 하나다. 그 라운드에 플레이어들이 한 말과, 그 결과를 서술한 글이다.
    플레이어가 이미 본 글이다. round_number 는 무엇을 넣었는지 기록할 때 쓴다.
    """

    round_number: int
    text: str


@dataclass(frozen=True)
class HistoryLine:
    """인물의 이력 한 줄. 지난 서술에서 그 인물이 나온 문장 하나와, 그 서술이 열었던 라운드의 번호."""

    round_number: int
    text: str


@dataclass(frozen=True)
class PersonHistory:
    """
    이번 장면에 나온 인물 하나의 이력. 지난 기록보다 앞의 서술에서 그 인물이 나온 문장들이다(app/memory/history.py).

    AI 를 부르지 않고 문장을 골라냈다. 플레이어가 이미 본 글이다. 라운드 순서대로라 바뀐 태도가 보인다.
    name 은 로어북 검색이 정한 이름표다(장면의 호칭). entry_id 는 판의 복사본 안의 인물 항목이다.
    """

    entry_id: uuid.UUID
    name: str
    lines: list[HistoryLine]


@dataclass(frozen=True)
class PersonState:
    """
    이번 장면에 나온 인물(NPC) 하나의 지금 상태. 엔진과 DB 가 가진 것이다(table_npcs).

    이번 라운드의 판정까지 반영한 뒤의 것이다. name 은 장면에서 부르는 이름, condition 은 몸 상태를 말로 적은 것이다.
    """

    name: str
    condition: str
    # 입고 있는 부상들. 생긴 순서다
    injuries: list[InjuryNote] = field(default_factory=list)
    # 일행을 대하는 태도의 말(우호, 적대). 중립이면 None 이다(app/tables/npc_attitudes.py)
    attitude: str | None = None


@dataclass(frozen=True)
class WhisperNote:
    """
    플레이어끼리 몰래 주고받은 쪽지 하나. 보낸 쪽이 GM 에게도 보여 주기로 한 것만 온다(app/whispers/).

    이름은 보낼 때의 캐릭터 이름이다. 캐릭터를 정하기 전에 보냈으면 None 이다.
    다른 플레이어는 이 쪽지를 모른다. 서술자는 장면에서 내용을 드러내지 않고, 인물의 속내를 이해하는 데만 쓴다.
    """

    sender: str | None
    recipient: str | None
    content: str


@dataclass(frozen=True)
class HappeningNote:
    """
    이번 라운드가 닫힐 때 일어난 판의 사건 하나(app/rounds/happenings.py, #367). 엔진이 정한 것이다.

    name 은 사건 항목의 이름, moved 는 옮겨진 사람마다 "이름 → 장소"다. 사건의 글은 로어북 검색이 따로 준다.
    """

    name: str
    moved: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class QuestNote:
    """
    테이블의 퀘스트 하나와 그 지금 상태. 상태는 정해진 사실이다. 드러내기, 성공, 실패는 엔진이 판의 조건을 보고
    (app/rounds/quest_goals.py), 기한의 실패는 기한을 넘겨 서버가(app/rounds/deadlines.py) 정했다.

    status 는 hidden, active, succeeded, failed 다. 숨긴(hidden) 것은 플레이어가 아직 모르는 일이다.
    서술자는 숨긴 것을 드러내지 않고, 진행 중인 것의 결말을 먼저 정하지 않는다.

    기한(#268). 숫자를 주지 않는다. 숫자를 주면 모델이 그것을 장면에 쓴다.
    pace 는 진행 중이고 기한이 있는 것의 남은 시간의 감각이다(ample 넉넉함, tight 빠듯함, last 다 됨). 아니면 None.
    missed_deadline 은 이번 라운드에 기한을 넘겨 실패했는가다. 숨긴 것에는 기한이 없다(드러날 때부터 센다).
    """

    name: str
    status: str
    pace: str | None = None
    missed_deadline: bool = False


@dataclass(frozen=True)
class MonsterNote:
    """
    이번 장면의 몬스터. 네임드 몹은 한 마리, 일반 몹은 같은 장소의 같은 종류를 한데 모은다.

    엔진이 정한 사실이다. 숫자(HP, 능력치)는 주지 않는다. 몸 상태를 말로 준다(app/rounds/cast.py 의 condition_of).
    content 는 도감의 글이다. 제작자가 약점을 적었을 수 있어서 이 절에만 넣고, 한 일의 줄에는 싣지 않는다.
    """

    # 부르는 이름. 네임드 몹은 그 이름이고, 일반 몹은 종류의 이름이다(번호 없이)
    name: str
    # 타입의 이름(인간형, 야수 …). 기타면 빈 글이다
    kind: str
    content: str
    # 있는 장소의 이름. 맵의 장소다
    place: str
    unique: bool
    # 마리마다의 몸 상태. 번호 순서다. 네임드 몹은 하나다
    conditions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DownedStrikeNote:
    """
    쓰러진 캐릭터를 친 결과(#369). 엔진이 정한 것이다. 피해 대신 죽음의 굴림 실패가 쌓인다.

    added 는 이번에 쌓인 실패(빗나가면 0), failures 는 그 뒤의 실패, limit 는 죽는 수, fate 는 그 뒤의 갈림길이다.
    """

    added: int
    failures: int
    limit: int
    fate: str


@dataclass(frozen=True)
class MonsterTurnNote:
    """
    몬스터 한 마리의 차례에 한 일. 엔진이 정한 것이다(app/rounds/monster_attacks.py).
    싸우는 인물(NPC)의 차례도 이 모양이다(app/rounds/npc_attacks.py, #487). 이름은 장면에서 부르는 이름이다.

    굴림의 숫자는 주지 않는다. 몬스터의 능력치를 드러낸다. 맞았으면 그 캐릭터의 HP 변화(impact)를 준다.
    움직이지 못한 차례(쓰러짐, 죽음, 부상으로 못 움직임, 칠 캐릭터가 없음)는 넣지 않는다. 한 일이 없다.
    """

    # 부르는 이름(수로 쥐 2)
    name: str
    # 공격의 이름과, 친 캐릭터
    attack: str
    target: str
    hit: bool
    impact: Impact | None = None
    # 쓰러진 캐릭터를 쳤으면 그 결과(#369). 서 있는 캐릭터를 쳤으면 None 이다
    downed: DownedStrikeNote | None = None
    # 공격에 장비가 든 것(#276). 무기도 방어 방식도 없었거나 이 칸이 생기기 전에 굳힌 것은 None 이다
    blow: BlowNote | None = None


@dataclass(frozen=True)
class TurnNote:
    """
    차례 하나. 캐릭터의 차례면 character_name, 몬스터의 차례면 monster, 인물의 차례면 npc 가 있다.

    이 순서대로 한 일의 줄을 놓는다(app/rounds/move_lines.py 의 round_lines).
    """

    character_name: str | None = None
    monster: MonsterTurnNote | None = None
    npc: MonsterTurnNote | None = None


@dataclass(frozen=True)
class ClockNote:
    """
    게임 안의 시각. 엔진이 정한 사실이다(app/calendar/).

    now 는 이 라운드가 열린 때다. 서술하는 장면이 시작하는 때다.
    ends 는 서술한 장면이 끝나는 때다. 다음 라운드가 그 시각에 열린다. passes_minutes 는 그 사이에 흐르는 분이다.
    """

    now: ClockTime
    ends: ClockTime
    passes_minutes: int


@dataclass(frozen=True)
class NarrationRequest:
    """서술자에게 주는 것. 방금 닫힌 라운드의 내용이다."""

    # 닫힌 라운드의 번호
    round_number: int
    # 그 라운드를 열었던 장면
    scene: str
    # 앉은 사람 모두가 한 일. 들어온 순서다
    moves: list[Move]
    # 이야기의 바탕. 가짜 서술자는 읽지 않는다
    story: StoryContext | None = None
    # 이 라운드 앞의 라운드들. 오래된 것부터다. 가짜 서술자는 읽지 않는다
    history: list[PastRound] = field(default_factory=list)
    # 서술의 문체. 라운드가 닫기 시작할 때의 테이블의 문체다. 가짜 서술자는 읽지 않는다
    style: NarrationStyle = NarrationStyle.NONE
    # 서술 모델(모델 목록의 이름표). 라운드를 열 때 굳힌 것이다.
    # 있으면 그 모델로만 서술한다(app/rounds/picked_narrator.py). 없으면 서버의 기본 모델이다(옛 라운드).
    # 언어 모델의 서술자 하나하나는 읽지 않는다. 가짜 서술자도 읽지 않는다
    model: str | None = None
    # 어느 테이블의 라운드인가, 서술을 맡길 때 방장이 누구인가. AI 호출을 기록할 때 쓴다(ai_core/calls.py).
    # 가짜 서술자는 읽지 않는다
    table_id: uuid.UUID | None = None
    host_id: uuid.UUID | None = None
    # 이번 장면에 맞는 로어북 항목. 서술을 맡기기 직전에 검색이 채운다. 가짜 서술자는 읽지 않는다
    lore: list[LoreNote] = field(default_factory=list)
    # 이번 장면에 맞는 참고 자료(SRD 같은 바깥 자료). 테이블이 켰을 때만, 로어북을 고른 뒤 남은 자리에 검색이 채운다.
    # 가짜 서술자는 읽지 않는다
    references: list[ReferenceNote] = field(default_factory=list)
    # 이번 장면에 맞는 지난 일(지난 기록보다 앞의 라운드). 서술을 맡기기 직전에 검색이 채운다. 가짜 서술자는 읽지 않는다
    memories: list[MemoryNote] = field(default_factory=list)
    # 이번 장면에 나온 인물(로어북이 고른 인물 항목)의 이력. 서술을 맡기기 직전에 채운다. 가짜 서술자는 읽지 않는다
    histories: list[PersonHistory] = field(default_factory=list)
    # 이번 장면에 나온 NPC 들의 지금 상태. 라운드를 읽을 때 DB 에서 채운다. 가짜 서술자는 읽지 않는다
    people: list[PersonState] = field(default_factory=list)
    # 이 라운드에 GM 에게도 보인 쪽지. 보낸 순서다. 라운드를 읽을 때 DB 에서 채운다. 가짜 서술자는 읽지 않는다
    whispers: list[WhisperNote] = field(default_factory=list)
    # 테이블의 퀘스트들과 그 지금 상태. 판의 순서다. 서술을 맡길 때 DB 에서 채운다. 가짜 서술자는 읽지 않는다
    quests: list[QuestNote] = field(default_factory=list)
    # 이번 라운드가 닫힐 때 일어난 판의 사건들. 판의 순서다. 서술을 맡길 때 DB 에서 채운다. 가짜 서술자는 읽지 않는다
    happenings: list[HappeningNote] = field(default_factory=list)
    # 이번 장면의 몬스터들. 판의 몬스터 순서다. 서술을 맡길 때 DB 에서 채운다. 가짜 서술자는 읽지 않는다
    monsters: list[MonsterNote] = field(default_factory=list)
    # 이 라운드의 차례(라운드의 turns). 맞붙은 몬스터가 없었으면 비어 있고, 그때는 moves 의 순서다.
    # 가짜 서술자도 이 순서로 줄을 놓는다
    turns: list[TurnNote] = field(default_factory=list)
    # 게임 안의 시각. 서술을 맡길 때 테이블의 시계에서 채운다. 시계가 없으면 None. 가짜 서술자는 읽지 않는다
    clock: ClockNote | None = None
    # 아직 맞히지 않은 인물의 진짜 이름에서 장면의 호칭으로(app/rounds/secret_names.py). 프롬프트에는 싣지 않는다.
    # 언어 모델의 서술자가 받은 글과 미리 보기에서 이 이름들을 찾는다. 가짜 서술자는 읽지 않는다
    secrets: dict[str, str] = field(default_factory=dict)
    # 서술의 입력·출력 단계(#387). 라운드를 열 때 굳힌 것이다. 입력의 예산과 칸마다의 상한, 출력의 상한과
    # 장면의 길이를 정한다(app/catalog/steps.py). 가짜 서술자는 읽지 않는다
    steps: NarrationSteps = BASE_STEPS


class Preview(Protocol):
    """
    서술이 쓰이는 동안의 글을 받는 곳. 앉은 사람에게 미리 보여 주는 데 쓴다.

    시도마다 begin 으로 시작하고, 새로 쓴 글을 text 로 조각마다 받는다. 이어 붙이면 그 시도가 쓴 글이다.
    둘 다 보통 함수다. 빨리 돌아와야 하고 예외를 내면 안 된다. 서술을 기다리게 만들지 않는다.
    """

    def begin(self) -> None:
        """새 시도가 시작됐다. 앞의 시도에서 받은 글은 버려진 글이다."""
        ...

    def text(self, piece: str) -> None:
        """이번 시도가 새로 쓴 글 조각."""
        ...


class NoPreview:
    """아무것도 보여 주지 않는 미리 보기. 미리 볼 사람이 없을 때의 기본값이다."""

    def begin(self) -> None:
        return None

    def text(self, piece: str) -> None:
        return None


NO_PREVIEW = NoPreview()


class Narrator(Protocol):
    """서술자의 모양. 이 메서드가 있으면 서술자다."""

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        """
        닫힌 라운드의 결과를 서술한다. 돌려준 글이 다음 라운드의 장면이 된다.

        쓰는 동안의 글을 preview 에 흘려보낸다. 시도마다 begin 을 먼저 부른다.
        """
        ...
