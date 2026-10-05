# game-server/app/rounds/narrator.py

"""
GM 의 서술을 만드는 것(서술자)의 모양과, AI 가 붙기 전에 쓰는 가짜 서술자.

라운드가 닫히면 서술자가 선언들을 받아 결과를 글로 쓴다. 그 글이 다음 라운드의 장면이 된다.

서술자는 글만 쓴다. 테이블의 상태를 바꾸지 않고, 선언이 성공했는지를 정하지 않는다.
엔진이 먼저 결과를 정하고(app/engine), 서술자는 정해진 결과(Verdict)를 받아 글로 옮긴다.

모양(Narrator)과 구현을 나눈다. 라운드의 코드는 모양만 안다.
나중에 AI 를 붙일 때 구현만 바꿔 끼운다. 테스트는 가짜를 쓴다. 가짜는 같은 입력에 늘 같은 글을 낸다.
"""

from dataclasses import dataclass
from typing import Protocol


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


@dataclass(frozen=True)
class Move:
    """한 캐릭터가 이번 라운드에 하겠다고 한 일과, 판정이 있었으면 그 결과."""

    character_name: str
    # 선언의 글. 선언을 내지 않았으면 None 이다. 아무것도 하지 않은 것으로 본다
    content: str | None
    # 판정의 결과. 판정이 없는 선언이면 None 이다
    verdict: Verdict | None = None


@dataclass(frozen=True)
class NarrationRequest:
    """서술자에게 주는 것. 방금 닫힌 라운드의 내용이다."""

    # 닫힌 라운드의 번호
    round_number: int
    # 그 라운드를 열었던 장면
    scene: str
    # 앉은 사람 모두가 한 일. 들어온 순서다
    moves: list[Move]


class Narrator(Protocol):
    """서술자의 모양. 이 메서드가 있으면 서술자다."""

    async def narrate(self, request: NarrationRequest) -> str:
        """닫힌 라운드의 결과를 서술한다. 돌려준 글이 다음 라운드의 장면이 된다."""
        ...


def describe_verdict(verdict: Verdict) -> str:
    """판정의 결과를 한 줄로 적는다. 예: (근력 판정 성공: 13 + 2 = 15, 목표 15)"""
    result = '성공' if verdict.success else '실패'
    # 보정이 음수면 "13 - 1" 로 적는다
    sign = '-' if verdict.modifier < 0 else '+'
    sum_ = f'{verdict.roll} {sign} {abs(verdict.modifier)} = {verdict.total}'
    return f'({verdict.ability} 판정 {result}: {sum_}, 목표 {verdict.target})'


def describe_move(move: Move) -> str:
    """한 캐릭터가 한 일을 한 줄로 적는다. 판정이 있었으면 뒤에 붙인다."""
    line = f'{move.character_name}: {move.content or "아무것도 하지 않았다."}'
    if move.verdict is None:
        return line
    return f'{line} {describe_verdict(move.verdict)}'


class FakeNarrator:
    """
    가짜 서술자. AI 를 부르지 않고 선언과 판정의 결과를 그대로 늘어놓는다.

    AI 가 붙기 전에 라운드의 흐름을 돌려 보는 데 쓴다. 자동 테스트도 이것을 쓴다.
    """

    async def narrate(self, request: NarrationRequest) -> str:
        """한 일을 한 줄씩 늘어놓은 글을 돌려준다."""
        lines = [f'[{request.round_number} 라운드의 결과]']
        lines.extend(describe_move(move) for move in request.moves)
        return '\n'.join(lines)
