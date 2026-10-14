# game-server/app/rounds/narrator.py

"""
GM 의 서술을 만드는 것(서술자)의 모양과, AI 가 붙기 전에 쓰는 가짜 서술자.

라운드가 닫히면 서술자가 선언들을 받아 결과를 글로 쓴다. 그 글이 다음 라운드의 장면이 된다.

서술자는 글만 쓴다. 테이블의 상태를 바꾸지 않고, 선언이 성공했는지를 정하지 않는다.
엔진이 먼저 결과를 정하고(app/engine), 서술자는 정해진 결과(Verdict)를 받아 글로 옮긴다.

모양(Narrator)과 구현을 나눈다. 라운드의 코드는 모양만 안다.
나중에 AI 를 붙일 때 구현만 바꿔 끼운다. 테스트는 가짜를 쓴다. 가짜는 같은 입력에 늘 같은 글을 낸다.

서술은 수십 초가 걸린다. 쓰는 동안의 글을 미리 보기(Preview)로 흘려보낼 수 있다.
미리 보기는 버려질 수 있는 글이다. 시도가 실패하면 다음 시도가 처음부터 다시 쓴다. 남는 장면은 서술자가 돌려준 글뿐이다.
"""

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from app.assets.models import LoreKind, NarrationStyle
from app.rounds.tiers import NarrationTier


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
class TreatmentNote:
    """
    치료의 결과. 엔진이 정한 것이다. 서술자는 이것을 바꾸지 못하고 글로 옮기기만 한다.

    부상과 치료받는 쪽은 규칙의 이름과 장면의 호칭이다. 숫자는 남은 라운드만 준다(HP 는 Impact 에 있다).
    """

    # 치료한 부상의 이름과 치료받은 쪽
    injury: str
    patient: str
    # 치료할 부상이 아직 있었는가. 앞사람이 먼저 고쳤거나 그사이에 나았으면 False 다. 그러면 아무 일도 없었다
    treated: bool = True
    # 치료로 다 나았는가
    healed: bool = False
    # 낫기까지 남은 라운드. 다 나았거나 치료하지 못했으면 None 이다
    rounds_left: int | None = None
    # 나으면서 남은 후유증의 이름. 없으면 None 이다
    aftermath: str | None = None
    # 실패했을 때 치료 실패 표에서 나온 일. nothing, pain, worsen, fatal. 성공했거나 치료하지 못했으면 None 이다
    mishap: str | None = None
    # 덧나서 늘어난 라운드. 덧나지 않았으면 None 이다
    worsened_by: int | None = None
    # 치료받던 쪽이 죽었는가(즉사)
    died: bool = False


@dataclass(frozen=True)
class HealNote:
    """이번 라운드에 시간이 지나 나은 오래 가는 부상 하나. 나으면서 남은 후유증이 있으면 그 이름이다."""

    name: str
    aftermath: str | None = None


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
    # 이 판정에 영향을 준 부상들의 이름(보정이 깎였거나 불리했다). 없으면 비어 있다
    hindrances: list[str] = field(default_factory=list)
    # 노려 쳤으면 노린 부상의 이름. 판정이 그만큼 어려웠다. 성공했으면 그 부상이 생겼다(impact 에 적힌다)
    aimed: str | None = None
    # 치료하는 행동이면 그 결과. 판정의 능력과 난이도는 규칙이 정한 치료의 것이다. 치료가 아니면 None 이다
    treatment: TreatmentNote | None = None


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
class QuestNote:
    """
    테이블의 퀘스트 하나와 그 지금 상태. 상태는 방장이 정한 사실이다(app/tables/quest_changes.py).

    status 는 hidden, active, succeeded, failed 다. 숨긴(hidden) 것은 플레이어가 아직 모르는 일이다.
    서술자는 숨긴 것을 드러내지 않고, 진행 중인 것의 결말을 먼저 정하지 않는다.
    """

    name: str
    status: str


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
    # 서술 등급. 라운드를 열 때 굳힌 것이다. 등급마다 서술자가 다르다(app/rounds/tiered_narrator.py).
    # 언어 모델의 서술자 하나하나는 읽지 않는다. 가짜 서술자도 읽지 않는다
    tier: NarrationTier = NarrationTier.STANDARD
    # 어느 테이블의 라운드인가, 서술을 맡길 때 방장이 누구인가. AI 호출을 기록할 때 쓴다(app/ai/calls.py).
    # 가짜 서술자는 읽지 않는다
    table_id: uuid.UUID | None = None
    host_id: uuid.UUID | None = None
    # 이번 장면에 맞는 로어북 항목. 서술을 맡기기 직전에 검색이 채운다. 가짜 서술자는 읽지 않는다
    lore: list[LoreNote] = field(default_factory=list)
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


