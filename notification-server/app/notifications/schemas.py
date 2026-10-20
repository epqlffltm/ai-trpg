# notification-server/app/notifications/schemas.py

"""
알림 넣기 API 의 요청과 응답의 모양.

DB 의 제약(app/notifications/models.py)과 같은 규칙을 여기서 먼저 본다. 틀린 요청은 DB 에 닿기 전에 422 다.
DB 의 제약은 코드에 실수가 있을 때의 마지막 방어선이다.
"""

import enum
import json
import uuid
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.notifications.models import KIND_MAX_LENGTH, SOURCE_KEY_MAX_LENGTH

# 받는 일의 값(JSON)의 상한(바이트, 빈칸 없이 줄인 UTF-8). DB 의 상한(PAYLOAD_MAX_BYTES, 4096)의 절반이다.
# DB 는 jsonb 를 글자로 바꿀 때 쉼표와 쌍점 뒤에 빈칸을 넣는다. 받은 값이 이 상한 안이면 DB 의 상한도 넘지 않는다
PAYLOAD_INPUT_MAX_BYTES = 2048

# 무슨 일인가. 점으로 나눈 소문자(scenario.sanctioned). DB 의 kind_format 과 같다
KIND_PATTERN = r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$'
# 넣는 서버가 붙이는 열쇠. 보이는 ASCII 글자만(빈칸, 줄바꿈 없이). 로그와 검색에서 헷갈리지 않게 한다
SOURCE_KEY_PATTERN = r'^[!-~]+$'


def compact_size(payload: dict[str, Any]) -> int:
    """일의 값을 빈칸 없이 JSON 으로 줄였을 때의 바이트 수."""
    return len(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode())


def require_small_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """일의 값이 상한을 넘으면 거절한다. 원문은 그 일을 맡은 서버에 둔다."""
    if compact_size(payload) > PAYLOAD_INPUT_MAX_BYTES:
        raise ValueError(f'payload 는 {PAYLOAD_INPUT_MAX_BYTES}바이트 이하여야 한다')
    return payload


class NotificationIn(BaseModel):
    """넣는 서버가 보내는 알림 하나. 넣은 서버(source)는 주소에서 정한다. 본문으로 받지 않는다."""

    # 모르는 칸이 오면 거절한다. 넣는 서버의 오타(user 를 user_id 로)가 조용히 버려지지 않게 한다
    model_config = ConfigDict(extra='forbid')

    source_key: str = Field(min_length=1, max_length=SOURCE_KEY_MAX_LENGTH, pattern=SOURCE_KEY_PATTERN)
    user_id: uuid.UUID
    kind: str = Field(min_length=1, max_length=KIND_MAX_LENGTH, pattern=KIND_PATTERN)
    payload: Annotated[dict[str, Any], AfterValidator(require_small_payload)]


class PutStatus(enum.StrEnum):
    """넣기의 결과."""

    # 새로 적었다(201)
    CREATED = 'created'
    # 같은 열쇠의 같은 알림이 이미 있었다(200). 다시 보낸 것이다
    EXISTING = 'existing'
    # 받는 사람이 이 종류를 껐다(200). 적지 않았다. 넣는 서버는 보낸 것으로 친다(#525)
    MUTED = 'muted'


class NotificationPut(BaseModel):
    """넣기의 답. 넣는 서버는 이것을 받으면 발송함에서 그 줄을 지운다."""

    # 적은 줄의 번호. 받는 사람이 꺼서 적지 않았으면(muted) 없다
    id: int | None
    status: PutStatus
