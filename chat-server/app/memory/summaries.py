# chat-server/app/memory/summaries.py

"""
굴리는 요약의 규칙. DB 도 모델도 모르는 순수 함수다.

  - 창 밖(overflow): 최근 대화의 창(conversation_core/window.py)에 들지 못하고 밀려난 앞부분
  - 요약할 때: 밀려난 말 가운데 마지막 요약 뒤의 것이 SUMMARY_AFTER_MESSAGES 개를 넘으면 요약한다.
    앞의 요약과 그 뒤의 말을 합쳐 새 요약을 쓴다(굴린다). 새 요약은 밀려난 마지막 말에 붙는다
  - 모델에 보낼 때: 밀려난 말 가운데 가장 뒤의 요약을 "[앞의 줄거리]" 로 카드에 넣는다.
    그 요약 뒤에서 창 앞까지의 말은 다음 요약이 생길 때까지 빠진다(요약은 응답과 따로 돌아 늦게 생긴다)
  - 메모의 제안(#677): 같은 호출에서 줄거리 뒤에 표식(NOTES_MARKER)을 쓰고 오래 기억할 사실을 셋까지 쓰게 한다.
    이미 적힌 메모(제안까지)를 함께 보여 주어 되풀이하지 않게 하고, 받은 뒤에도 같은 것은 거른다(pick_proposals).
    줄마다 하나, 번호와 따옴표는 떼고, 메모의 길이(NOTE_MAX_CHARS)를 넘는 것과 빈 것은 뺀다. 틀려도 오류가 아니다
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from ai_core.provider import ChatMessage, Role
from conversation_core.suggestions import clean_line
from conversation_core.window import Turn, select_window

from app.memory.models import NOTE_MAX_CHARS

# 모델이 요약에 쓸 글의 길이의 상한(토큰)과 지시의 글자 수. 메모의 제안이 뒤에 붙는 만큼 넉넉히 둔다
SUMMARY_OUTPUT_LIMIT = 800
SUMMARY_TARGET_CHARS = 800
# 줄거리와 메모의 제안을 가르는 표식. 닫는 태그는 써도 되고 안 써도 된다
NOTES_MARKER = '<notes>'
NOTES_CLOSING = '</notes>'
# 한 번의 요약이 제안하는 메모의 수의 상한
PROPOSALS_PER_SUMMARY = 3
# 대화의 말을 요약에 보낼 때 붙이는 이름
SPEAKERS = {'user': '사용자', 'assistant': '캐릭터', 'action': '행동'}


class PathMessage(Protocol):
    """가지의 말 하나의 모양(id, role, content). 테이블의 Message 가 이 모양이다."""

    @property
    def id(self): ...

    @property
    def role(self) -> str: ...

    @property
    def content(self) -> str: ...


@dataclass(frozen=True)
class Plan:
    """
    요약할 것. previous 는 앞의 요약(없으면 None), fresh 는 그 뒤에서 새로 요약할 말들이다.
    known 은 이미 적힌 메모의 글(제안까지)이다. 같은 것을 다시 제안하지 않게 모델에 보인다.
    """

    previous: str | None
    fresh: list[PathMessage]
    known: tuple[str, ...] = ()


def overflow[M: PathMessage](path: Sequence[M], context_chars: int) -> list[M]:
    """창에 들지 못하고 밀려난 앞부분. 첫 말부터 차례로."""
    kept = select_window([Turn(message.role, message.content) for message in path], context_chars)
    return list(path[: len(path) - len(kept)])


def last_summarized(dropped: Sequence[PathMessage], summaries: Mapping) -> int:
    """밀려난 말 가운데 요약이 붙은 가장 뒤의 말의 자리. 없으면 -1."""
    for index in range(len(dropped) - 1, -1, -1):
        if dropped[index].id in summaries:
            return index
    return -1


def latest_summary(dropped: Sequence[PathMessage], summaries: Mapping) -> str | None:
    """밀려난 말 가운데 가장 뒤의 요약의 글. 없으면 None. summaries 는 말의 id 에서 요약의 글로."""
    index = last_summarized(dropped, summaries)
    return summaries[dropped[index].id] if index >= 0 else None


def plan_summary(
    dropped: Sequence[PathMessage], summaries: Mapping, after_messages: int, known: Sequence[str] = ()
) -> Plan | None:
    """새로 요약할 것. 마지막 요약 뒤에 밀려난 말이 after_messages 개보다 적으면 None."""
    index = last_summarized(dropped, summaries)
    fresh = list(dropped[index + 1 :])
    if len(fresh) < after_messages:
        return None
    return Plan(summaries[dropped[index].id] if index >= 0 else None, fresh, tuple(known))


def summary_messages(plan: Plan) -> list[ChatMessage]:
    """요약을 시키는 메시지. 지시(system)와, 앞의 줄거리와 이어진 대화(user)다."""
    instruction = (
        '너는 대화를 요약하는 도우미다. 앞의 줄거리와 이어진 대화를 합쳐 새 줄거리를 쓴다. '
        '다음 대화를 이어 가는 데 필요한 것(일어난 일, 약속, 관계의 변화, 사용자에 대해 알게 된 것)만 '
        f'3인칭 과거형으로 {SUMMARY_TARGET_CHARS}자 안에 쓴다. 대화에 없는 것은 지어내지 않는다.\n'
        f'줄거리를 다 쓴 뒤 새 줄에 {NOTES_MARKER} 를 쓰고, '
        '오래 기억해 둘 사실(사용자에 대해 알게 된 것, 약속, 정해진 일)을 '
        f'{PROPOSALS_PER_SUMMARY}개까지 한 줄에 하나씩 짧게 쓴다. '
        '[이미 적힌 기억]에 있는 것은 쓰지 않는다. 없으면 표식도 쓰지 않는다.'
    )
    lines = [f'{SPEAKERS.get(message.role, message.role)}: {message.content}' for message in plan.fresh]
    body = '\n\n'.join(
        part
        for part in (
            '[이미 적힌 기억]\n' + '\n'.join(f'- {text}' for text in plan.known) if plan.known else None,
            f'[앞의 줄거리]\n{plan.previous}' if plan.previous else None,
            '[이어진 대화]\n' + '\n'.join(lines),
        )
        if part
    )
    return [ChatMessage(role=Role.SYSTEM, content=instruction), ChatMessage(role=Role.USER, content=body)]


def split_summary(text: str) -> tuple[str, list[str]]:
    """모델이 쓴 글을 (줄거리, 메모의 제안 줄들)로. 표식이 없으면 제안이 없다. 줄거리 끝의 빈칸은 뺀다."""
    index = text.find(NOTES_MARKER)
    if index < 0:
        return text.strip(), []
    tail = text[index + len(NOTES_MARKER) :].split(NOTES_CLOSING, 1)[0]
    return text[:index].strip(), tail.splitlines()


def normalized(text: str) -> str:
    """같은 메모인지 견줄 모양. 빈칸을 하나로 줄이고 대소문자를 가리지 않는다."""
    return ' '.join(text.split()).casefold()


def pick_proposals(lines: Sequence[str], known: Sequence[str], limit: int = PROPOSALS_PER_SUMMARY) -> list[str]:
    """제안 줄들에서 메모로 둘 것. 번호와 따옴표를 떼고, 빈 것, 긴 것, 이미 있는 것, 겹치는 것을 빼고 limit 개까지."""
    seen = {normalized(text) for text in known}
    chosen: list[str] = []
    for line in lines:
        text = clean_line(line)
        if not text or len(text) > NOTE_MAX_CHARS or normalized(text) in seen:
            continue
        seen.add(normalized(text))
        chosen.append(text)
        if len(chosen) == limit:
            break
    return chosen


def render_story(text: str | None) -> str | None:
    """카드의 "[앞의 줄거리]" 블록. 요약이 없으면 None."""
    return f'[앞의 줄거리]\n{text}' if text else None
