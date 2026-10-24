# shared/conversation-core/src/conversation_core/changes.py

"""
모델이 답 끝에 쓰는 상태 바꾸기의 제안(#676, docs/architecture/chat-server.md 의 "모델의 제안"). DB 도 모델도 모른다.

모델에게 "바꿀 것이 있으면 본문 뒤에 표식(CHANGES_MARKER)을 쓰고 한 줄에 하나씩 써라"고 시킨다(instruction).
다음 답 추천과 같은 응답에서 받는다. 따로 부르지 않는다(정액 과금이 깨진다). 줄의 모양은 셋이다.

  affection +2      호감도를 바꾼다(부호 있는 정수)
  give rose         사용자에게 물건을 준다(물건의 id)
  move library      함께 다른 장소로 간다(장소의 id)

여기서는 모양만 읽는다(parse_changes). 해도 되는지와 크기의 상한은 쓰는 서버의 엔진이 본다
(chat 서버의 app/world/proposals.py).
모양이 틀린 줄은 버린다. 같은 종류가 여럿이면 처음 것만 쓴다. 오류로 만들지 않는다. 대화는 그대로다.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace

from conversation_core.markers import CHANGES_CLOSING, CHANGES_MARKER, block_after
from conversation_core.suggestions import clean_line

# 블록에서 읽는 줄의 수의 상한. 모델이 길게 써도 이만큼만 본다
MAX_LINES = 10
# 줄의 모양. id 는 asset 의 판과 같다(영문자, 숫자, _, -, 40자)
AFFECTION_LINE = re.compile(r'^affection\s*([+-]?\d{1,3})$', re.IGNORECASE)
GIVE_LINE = re.compile(r'^give\s+([A-Za-z0-9_-]{1,40})$', re.IGNORECASE)
MOVE_LINE = re.compile(r'^move\s+([A-Za-z0-9_-]{1,40})$', re.IGNORECASE)


@dataclass(frozen=True)
class Proposed:
    """모델이 제안한 것. affection 은 바꾸는 크기, gift 는 줄 물건의 id, move 는 갈 장소의 id 다. 없으면 None."""

    affection: int | None = None
    gift: str | None = None
    move: str | None = None


@dataclass(frozen=True)
class Choice:
    """모델에게 보여 줄 고를 거리 하나(id 와 이름)."""

    id: str
    name: str


def instruction(step: int, gifts: Sequence[Choice], moves: Sequence[Choice]) -> str | None:
    """
    카드에 덧붙이는 지시. 지금 할 수 있는 것만 적는다(step 은 호감도를 바꿀 수 있는 크기, 0 이면 바꾸지 못한다).
    할 수 있는 것이 없으면 None(지시를 넣지 않는다).
    """
    lines = []
    if step > 0:
        lines.append(f'affection +2 : 이 답으로 사용자에 대한 마음이 바뀌었으면 쓴다. -{step} 에서 +{step} 까지.')
    if gifts:
        listed = ', '.join(f'{choice.id}({choice.name})' for choice in gifts)
        lines.append(f'give 물건의id : 답에서 사용자에게 물건을 주었으면 쓴다. 줄 수 있는 것: {listed}')
    if moves:
        listed = ', '.join(f'{choice.id}({choice.name})' for choice in moves)
        lines.append(f'move 장소의id : 답에서 사용자와 함께 다른 곳으로 갔으면 쓴다. 갈 수 있는 곳: {listed}')
    if not lines:
        return None
    return '\n'.join(
        [
            f'답에서 일어난 일로 상태가 바뀌면 본문을 다 쓴 뒤 새 줄에 {CHANGES_MARKER} 를 쓴다.',
            '그 아래에 바뀐 것을 한 줄에 하나씩 쓴다.',
            *lines,
            '바뀐 것이 없으면 표식도 쓰지 않는다. 본문에는 이 줄들을 쓰지 않는다. 서버가 받아들인 것만 이루어진다.',
        ]
    )


def read_line(line: str, proposed: Proposed) -> Proposed:
    """한 줄을 읽어 아직 없는 종류면 더한다. 모양이 틀리면 그대로다."""
    text = clean_line(line)
    affection = AFFECTION_LINE.match(text)
    if affection and proposed.affection is None:
        return replace(proposed, affection=int(affection.group(1)))
    gift = GIVE_LINE.match(text)
    if gift and proposed.gift is None:
        return replace(proposed, gift=gift.group(1))
    move = MOVE_LINE.match(text)
    if move and proposed.move is None:
        return replace(proposed, move=move.group(1))
    return proposed


def parse_changes(text: str) -> Proposed:
    """다 받은 글에서 상태 바꾸기의 제안. 표식이 없으면 빈 제안이다."""
    block = block_after(text, CHANGES_MARKER, CHANGES_CLOSING)
    proposed = Proposed()
    if block is None:
        return proposed
    lines = [line for line in block.splitlines() if line.strip()]
    for line in lines[:MAX_LINES]:
        proposed = read_line(line, proposed)
    return proposed
