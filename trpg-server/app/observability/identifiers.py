# trpg-server/app/observability/identifiers.py

"""
요청과 작업을 가리키는 식별자의 규칙. 다른 것을 모르는 순수한 함수들이다. 규격은 docs/observability.md 에 있다.

식별자는 셋이다.
  - request_id: 이 서버가 받은 요청 하나. 밖에서 준 값이 형식에 맞으면 그대로 쓰고, 아니면 새로 만든다.
  - trace_id: 한 사용자의 요청이 여러 서버를 거칠 때 그 전체. W3C Trace Context 의 trace-id 와 같은 모양이다.
  - job_id: 요청과 따로 도는 작업 하나.

식별자는 기록을 서로 잇는 데만 쓴다. 누구인지, 해도 되는지를 판단하는 데 쓰지 않는다. 밖에서 정할 수 있는 값이다.

밖에서 받은 값은 형식을 먼저 본다. 로그에 그대로 적히는 값이라, 줄바꿈이나 제어 문자가 섞이면
가짜 로그 줄을 끼워 넣을 수 있다. 형식에 맞지 않으면 고쳐 쓰지 않고 버린다.
"""

import re
import secrets
import uuid
from dataclasses import dataclass

# 요청 식별자를 주고받는 머리말. 응답에도 같은 이름으로 돌려준다
REQUEST_ID_HEADER = 'X-Request-ID'
# 추적 정보를 주고받는 머리말. W3C Trace Context 의 이름 그대로다. 나중에 OpenTelemetry 가 같은 머리말을 읽는다
TRACEPARENT_HEADER = 'traceparent'

# 밖에서 받는 요청 식별자의 모양. 영문, 숫자, 점, 밑줄, 붙임표로 8자에서 64자. UUID 가 여기에 든다
REQUEST_ID = re.compile(r'[A-Za-z0-9._-]{8,64}')
# traceparent 의 모양(버전 00). 버전-추적 식별자(32자)-부모 식별자(16자)-표시(2자). 모두 소문자 16진수다
TRACEPARENT = re.compile(r'00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})')
# 머리말 값을 이보다 길게 주면 형식을 보지도 않고 버린다
MAX_HEADER_LENGTH = 128
# 새로 시작하는 추적의 표시. 아직 추적을 모으는 곳이 없어서 "모으지 않음"이다
NOT_SAMPLED = '00'


@dataclass(frozen=True)
class Trace:
    """서버들을 거치는 흐름 하나. trace_id 는 소문자 16진수 32자, flags 는 받은 표시를 그대로 넘기려고 둔다."""

    trace_id: str
    flags: str = NOT_SAMPLED


def accept_request_id(value: str | None) -> str | None:
    """밖에서 받은 요청 식별자가 형식에 맞으면 그대로 돌려준다. 없거나 맞지 않으면 None 이다."""
    if value is None or len(value) > MAX_HEADER_LENGTH:
        return None
    return value if REQUEST_ID.fullmatch(value) else None


def new_request_id() -> str:
    """새 요청 식별자. UUID 다."""
    return str(uuid.uuid4())


def request_id_from(value: str | None) -> str:
    """이 요청의 식별자를 정한다. 밖에서 받은 값이 쓸 만하면 그것을, 아니면 새것을 쓴다."""
    return accept_request_id(value) or new_request_id()


def new_job_id() -> str:
    """새 작업 식별자. UUID 다."""
    return str(uuid.uuid4())


def is_all_zero(text: str) -> bool:
    """0 으로만 된 값인가. 추적 식별자와 부모 식별자는 0 으로만 될 수 없다."""
    return set(text) == {'0'}


def parse_traceparent(value: str | None) -> Trace | None:
    """
    traceparent 머리말에서 추적을 읽는다. 없거나 형식에 맞지 않으면 None 이다.

    버전 00 만 읽는다. 추적 식별자와 표시만 쓰고, 부모 식별자는 버린다. 이 서버는 구간(span)을 기록하지 않는다.
    """
    if value is None or len(value) > MAX_HEADER_LENGTH:
        return None
    match = TRACEPARENT.fullmatch(value.strip())
    if match is None or is_all_zero(match[1]) or is_all_zero(match[2]):
        return None
    return Trace(trace_id=match[1], flags=match[3])


def new_trace() -> Trace:
    """새 추적을 시작한다."""
    return Trace(trace_id=secrets.token_hex(16))


def trace_from(value: str | None) -> Trace:
    """이 요청의 추적을 정한다. 밖에서 받은 것이 쓸 만하면 이어 가고, 아니면 새로 시작한다."""
    return parse_traceparent(value) or new_trace()


def format_traceparent(trace: Trace) -> str:
    """
    다른 서버에 보낼 traceparent 값을 만든다.

    부모 식별자는 부를 때마다 새로 만든다. 받는 쪽은 추적 식별자만 이어 쓴다.
    """
    return f'00-{trace.trace_id}-{secrets.token_hex(8)}-{trace.flags}'
