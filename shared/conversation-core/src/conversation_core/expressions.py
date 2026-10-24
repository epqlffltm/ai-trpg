# shared/conversation-core/src/conversation_core/expressions.py

"""
표정 고르기(2026-10-23 유저 결정). DB 도 모델도 모른다.

캐릭터 그림(asset 의 판 형식 6)에 표정이 있으면, 모델에게
"답의 맨 앞에 표식(OPEN 표정 CLOSE)을 쓰고 본문을 써라"고 시킨다.
맨 앞이라 글이 흘러나오기 시작할 때 그림을 바꿀 수 있다(미연시처럼). 호출을 따로 하지 않는다.

  - 흘려 받을 때는 맨 앞의 몇 글자를 붙잡는다(ExpressionHead). 표식으로 시작하지 않는다는 것을 알면 바로 내보낸다.
    표식이 닫히면 표정을 떼어 두고 그 뒤부터 본문으로 내보낸다
  - 표정은 고를 수 있는 것(그 캐릭터 그림에 있는 이름) 가운데 하나여야 한다(match_expression). 대소문자는 가리지 않는다.
    아니거나 "기본"이면 기본 표정(None)이다. 표식이 틀려도 오류로 만들지 않는다. 대화는 그대로다
  - HEAD_MAX 글자 안에 표식이 닫히지 않으면 표식이 아닌 것으로 보고 받은 그대로 내보낸다
이어서 출력에는 쓰지 않는다(끊긴 답의 표정을 그대로 둔다).
"""

from collections.abc import Collection
from dataclasses import dataclass

OPEN = '<expression>'
CLOSE = '</expression>'
# 표식을 기다리는 글자의 상한. 표정의 이름은 20자까지다(asset 의 SPRITE_EXPRESSION_MAX_LENGTH)
HEAD_MAX = len(OPEN) + 40 + len(CLOSE)
# 기본 표정을 뜻하는 이름. 모델이 써도 된다
BASE_NAMES = frozenset({'', '기본'})


def instruction(names: Collection[str]) -> str:
    """카드에 덧붙이는 지시. 고를 수 있는 표정을 늘어놓는다."""
    choices = ', '.join(['기본', *names])
    return '\n'.join(
        [
            f'답의 맨 앞에 {OPEN}표정{CLOSE} 를 쓰고 그 뒤에 본문을 쓴다.',
            f'표정은 이 가운데 하나다: {choices}. 이번 답의 캐릭터의 표정에 맞는 것을 고른다.',
        ]
    )


def match_expression(raw: str | None, names: Collection[str]) -> str | None:
    """모델이 쓴 표정을 고를 수 있는 이름으로. 없거나 기본이거나 모르는 이름이면 None(기본 표정)."""
    if raw is None or raw.strip() in BASE_NAMES:
        return None
    wanted = raw.strip().casefold()
    return next((name for name in names if name.casefold() == wanted), None)


@dataclass
class ExpressionHead:
    """
    흘려 받는 글의 맨 앞에서 표정의 표식을 뗀다. 정하기 전에는 받은 글을 붙잡고, 정한 뒤에는 그대로 내보낸다.

    raw 는 모델이 쓴 표정(표식 안의 글)이다. 표식이 없으면 None 이다. decided 가 참이 되면 더 붙잡지 않는다.
    표식 바로 뒤의 빈칸과 줄바꿈은 본문이 시작할 때까지 뗀다(trimming).
    """

    held: str = ''
    decided: bool = False
    raw: str | None = None
    trimming: bool = False

    def feed(self, piece: str) -> str:
        """조각 하나를 받는다. 지금 내보낼 본문(비어 있을 수 있다)."""
        if self.decided:
            return self.trim(piece)
        self.held += piece
        start = self.held.lstrip()
        if OPEN.startswith(start):
            return ''
        if not start.startswith(OPEN):
            return self.give_up()
        end = start.find(CLOSE)
        if end < 0:
            return self.give_up() if len(start) > HEAD_MAX else ''
        self.raw = start[len(OPEN) : end]
        self.decided = True
        self.trimming = True
        self.held = ''
        return self.trim(start[end + len(CLOSE) :])

    def trim(self, piece: str) -> str:
        """표식 뒤의 빈칸을 본문이 시작할 때까지 뗀다."""
        if not self.trimming:
            return piece
        text = piece.lstrip()
        self.trimming = not text
        return text

    def release(self) -> str:
        """끝났다. 아직 정하지 않았으면 붙잡은 글을 그대로 내보낸다."""
        return '' if self.decided else self.give_up()

    def give_up(self) -> str:
        """표식이 없다. 붙잡은 글을 그대로 내보내고 이 뒤로는 받는 대로 내보낸다."""
        text, self.held = self.held, ''
        self.decided = True
        return text


def split_expression(text: str) -> tuple[str | None, str]:
    """다 받은 글을 (모델이 쓴 표정, 나머지)로. 흘려 받을 때와 같은 규칙이다."""
    head = ExpressionHead()
    rest = head.feed(text) + head.release()
    return head.raw, rest
