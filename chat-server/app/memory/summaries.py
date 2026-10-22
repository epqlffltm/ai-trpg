# chat-server/app/memory/summaries.py

"""
굴리는 요약의 규칙. DB 도 모델도 모르는 순수 함수다.

  - 창 밖(overflow): 최근 대화의 창(app/conversation/window.py)에 들지 못하고 밀려난 앞부분
  - 요약할 때: 밀려난 말 가운데 마지막 요약 뒤의 것이 SUMMARY_AFTER_MESSAGES 개를 넘으면 요약한다.
    앞의 요약과 그 뒤의 말을 합쳐 새 요약을 쓴다(굴린다). 새 요약은 밀려난 마지막 말에 붙는다
  - 모델에 보낼 때: 밀려난 말 가운데 가장 뒤의 요약을 "[앞의 줄거리]" 로 카드에 넣는다.
    그 요약 뒤에서 창 앞까지의 말은 다음 요약이 생길 때까지 빠진다(요약은 응답과 따로 돌아 늦게 생긴다)
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from ai_core.provider import ChatMessage, Role

from app.conversation.window import Turn, select_window

# 모델이 요약에 쓸 글의 길이의 상한(토큰)과 지시의 글자 수
SUMMARY_OUTPUT_LIMIT = 600
SUMMARY_TARGET_CHARS = 800
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
    """요약할 것. previous 는 앞의 요약(없으면 None), fresh 는 그 뒤에서 새로 요약할 말들이다."""

    previous: str | None
    fresh: list[PathMessage]


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


def plan_summary(dropped: Sequence[PathMessage], summaries: Mapping, after_messages: int) -> Plan | None:
    """새로 요약할 것. 마지막 요약 뒤에 밀려난 말이 after_messages 개보다 적으면 None."""
    index = last_summarized(dropped, summaries)
    fresh = list(dropped[index + 1 :])
    if len(fresh) < after_messages:
        return None
    return Plan(summaries[dropped[index].id] if index >= 0 else None, fresh)


def summary_messages(plan: Plan) -> list[ChatMessage]:
    """요약을 시키는 메시지. 지시(system)와, 앞의 줄거리와 이어진 대화(user)다."""
    instruction = (
        '너는 대화를 요약하는 도우미다. 앞의 줄거리와 이어진 대화를 합쳐 새 줄거리를 쓴다. '
        '다음 대화를 이어 가는 데 필요한 것(일어난 일, 약속, 관계의 변화, 사용자에 대해 알게 된 것)만 '
        f'3인칭 과거형으로 {SUMMARY_TARGET_CHARS}자 안에 쓴다. 대화에 없는 것은 지어내지 않는다. 줄거리만 쓴다.'
    )
    lines = [f'{SPEAKERS.get(message.role, message.role)}: {message.content}' for message in plan.fresh]
    body = '\n\n'.join(
        part
        for part in (
            f'[앞의 줄거리]\n{plan.previous}' if plan.previous else None,
            '[이어진 대화]\n' + '\n'.join(lines),
        )
        if part
    )
    return [ChatMessage(role=Role.SYSTEM, content=instruction), ChatMessage(role=Role.USER, content=body)]


def render_story(text: str | None) -> str | None:
    """카드의 "[앞의 줄거리]" 블록. 요약이 없으면 None."""
    return f'[앞의 줄거리]\n{text}' if text else None
