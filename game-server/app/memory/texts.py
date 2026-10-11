# game-server/app/memory/texts.py

"""
지난 라운드로 기억을 만든다. DB 도 모델도 모르는 순수한 함수들이다.

기억 하나는 라운드 하나다. 라운드 N 의 기억 = 라운드 N 에 플레이어들이 한 말 + 그 결과를 서술한 글(라운드 N+1 의 장면).
한 일과 그 결과를 한 덩어리로 둬야 "차단기를 부순다"와 "차단기가 박살 났다"가 함께 찾아진다.
다음 라운드가 아직 없는 라운드(결과를 서술하는 중이거나 마지막 라운드)는 기억이 되지 않는다.
라운드를 여는 첫 장면(시나리오의 도입부)은 어느 기억에도 들지 않는다. 제작자의 글이고 지난 일이 아니다.

기억의 글은 둘이다.
  - 벡터로 바꾸는 글(memory_text). 한 말 전부와 결과 전부다. 자르지 않고, 판정의 결과도 싣지 않는다.
    이 모양을 바꾸면 이미 만든 벡터와 어긋나고, 거리 기준(app/memory/retrieval.py)도 다시 재야 한다.
  - 프롬프트에 넣는 글(note_text). 글자 수의 상한 안에서 자른다. 자를 때 지키는 것이 둘이다.
      1. 결과가 빠지지 않는다. 한 말이 길어도 결과의 자리를 먼저 남긴다.
         한 말만 남으면 모델은 "하려던 일"을 "일어난 일"로 읽는다.
      2. 판정이 있던 줄에는 성공과 실패를 붙인다. 결과의 서술을 자르면 성패가 잘려 나갈 수 있다.
         주사위의 숫자는 싣지 않는다. 숫자를 주면 모델이 그것을 장면에 쓴다.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.rounds.narrator import PastRound

# 아무도 선언하지 않은 라운드의 한 말 자리. 지난 기록(app/rounds/prompt.py)과 같은 말이다
NOBODY_DECLARED = '(아무도 선언하지 않았다)'
# 결과의 서술 앞에 붙이는 말
RESULT_HEAD = '결과: '
# 판정이 있던 줄의 끝에 붙이는 말(프롬프트에 넣는 글에만)
SUCCEEDED = ' (판정 성공)'
FAILED = ' (판정 실패)'
# 문장의 끝. 마침표·느낌표·물음표·말줄임표 뒤에 빈칸이 오거나 글이 끝나는 곳, 그리고 줄바꿈
SENTENCE_END = re.compile(r'[.!?…](?=\s|$)|\n')
# 잘랐다는 표시
CLIPPED = '…'


@dataclass(frozen=True)
class Memory:
    """
    지난 라운드 하나의 기억. lines 는 "캐릭터 이름: 한 말" 한 줄씩, result 는 그 결과를 서술한 글이다.

    successes 는 줄마다 판정이 성공했는가다. lines 와 같은 차례이고, 판정이 없던 줄은 None 이다.
    비어 있으면 판정을 모른다(PastRound 와 같다).
    """

    number: int
    lines: tuple[str, ...]
    result: str
    successes: tuple[bool | None, ...] = ()


def memories_of(rounds: Sequence[PastRound]) -> list[Memory]:
    """
    라운드들로 기억을 만든다. 다음 라운드가 있는 라운드만 기억이 된다. 라운드 번호 순이다.

    rounds 는 한 테이블의 라운드들이다. 차례가 섞여 있어도 된다.
    """
    by_number = {past.number: past for past in rounds}
    return [
        Memory(past.number, tuple(past.lines), by_number[past.number + 1].scene, tuple(past.successes))
        for past in sorted(rounds, key=lambda past: past.number)
        if past.number + 1 in by_number
    ]


def memory_text(memory: Memory) -> str:
    """
    기억의 글 전부. 한 말을 한 줄씩, 그다음 "결과: " 뒤에 서술. 벡터로 바꿀 때와 인물을 찾을 때 쓴다.

    자르지 않고 판정의 결과도 붙이지 않는다. 프롬프트에 넣는 글은 note_text 다.
    """
    said = list(memory.lines) or [NOBODY_DECLARED]
    return '\n'.join([*said, f'{RESULT_HEAD}{memory.result}'])


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


def verdict_mark(success: bool | None) -> str:
    """줄의 끝에 붙일 판정의 결과. 판정이 없었으면 붙이지 않는다."""
    if success is None:
        return ''
    return SUCCEEDED if success else FAILED


def line_marks(memory: Memory) -> list[str]:
    """
    기억의 줄마다 붙일 판정의 결과. lines 와 같은 차례다.

    successes 가 줄의 수와 맞지 않으면(비어 있음: 판정을 모른다) 아무 줄에도 붙이지 않는다.
    """
    if len(memory.successes) != len(memory.lines):
        return ['' for _ in memory.lines]
    return [verdict_mark(success) for success in memory.successes]


def fair_limits(lengths: Sequence[int], budget: int) -> list[int]:
    """
    글자 수 budget 을 글들에 고르게 나눈다. 글마다 쓸 수 있는 글자 수를 lengths 와 같은 차례로 돌려준다.

    짧은 글은 제 길이만 쓰고, 남은 몫은 긴 글들이 나눠 갖는다. 한 사람의 긴 선언이 다른 사람의 선언을 밀어내지 않는다.
    """
    limits = [0] * len(lengths)
    remaining = max(budget, 0)
    for left, index in enumerate(sorted(range(len(lengths)), key=lambda index: lengths[index])):
        share = remaining // (len(lengths) - left)
        limits[index] = min(lengths[index], share)
        remaining -= limits[index]
    return limits


def said_lines(memory: Memory, limit: int) -> list[str]:
    """
    프롬프트에 넣을 한 말의 줄들. 줄바꿈까지 합쳐 limit 자를 넘지 않게 줄마다 문장 끝에서 자른다.

    판정이 있던 줄은 끝에 성공이나 실패가 붙는다. 그 표시는 잘리지 않는다. 글을 그만큼 덜 남긴다.
    아무도 선언하지 않았으면 그렇다고 적은 한 줄이다.
    """
    if not memory.lines:
        return [NOBODY_DECLARED]
    marks = line_marks(memory)
    lengths = [len(line) + len(mark) for line, mark in zip(memory.lines, marks, strict=True)]
    limits = fair_limits(lengths, limit - (len(memory.lines) - 1))
    return [
        clip(line, max(room - len(mark), len(CLIPPED))) + mark
        for line, mark, room in zip(memory.lines, marks, limits, strict=True)
    ]


def note_text(memory: Memory, limit: int, lines_limit: int) -> str:
    """
    기억을 프롬프트에 넣을 글. 한 말을 한 줄씩, 그다음 "결과: " 뒤에 서술. 모두 합쳐 limit 자를 넘지 않는다.

    결과의 자리를 먼저 남긴다. 한 말은 lines_limit 자까지 쓰고, 결과가 짧아 자리가 남으면 그만큼 더 쓴다.
    그래서 한 말이 아무리 길어도 결과는 limit - lines_limit 자 가까이 들어간다.
    lines_limit 은 limit 보다 충분히 작아야 한다(app/memory/retrieval.py 의 상수).
    """
    result = f'{RESULT_HEAD}{memory.result}'
    said = '\n'.join(said_lines(memory, max(lines_limit, limit - len(result) - 1)))
    return f'{said}\n{clip(result, limit - len(said) - 1)}'


def missing_memories(memories: list[Memory], done: set[int]) -> list[Memory]:
    """아직 벡터가 없는 기억들. done 은 이미 벡터가 있는 라운드의 번호다."""
    return [memory for memory in memories if memory.number not in done]