def describe_verdict(verdict: Verdict) -> str:
    """
    판정의 결과를 한 줄로 적는다. 예: (근력 판정 성공: 13 + 2 = 15, 목표 15)

    부상이 영향을 줬으면 그 이름을 붙인다. 예: (근력 판정 실패: 5 - 1 = 4, 목표 15. 전부터 입은 부상의 영향: 팔 골절)
    노려 쳤으면 노린 것을 붙인다. 예: (민첩 판정 성공: 18 + 2 = 20, 목표 20. 노려 치기: 한쪽 눈 잃음)
    """
    result = '성공' if verdict.success else '실패'
    # 보정이 음수면 "13 - 1" 로 적는다
    sign = '-' if verdict.modifier < 0 else '+'
    sum_ = f'{verdict.roll} {sign} {abs(verdict.modifier)} = {verdict.total}'
    hindered = f'. 전부터 입은 부상의 영향: {", ".join(verdict.hindrances)}' if verdict.hindrances else ''
    aimed = f'. 노려 치기: {verdict.aimed}' if verdict.aimed else ''
    return f'({verdict.ability} 판정 {result}: {sum_}, 목표 {verdict.target}{hindered}{aimed})'


MISHAPS = {'nothing': '별일 없음', 'pain': '덧나서 아픔', 'worsen': '상처가 덧남', 'fatal': '즉사'}


def describe_treatment(note: TreatmentNote) -> str:
    """
    치료의 결과를 한 줄로 적는다.

    예: → 토르빈의 팔 골절 치료: 앞당겨짐, 낫기까지 15 라운드
        → 토르빈의 팔 골절 치료: 다 나음. 후유증: 굽은 팔
        → 토르빈의 팔 골절 치료 실패: 상처가 덧남, 5 라운드 늦어짐, 낫기까지 25 라운드
    """
    # 치료받던 사람이 떠났으면 이름을 모른다. 부상만 적는다
    head = f'→ {note.patient}의 {note.injury} 치료' if note.patient else f'→ {note.injury} 치료'
    if not note.treated:
        return f'{head}: 치료할 부상이 이미 없었다'
    if note.mishap is None:
        if note.healed:
            return f'{head}: 다 나음' + (f'. 후유증: {note.aftermath}' if note.aftermath else '')
        return f'{head}: 앞당겨짐, 낫기까지 {note.rounds_left} 라운드'
    if note.died:
        return f'{head} 실패: {MISHAPS[note.mishap]}, {note.patient} 죽음'
    parts = [MISHAPS[note.mishap]]
    if note.worsened_by:
        parts.append(f'{note.worsened_by} 라운드 늦어짐')
    if note.rounds_left is not None:
        parts.append(f'낫기까지 {note.rounds_left} 라운드')
    return f'{head} 실패: {", ".join(parts)}'


# 이름만 맞힌 지목에 붙는 말. 플레이어가 함께 한 주장("범인은")까지 맞은 것이 아니다
UNSETTLED_CLAIMS = '이름 밖의 주장이 맞는지는 정해지지 않았다'


