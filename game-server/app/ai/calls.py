# game-server/app/ai/calls.py

"""
AI 호출 한 번의 기록과, 그 기록을 받는 곳(CallLog)의 모양.

AI 를 부르는 코드는 부를 때마다 기록을 하나 넘긴다. 성공했든, 답을 받지 않았든, 부르지 못했든.
실패한 호출도 시간과 토큰을 썼다. 사용량과 비용의 근거는 빠짐없이 남아야 한다.

기록을 어디에 쓰는지는 모른다. 앱은 DB 에 쓰는 것을, 테스트는 목록에 쌓는 가짜를 꽂는다(app/ai/fake.py).
provider 를 바꿔 끼우는 것과 같은 방식이다.

생각 글(reasoning)은 기록에 넣지 않는다. GM 메모를 따져 본 내용이 들어 있을 수 있다.
보낸 메시지도 넣지 않는다. 라운드에 굳혀 둔 것과 판의 복사본, 틀의 버전으로 다시 조립할 수 있다.
"""

import enum
import uuid
from dataclasses import dataclass
from typing import Protocol

from app.ai.provider import Reasoning


class Outcome(enum.StrEnum):
    """호출이 어떻게 끝났나."""

    # 답을 받아 썼다
    OK = 'ok'
    # 답은 왔지만 쓰지 않았다. 끊겼거나, 비었거나, 너무 길다
    REJECTED = 'rejected'
    # 답을 받지 못했다. 연결이 안 되거나, 시간이 넘었거나, 이상한 답이 왔다
    FAILED = 'failed'


@dataclass(frozen=True)
class CallScope:
    """
    무엇을 위해, 어느 테이블에서 불렀나. 부르는 쪽이 채운다.

    purpose 는 쓰임새다(narration). host_id 는 부를 때의 방장이다. 나중에 비용을 누구에게 매길지의 근거다.
    """

    purpose: str
    table_id: uuid.UUID | None = None
    round_number: int | None = None
    host_id: uuid.UUID | None = None


@dataclass(frozen=True)
class CallRecord:
    """
    AI 호출 한 번. 무엇을 위해, 어떤 조건으로 불렀고, 어떻게 끝났나.

    error 는 쓰지 않았거나 받지 못한 이유다(cut_off, timeout …). 잘 끝났으면 None.
    text 는 모델이 쓴 글이다. 쓰지 않은 글도 남긴다. 왜 쓰지 않았는지 나중에 볼 수 있다. 받지 못했으면 None.
    토큰 수와 멈춘 이유는 provider 가 알려 준 만큼이다. 모르면 None.
    """

    scope: CallScope
    provider: str
    model: str
    prompt_version: str
    reasoning: Reasoning
    outcome: Outcome
    latency_ms: int
    narration_style: str | None = None
    error: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    text: str | None = None


class CallLog(Protocol):
    """호출 기록을 받는 곳의 모양. 이 메서드가 있으면 기록장이다."""

    async def write(self, record: CallRecord) -> None:
        """기록 하나를 남긴다. 고치거나 지우는 길은 없다."""
        ...
