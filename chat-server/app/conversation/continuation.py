# chat-server/app/conversation/continuation.py

"""
이어서 출력(docs/architecture/chat-server.md 의 "과금"과 "대화 조작"). 끊긴 답(partial)에 이어 쓴다.
DB 도 모델도 모른다.

모델에게는 끊긴 답까지의 대화와, 맨 끝에 "끊긴 곳 바로 다음부터 이어 써라"는 지시(instruction)를 보낸다.
공급자마다 "답을 미리 채워 이어 쓰게 하는" 길이 있거나 없어서, 모든 공급자에서 똑같이 도는 지시로 한다.
지시는 사람의 차례(user)로 보낸다. 대화가 사람의 말로 끝나야 받는 공급자가 있다.

모델이 앞의 글 끝을 되풀이하고 이어 쓰는 일이 있다. 그래서 새 글의 앞이 앞 글의 끝과 겹치면 겹친 만큼 뗀다(OverlapTrim).
  - 앞 글의 끝 OVERLAP_SCAN 글자 안에서 찾는다. MIN_OVERLAP 글자보다 짧게 겹친 것은 우연으로 보고 둔다
  - 흘려 받을 때는 새 글이 아직 앞 글의 어느 끝부분과 같게 이어지는 동안 붙잡는다. 어긋나는 순간 정하고 내보낸다
    (되풀이하지 않는 보통의 답은 몇 글자 안에 어긋난다)
앞 글이 문장 끝(마침표 등)에서 끊겼고 새 글이 빈칸 없이 시작하면 빈칸 하나를 끼운다.
저장한 끊긴 답은 끝의 빈칸을 뺀 것이라, 끊긴 자리에 있던 빈칸이 사라졌을 수 있다.
"""

from dataclasses import dataclass

# 앞 글의 끝에서 겹침을 찾는 범위(글자)
OVERLAP_SCAN = 300
# 이보다 짧게 겹친 것은 떼지 않는다(글자)
MIN_OVERLAP = 8
# 이 글자로 끝나면 문장이 끝난 것으로 본다
SENTENCE_ENDS = frozenset('.!?…"\'」』)~')


def instruction() -> str:
    """대화 끝에 붙이는 이어 쓰기의 지시. 사람의 말이 아님을 밝힌다."""
    return (
        '(지시: 사용자의 말이 아니다. 바로 앞의 네 답이 중간에 끊겼다. '
        '끊긴 곳 바로 다음 글자부터 이어 쓴다. 앞의 글은 되풀이하지 않는다.)'
    )


def still_repeating(previous: str, text: str) -> bool:
    """text 가 아직 앞 글의 어느 끝부분과 같게 이어지는 중인가(더 받아야 겹침을 안다)."""
    tail = previous[-OVERLAP_SCAN:]
    return any(tail[start:].startswith(text) for start in range(len(tail)))


def repeated_length(previous: str, text: str) -> int:
    """text 의 앞이 앞 글의 끝과 겹친 길이. MIN_OVERLAP 보다 짧으면 0."""
    tail = previous[-OVERLAP_SCAN:]
    for start in range(len(tail)):
        suffix = tail[start:]
        if len(suffix) < MIN_OVERLAP:
            break
        if text.startswith(suffix):
            return len(suffix)
    return 0


def joiner(previous: str, text: str) -> str:
    """앞 글과 새 글 사이에 끼울 것. 문장 끝에서 끊겼고 새 글이 빈칸 없이 시작하면 빈칸 하나."""
    if not previous or not text or text[0].isspace() or previous[-1].isspace():
        return ''
    return ' ' if previous[-1] in SENTENCE_ENDS else ''


@dataclass
class OverlapTrim:
    """
    이어 쓴 글의 앞에서 되풀이한 부분을 떼고, 필요하면 빈칸을 끼운다. 흘려 받는 글에 쓴다.

    previous 는 앞 글(끊긴 답)이다. 정하기 전에는 받은 글을 붙잡고, 정한 뒤에는 그대로 내보낸다.
    """

    previous: str
    held: str = ''
    decided: bool = False

    def feed(self, piece: str) -> str:
        """조각 하나를 받는다. 지금 내보낼 글(비어 있을 수 있다)."""
        if self.decided:
            return piece
        self.held += piece
        if still_repeating(self.previous, self.held):
            return ''
        return self.decide()

    def release(self) -> str:
        """끝났다. 아직 정하지 않았으면 지금 정하고 붙잡은 글을 내보낸다. 정했으면 붙잡은 것이 없다."""
        return self.decide()

    def decide(self) -> str:
        """겹친 만큼 떼고 사이에 끼울 것을 붙여 내보낸다. 이 뒤로는 받는 대로 내보낸다. 붙잡은 것이 없으면 빈 글."""
        text = self.held[repeated_length(self.previous, self.held) :]
        self.held = ''
        self.decided = True
        return joiner(self.previous, text) + text


def continued_text(previous: str, text: str) -> str:
    """다 받은 이어 쓴 글에서 앞에 붙일 글. 흘려 받을 때와 같은 규칙이다."""
    trim = OverlapTrim(previous)
    return trim.feed(text) + trim.release()
