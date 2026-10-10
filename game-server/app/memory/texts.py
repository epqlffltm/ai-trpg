# game-server/app/memory/texts.py

"""
지난 라운드로 기억을 만든다. DB 도 모델도 모르는 순수한 함수들이다.

기억 하나는 라운드 하나다. 라운드 N 의 기억 = 라운드 N 에 플레이어들이 한 말 + 그 결과를 서술한 글(라운드 N+1 의 장면).
한 일과 그 결과를 한 덩어리로 둬야 "차단기를 부순다"와 "차단기가 박살 났다"가 함께 찾아진다.
다음 라운드가 아직 없는 라운드(결과를 서술하는 중이거나 마지막 라운드)는 기억이 되지 않는다.

판정의 결과(주사위)는 싣지 않는다. 결과의 서술에 이미 녹아 있다(지난 기록의 PastRound 와 같다).
라운드를 여는 첫 장면(시나리오의 도입부)은 어느 기억에도 들지 않는다. 제작자의 글이고 지난 일이 아니다.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.rounds.narrator import PastRound

# 아무도 선언하지 않은 라운드의 한 말 자리. 지난 기록(app/rounds/prompt.py)과 같은 말이다
NOBODY_DECLARED = '(아무도 선언하지 않았다)'
# 문장의 끝. 마침표·느낌표·물음표·말줄임표 뒤에 빈칸이 오거나 글이 끝나는 곳, 그리고 줄바꿈
SENTENCE_END = re.compile(r'[.!?…](?=\s|$)|\n')
# 잘랐다는 표시
CLIPPED = '…'


@dataclass(frozen=True)
class Memory:
    """지난 라운드 하나의 기억. lines 는 "캐릭터 이름: 한 말" 한 줄씩, result 는 그 결과를 서술한 글이다."""

    number: int
    lines: tuple[str, ...]
    result: str


def memories_of(rounds: Sequence[PastRound]) -> list[Memory]:
    """
    라운드들로 기억을 만든다. 다음 라운드가 있는 라운드만 기억이 된다. 라운드 번호 순이다.

    rounds 는 한 테이블의 라운드들이다. 차례가 섞여 있어도 된다.
    """
    by_number = {past.number: past for past in rounds}
    return [
        Memory(past.number, tuple(past.lines), by_number[past.number + 1].scene)
        for past in sorted(rounds, key=lambda past: past.number)
        if past.number + 1 in by_number
    ]


def memory_text(memory: Memory) -> str:
    """기억의 글. 한 말을 한 줄씩, 그다음 "결과: " 뒤에 서술. 벡터로 바꿀 때와 프롬프트에 넣을 때 함께 쓴다."""
    said = list(memory.lines) or [NOBODY_DECLARED]
    return '\n'.join([*said, f'결과: {memory.result}'])


def clip(text: str, limit: int) -> str:
    """
    limit 자를 넘으면 그 안의 마지막 문장 끝에서 자르고 말줄임표를 붙인다. 넘지 않으면 그대로다.

    문장 중간에서 자른 글은 모델이 이어 쓰려 한다. 문장 끝이 하나도 없으면 limit 에 맞춰 자른다.
    돌려주는 글은 말줄임표까지 limit 자를 넘지 않는다.
    """
    if len(text) <= limit:
        return text
    head = text[: limit - len(CLIPPED)]
    ends = [match.end() for match in SENTENCE_END.finditer(head)]
    cut = ends[-1] if ends else len(head)
    return head[:cut].rstrip() + CLIPPED


def missing_memories(memories: list[Memory], done: set[int]) -> list[Memory]:
    """아직 벡터가 없는 기억들. done 은 이미 벡터가 있는 라운드의 번호다."""
    return [memory for memory in memories if memory.number not in done]
