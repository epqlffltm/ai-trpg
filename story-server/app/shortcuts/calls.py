# story-server/app/shortcuts/calls.py

"""
단축어를 부르는 말을 읽는다(#981). DB 도 바깥도 모른다. chat 서버의 것과 같은 규칙이다.

  - 말의 맨 앞의 "/이름"만 부른 것으로 본다. 이름 뒤는 빈칸이나 줄 바꿈이거나 말의 끝이다(split_call)
  - 세계관의 판에 같은 이름이 있으면 그것을 쓰고, 없으면 내 단축어에서 찾는다(pick). 없는 이름이면 그냥 글이다
  - 본문은 SHORTCUT_BODY_MAX_CHARS 까지만 붙인다(asset 서버의 상한과 같다. 판의 사본이 그보다 길어도 넘지 않는다)
  - 본문은 사람의 말 안에 붙는다(model_text). 시스템 지시(카드)에 넣지 않는다. 엔진의 상태를 바꾸지 못한다
    (판정은 행동 API 만 한다. 사람의 말은 상태를 바꾸지 않는다).
    그 턴(이번에 답하는 사람의 말)에만 붙는다. 지난 말에는 부른 이름을 뗀 글만 간다
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

# 단축어의 이름(asset 서버의 SHORTCUT_NAME_MAX_LENGTH, SHORTCUT_NAME_PATTERN 과 같다)
SHORTCUT_NAME_MAX_CHARS = 10
# 붙이는 본문의 길이의 끝(asset 서버의 SHORTCUT_BODY_MAX_LENGTH 와 같다)
SHORTCUT_BODY_MAX_CHARS = 400
# 말의 맨 앞의 "/이름". 이름 뒤는 빈칸이거나 말의 끝이다
CALL = re.compile(rf'^/([^\s/]{{1,{SHORTCUT_NAME_MAX_CHARS}}})(?:\s+|$)')
# 모델에 보낼 때 본문 앞에 붙인다. 사람의 말과 가른다
SHORTCUT_PREFIX = '[단축어]'


class Named(Protocol):
    """이름과 본문이 있는 단축어(판의 사본의 것이든 내 것이든)."""

    name: str
    description: str
    body: str


@dataclass(frozen=True)
class Call:
    """말이 부른 단축어. name 은 부른 이름, rest 는 그 뒤의 글(없으면 빈 글)이다."""

    name: str
    rest: str


def split_call(content: str) -> Call | None:
    """말의 맨 앞에서 부른 단축어. 부르지 않았으면 None."""
    match = CALL.match(content.lstrip())
    if match is None:
        return None
    return Call(name=match.group(1), rest=content.lstrip()[match.end() :].strip())


def find(name: str, shortcuts: Iterable[Named]) -> Named | None:
    """목록에서 그 이름의 단축어. 없으면 None."""
    return next((shortcut for shortcut in shortcuts if shortcut.name == name), None)


def pick(name: str, work: Iterable[Named], mine: Iterable[Named]) -> Named | None:
    """부른 이름의 단축어. 작품(세계관의 판)의 것이 먼저다. 둘 다 없으면 None."""
    return find(name, work) or find(name, mine)


def choosable[Shortcut: Named](work: Iterable[Shortcut], mine: Iterable[Shortcut]) -> list[tuple[Shortcut, bool]]:
    """
    고를 수 있는 단축어들과 작품의 것인지. 작품의 것이 먼저(적은 차례), 그 뒤에 내 것이다.
    작품에 같은 이름이 있는 내 단축어는 뺀다(불러도 작품의 것이 쓰인다).
    """
    listed = [(shortcut, True) for shortcut in work]
    names = {shortcut.name for shortcut, _ in listed}
    return [*listed, *((shortcut, False) for shortcut in mine if shortcut.name not in names)]


def clipped(body: str) -> str | None:
    """붙일 본문. 길이의 끝까지 자르고 앞뒤 빈칸을 지운다. 비면 None(붙이지 않는다)."""
    text = body.strip()[:SHORTCUT_BODY_MAX_CHARS].strip()
    return text or None


def body_for(content: str, work: Iterable[Named], mine: Iterable[Named]) -> str | None:
    """사람의 말이 부른 단축어의 본문(잘라 둔 것). 부르지 않았거나 없는 이름이면 None."""
    call = split_call(content)
    if call is None:
        return None
    found = pick(call.name, work, mine)
    return clipped(found.body) if found is not None else None


def model_text(content: str, body: str | None, current: bool) -> str:
    """
    사람의 말을 모델에 보낼 글. 단축어를 쓴 말(body 가 있다)이 아니면 그대로다.
    쓴 말이면 부른 이름을 뗀다. 그 턴(current)이면 본문을 SHORTCUT_PREFIX 와 함께 끝에 붙인다.
    지난 말에 남은 글이 없으면 적은 그대로 보낸다(빈 말을 보내지 않는다).
    """
    call = split_call(content) if body is not None else None
    if call is None:
        return content
    if current:
        added = f'{SHORTCUT_PREFIX} {body}'
        return f'{call.rest}\n\n{added}' if call.rest else added
    return call.rest or content
