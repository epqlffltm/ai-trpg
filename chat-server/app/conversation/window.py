# chat-server/app/conversation/window.py

"""
모델에 보낼 최근 대화를 고른다(docs/architecture/chat-server.md 의 "기억"의 첫 층). DB 도 모델도 모른다.

지금 보고 있는 가지의 말들(첫 말부터 차례로)에서 가장 최근 것부터 거꾸로 채운다.
글자 수의 상한(budget)을 넘기 직전까지다.
  - 마지막 말(방금 보낸 사람의 말)은 상한을 넘어도 넣는다. 그것 없이 답할 수 없다.
  - 중간을 건너뛰지 않는다. 넘는 말을 만나면 거기서 멈춘다. 대화의 앞뒤가 끊기지 않게 한다.
  - 창 밖으로 밀려난 앞부분은 요약이 맡는다(나중 단계, "굴리는 요약").
토큰이 아니라 글자로 센다. 모델마다 토큰을 세는 법이 달라, 정확히 세려면 모델마다 토크나이저가 든다. 어림으로 충분하다.
"""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Turn:
    """대화의 말 하나. role 은 user 나 assistant 다."""

    role: str
    content: str


def select_window(turns: Sequence[Turn], budget: int) -> list[Turn]:
    """최근 말부터 budget 글자 안에 드는 만큼. 첫 말부터 차례로 돌려준다. 마지막 말은 늘 든다."""
    chosen: list[Turn] = []
    used = 0
    for turn in reversed(turns):
        used += len(turn.content)
        if chosen and used > budget:
            break
        chosen.append(turn)
    return list(reversed(chosen))