def describe_naming(note: NamingNote) -> str:
    """
    지목의 결과를 한 줄로 적는다.

    예: → 지목 맞음: 악역영애의 진짜 이름은 비올레타
        → 지목 맞음: 비올레타(이)라는 인물이 이 이야기에 있다. 이름 밖의 주장이 맞는지는 정해지지 않았다
        → 지목 틀림: 악역영애의 진짜 이름은 '로즈'(이)가 아니다
        → 지목 틀림: '로즈'(은)는 맞는 이름이 아니다
    """
    if note.correct:
        if note.label is None:
            return f'→ 지목 맞음: {note.name}(이)라는 인물이 이 이야기에 있다. {UNSETTLED_CLAIMS}'
        if note.label == note.name:
            return f'→ 지목 맞음: {note.name}'
        return f'→ 지목 맞음: {note.label}의 진짜 이름은 {note.name}'
    if note.label is not None:
        return f"→ 지목 틀림: {note.label}의 진짜 이름은 '{note.guess}'(이)가 아니다"
    return f"→ 지목 틀림: '{note.guess}'(은)는 맞는 이름이 아니다"


def describe_healed(healed: list[HealNote]) -> str:
    """시간이 지나 나은 부상들. 예: [나은 부상: 팔 골절(후유증: 굽은 팔), 다리 부상]"""
    names = [note.name + (f'(후유증: {note.aftermath})' if note.aftermath else '') for note in healed]
    return f'[나은 부상: {", ".join(names)}]'


def describe_impact(impact: Impact) -> str:
    """HP 가 바뀐 것을 한 줄로 적는다. 예: → 엘프 피해 3 (HP 7/10)"""
    word = '피해' if impact.kind == 'damage' else '회복'
    state = f'HP {impact.hp}/{impact.max_hp}' + (', 쓰러짐' if impact.downed else '')
    return f'→ {impact.character_name} {word} {impact.amount} ({state})' + new_injury(impact.injury)


def new_injury(name: str | None) -> str:
    """새로 입은 부상을 결과 줄 뒤에 붙일 글. 없으면 빈 글이다. 예: ". 새 부상: 팔 골절"."""
    return f'. 새 부상: {name}' if name else ''


def describe_injuries(injuries: list[InjuryNote]) -> str:
    """입고 있는 부상들을 한 덩어리로 적는다. 예: 팔 골절(한쪽 팔이 부러져 제대로 쓰지 못한다)"""
    return ', '.join(f'{injury.name}({injury.fact})' for injury in injuries)


def describe_npc_impact(impact: NpcImpact) -> str:
    """NPC 의 HP 가 바뀐 것을 한 줄로 적는다. 숫자는 양만 적는다. 예: → 악역영애 피해 5 (크게 다침)"""
    word = '피해' if impact.kind == 'damage' else '회복'
    return f'→ {impact.name} {word} {impact.amount} ({impact.condition})' + new_injury(impact.injury)


def describe_idle(move: Move) -> str:
    """
    선언을 내지 않은 캐릭터를 뭐라고 적을지 정한다.

    새로 들어온 캐릭터를 가장 먼저 본다. 이 라운드에 한 일이 없는 것은 들어온 라운드이기 때문이다.
    죽은 캐릭터는 쓰러져 있기도 하다. 죽음을 쓰러짐보다 먼저 본다.
    """
    if move.replaces is not None:
        return f'죽은 {move.replaces}의 뒤를 이어 새로 이야기에 들어온다.'
    if move.dead:
        return '죽었다.'
    return '쓰러져 있다.' if move.downed else '아무것도 하지 않았다.'


FATES = {'dying': '죽어 가는 중', 'stable': '고비를 넘김', 'dead': '죽음'}


def describe_death_save(note: DeathSaveNote) -> str:
    """죽음의 굴림을 한 줄로 적는다. 예: (죽음의 굴림 실패: 7, 목표 10. 성공 1, 실패 2, 죽어 가는 중)"""
    result = '성공' if note.success else '실패'
    counts = f'성공 {note.successes}, 실패 {note.failures}'
    return f'(죽음의 굴림 {result}: {note.roll}, 목표 {note.target}. {counts}, {FATES[note.fate]})'


