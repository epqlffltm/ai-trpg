# shared/conversation-core/src/conversation_core/suggestions.py

"""
다음 답 추천(docs/architecture/chat-server.md 의 "다음 답 추천"). DB 도 모델도 모른다.

모델에게 "본문을 다 쓴 뒤 표식(MARKER)을 쓰고 그 아래에 선택지를 한 줄에 하나씩 써라"고 시킨다(instruction).
호출을 따로 하지 않아 원가가 거의 늘지 않는다. 받은 글은 셋으로 나눈다.

  - 본문: 표식 앞. 사람에게 흘리고 말의 content 로 저장한다. 다음 호출의 프롬프트에도 이것만 간다
  - 선택지: 표식 뒤. 다 받은 뒤에 거른다(parse_suggestions). 말의 suggestions 칸에만 둔다
    (본문에 섞으면 다음 호출에 다시 들어가 모델이 선택지를 흉내 낸다)

본문 뒤에는 상태 바꾸기의 제안(conversation_core/changes.py)도 올 수 있다. 본문은 어느 표식이든 처음 나온 것 앞까지다
(conversation_core/markers.py).

흘릴 때는 표식이 조각의 경계에 걸릴 수 있다. 그래서 끝의 몇 글자(표식의 앞부분일 수 있는 것)는
다음 조각이 올 때까지 붙잡는다(MarkerHold). 흘린 글 끝에 빈칸이 남을 수 있지만 저장하는 본문에서는 뺀다.
마지막 done 메시지가 저장한 말을 싣는다.

선택지를 거르는 규칙. 틀려도 오류로 만들지 않고 선택지만 줄이거나 없앤다. 대화는 그대로다.
  - 줄마다 하나. 앞의 번호, 글머리표, 감싼 따옴표는 뗀다. 빈 줄은 뺀다
  - SUGGESTION_MAX_CHARS 보다 긴 것은 뺀다(자르면 뜻이 틀어진다). 같은 것은 하나만 둔다
  - 앞에서부터 MAX_SUGGESTIONS 개까지
"""

import re
from dataclasses import dataclass, field

from conversation_core.markers import END_MARKERS, SUGGESTIONS_CLOSING, SUGGESTIONS_MARKER, block_after, first_marker

# 본문과 선택지를 가르는 표식. 영문 태그가 모델마다 가장 잘 지켜진다. 닫는 태그는 써도 되고 안 써도 된다
MARKER = SUGGESTIONS_MARKER
CLOSING = SUGGESTIONS_CLOSING
# 선택지의 수와 하나의 길이(글자)의 상한
MAX_SUGGESTIONS = 3
SUGGESTION_MAX_CHARS = 200
# 줄 앞의 번호와 글머리표(1. 1) - * •)
LEADING_MARK = re.compile(r'^(?:\d+[.)]|[-*•])\s*')
# 선택지를 감싼 따옴표
QUOTES = '"\'“”‘’「」'


def instruction() -> str:
    """카드에 덧붙이는 지시. 본문에서는 여전히 사용자를 대신 쓰지 않는다. 선택지는 사용자가 고를 후보다."""
    return '\n'.join(
        [
            f'답을 다 쓴 뒤 새 줄에 {MARKER} 를 쓴다.',
            '그 아래에 사용자가 이어서 할 만한 말이나 행동 셋을 한 줄에 하나씩 쓴다.',
            '선택지는 사용자의 입장에서 짧게 쓴다. 번호와 따옴표는 붙이지 않는다. 본문에는 선택지를 쓰지 않는다.',
        ]
    )


def held_length(text: str) -> int:
    """text 의 끝에서 어느 표식의 앞부분일 수 있는 가장 긴 길이. 표식이 다음 조각에서 마저 올 수 있다."""
    longest = max(len(marker) for marker in END_MARKERS) - 1
    for size in range(min(len(text), longest), 0, -1):
        if any(marker.startswith(text[-size:]) for marker in END_MARKERS):
            return size
    return 0


@dataclass
class MarkerHold:
    """
    흘려 받는 글에서 표식 앞(본문)만 내보낸다. 표식을 만나면 그 뒤(선택지, 상태 바꾸기의 제안)는 모아 두기만 한다.

    feed 는 지금 내보내도 되는 본문을 돌려준다. 표식의 앞부분일 수 있는 끝의 글자는 붙잡아 둔다.
    다 받은 뒤(또는 끊긴 뒤) release 가 붙잡은 본문을 내준다. 표식을 만났으면 붙잡은 것이 없다.
    """

    held: str = ''
    tail: str | None = None
    sent: list[str] = field(default_factory=list)

    def feed(self, piece: str) -> str:
        """조각 하나를 받는다. 지금 내보낼 본문(비어 있을 수 있다)."""
        if self.tail is not None:
            self.tail += piece
            return ''
        text = self.held + piece
        index = first_marker(text)
        if index >= 0:
            self.tail = text[index:].split('>', 1)[1]
            self.held = ''
            return self.send(text[:index])
        cut = len(text) - held_length(text)
        self.held = text[cut:]
        return self.send(text[:cut])

    def release(self) -> str:
        """끝났다. 붙잡아 둔 본문."""
        rest, self.held = self.held, ''
        return self.send(rest)

    def send(self, text: str) -> str:
        """내보낸 본문을 적어 두고 그대로 돌려준다."""
        if text:
            self.sent.append(text)
        return text

    def body(self) -> str:
        """지금까지 내보낸 본문(끝의 빈칸은 뺀다). 끊겼을 때 이만큼 저장한다. release 를 부른 뒤에 읽는다."""
        return ''.join(self.sent).rstrip()


def split_answer(text: str) -> tuple[str, str | None]:
    """
    다 받은 글을 본문과 선택지의 블록으로. 본문은 처음 나온 표식 앞까지다(본문 끝의 빈칸은 뺀다).
    선택지의 블록은 MARKER 뒤에서 닫는 태그나 상태 바꾸기의 표식 앞까지다. MARKER 가 없으면 None.
    """
    index = first_marker(text)
    if index < 0:
        return text.rstrip(), None
    return text[:index].rstrip(), block_after(text, MARKER, CLOSING)


def clean_line(line: str) -> str:
    """선택지 한 줄에서 번호, 글머리표, 감싼 따옴표를 뗀다."""
    text = LEADING_MARK.sub('', line.strip()).strip()
    if len(text) >= 2 and text[0] in QUOTES and text[-1] in QUOTES:
        text = text[1:-1].strip()
    return text


def parse_suggestions(tail: str | None) -> list[str]:
    """표식 뒤의 글에서 선택지들. 규칙은 이 파일의 설명에 있다. 없으면 빈 목록."""
    if tail is None:
        return []
    chosen: list[str] = []
    for line in tail.split(CLOSING, 1)[0].splitlines():
        text = clean_line(line)
        if text and len(text) <= SUGGESTION_MAX_CHARS and text not in chosen:
            chosen.append(text)
        if len(chosen) == MAX_SUGGESTIONS:
            break
    return chosen
