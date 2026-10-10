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

    lines 는 "캐릭터 이름: 선언의 글" 한 줄씩이다. 판정의 결과는 싣지 않는다. 그다음 장면의 서술에 이미 녹아 있다.
    """

    number: int
    scene: str
    lines: list[str] = field(default_factory=list)


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
    # 어느 테이블의 라운드인가, 서술을 맡길 때 방장이 누구인가. AI 호출을 기록할 때 쓴다(app/ai/calls.py).
    # 가짜 서술자는 읽지 않는다
    table_id: uuid.UUID | None = None
    host_id: uuid.UUID | None = None
    # 이번 장면에 맞는 로어북 항목. 서술을 맡기기 직전에 검색이 채운다. 가짜 서술자는 읽지 않는다
    lore: list[LoreNote] = field(default_factory=list)
    # 이번 장면에 맞는 지난 일(지난 기록보다 앞의 라운드). 서술을 맡기기 직전에 검색이 채운다. 가짜 서술자는 읽지 않는다
    memories: list[MemoryNote] = field(default_factory=list)


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
    """판정의 결과를 한 줄로 적는다. 예: (근력 판정 성공: 13 + 2 = 15, 목표 15)"""
    result = '성공' if verdict.success else '실패'
    # 보정이 음수면 "13 - 1" 로 적는다
    sign = '-' if verdict.modifier < 0 else '+'
    sum_ = f'{verdict.roll} {sign} {abs(verdict.modifier)} = {verdict.total}'
    return f'({verdict.ability} 판정 {result}: {sum_}, 목표 {verdict.target})'


def describe_impact(impact: Impact) -> str:
    """HP 가 바뀐 것을 한 줄로 적는다. 예: → 엘프 피해 3 (HP 7/10)"""
    word = '피해' if impact.kind == 'damage' else '회복'
    state = f'HP {impact.hp}/{impact.max_hp}' + (', 쓰러짐' if impact.downed else '')
    return f'→ {impact.character_name} {word} {impact.amount} ({state})'


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


def describe_move(move: Move) -> str:
    """
    한 캐릭터가 한 일을 한 줄로 적는다. 판정이 있었으면 뒤에 붙이고, HP 가 바뀌었으면 그 뒤에 붙인다.
    죽음의 굴림을 굴렸으면 맨 뒤에 붙인다.
    """
    parts = [f'{move.character_name}: {move.content or describe_idle(move)}']
    if move.verdict is not None:
        parts.append(describe_verdict(move.verdict))
        if move.verdict.impact is not None:
            parts.append(describe_impact(move.verdict.impact))
    if move.death_save is not None:
        parts.append(describe_death_save(move.death_save))
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