# 물건을 쓰거나 건네지 못한 까닭을 서술자에게 주는 말
ITEM_FAILURES = {
    'not_held': '가지고 있지 않았다',
    'target_gone': '받을 사람이 없었다',
    'too_many': '받는 쪽이 더 가질 수 없었다',
}


def describe_item_action(note: ItemActionNote) -> str:
    """
    물건을 쓰거나 건넨 결과를 한 줄로 적는다. 회복했으면 HP 의 변화를 붙인다.

    예: (쓴 물건: 치유 물약) → 엘프 회복 3 (HP 8/10)
        (건넨 물건: 밧줄 1개 → 영애)
        (쓰려던 물건: 치유 물약. 가지고 있지 않았다)
    """
    what = note.name if note.kind == 'use' else f'{note.name} {note.count}개'
    to = f' → {note.target}' if note.target else ''
    if not note.done:
        verb = '쓰려던' if note.kind == 'use' else '건네려던'
        return f'({verb} 물건: {what}{to}. {ITEM_FAILURES.get(note.reason, "하지 못했다")})'
    verb = '쓴' if note.kind == 'use' else '건넨'
    line = f'({verb} 물건: {what}{to})'
    return f'{line} {describe_impact(note.impact)}' if note.impact else line


def describe_items(items: list[ItemNote]) -> str:
    """가진 물건들을 한 줄로 적는다. 하나뿐이면 개수를 적지 않는다. 예: 치유 물약 2개, 밧줄"""
    return ', '.join(item.name if item.count == 1 else f'{item.name} {item.count}개' for item in items)


def describe_move(move: Move) -> str:
    """
    한 캐릭터가 한 일을 한 줄로 적는다. 판정이 있었으면 뒤에 붙이고, 치료였으면 그 결과를,
    HP 가 바뀌었으면 그 뒤에 붙인다. 지목이었으면 그 결과를, 물건을 쓰거나 건넸으면 그 결과를 붙인다.
    죽음의 굴림을 굴렸으면 그 뒤에, 시간이 지나 나은 부상이 있으면 그 뒤에, 입고 있는 부상이 있으면 그 뒤에,
    가진 물건이 있으면 맨 뒤에 붙인다.
    """
    parts = [f'{move.character_name}: {move.content or describe_idle(move)}']
    # 선언을 냈지만 앞사람의 치료가 실패해 그 자리에서 죽었다. 선언한 일을 하지 못했다
    if move.content and move.dead and move.verdict is None and move.naming is None:
        parts.append('(하려던 일을 하기 전에 죽었다)')
    if move.verdict is not None:
        parts.append(describe_verdict(move.verdict))
        if move.verdict.treatment is not None:
            parts.append(describe_treatment(move.verdict.treatment))
        if move.verdict.impact is not None:
            parts.append(describe_impact(move.verdict.impact))
        if move.verdict.npc_impact is not None:
            parts.append(describe_npc_impact(move.verdict.npc_impact))
    if move.naming is not None:
        parts.append(describe_naming(move.naming))
    if move.item_action is not None:
        parts.append(describe_item_action(move.item_action))
    if move.death_save is not None:
        parts.append(describe_death_save(move.death_save))
    if move.healed:
        parts.append(describe_healed(move.healed))
    if move.injuries:
        parts.append(f'[입은 부상: {describe_injuries(move.injuries)}]')
    if move.items:
        parts.append(f'[소지품: {describe_items(move.items)}]')
    return ' '.join(parts)


class FakeNarrator:
    """
    가짜 서술자. AI 를 부르지 않고 선언과 판정의 결과를 그대로 늘어놓는다.

    AI 가 붙기 전에 라운드의 흐름을 돌려 보는 데 쓴다. 자동 테스트도 이것을 쓴다.
    """

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        """한 일을 한 줄씩 늘어놓은 글을 돌려준다. 미리 보기에는 그 글을 한 번에 보낸다."""
        lines = [f'[{request.round_number} 라운드의 결과]']
        lines.extend(describe_move(move) for move in request.moves)
        scene = '\n'.join(lines)
        preview.begin()
        preview.text(scene)
        return scene
