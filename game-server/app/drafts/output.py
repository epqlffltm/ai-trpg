# game-server/app/drafts/output.py

"""
초안을 쓰는 모델의 답(JSON)의 모양과, 글에서 그 모양을 읽는 법.

모델은 이름표(p1, i1, q1)로만 가리킨다. 이름이나 ID 를 쓰게 하지 않는 까닭:
  - ID(UUID)는 모델이 지어내기 쉽다. 한 글자만 틀려도 다른 것을 가리킨다.
  - 이름은 겹칠 수 있다(같은 이름의 캐릭터, 같은 이름의 물건). 이름표는 서버가 붙여서 겹치지 않는다.
이름표가 무엇을 가리키는지는 서버가 안다(app/drafts/context.py). 목록에 없는 이름표는 버린다.

모양이 틀린 답은 통째로 버린다. 고쳐 읽지 않는다. 고쳐 읽으면 모델이 뜻하지 않은 것을 받아들이게 된다.

목록에 없는 물건을 적을 자리(unlisted_items)가 따로 있다. 이름(글)이고 이름표가 아니다.
서버는 이것으로 장부를 바꾸지 않는다. 이 자리가 없을 때 모델은 목록에 없는 물건을 목록의 다른 물건으로 바꿔 적고,
설명과 두 번째 JSON 을 붙였다(ledger-draft-3). 적을 데가 있으면 억지로 끼워 넣지 않는다.
"""

import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from app.assets.models import ITEM_STACK_MAX

# 한 번의 답에 담을 수 있는 초안의 수. 한 라운드의 장면에서 이보다 많이 일어나지 않는다.
# 넘으면 답을 통째로 버린다. 모델이 목록을 늘어놓기 시작한 것이다
MAX_FOUND_ITEMS = 8
MAX_QUEST_CHANGES = 5
MAX_UNLISTED_ITEMS = 8
# 목록에 없는 물건의 이름 하나의 길이
UNLISTED_NAME_MAX_LENGTH = 60

# 이름표. 글자 하나와 숫자. 예: p1, i12, q3
Label = Annotated[str, StringConstraints(pattern=r'^[a-z][0-9]{1,3}$')]

# 모델이 답을 ```json … ``` 으로 감싸 오는 일이 잦다. 그 껍데기만 벗긴다
FENCE_PATTERN = re.compile(r'^\s*```(?:json)?\s*(.*?)\s*```\s*$', re.DOTALL)


class FoundItem(BaseModel):
    """캐릭터(character) 하나가 물건(item) 하나를 count 개 손에 넣었다는 초안."""

    model_config = ConfigDict(extra='forbid')

    character: Label
    item: Label
    count: int = Field(ge=1, le=ITEM_STACK_MAX)


class QuestChange(BaseModel):
    """퀘스트(quest) 하나의 상태가 status 가 됐다는 초안. 숨김으로 돌리는 초안은 없다."""

    model_config = ConfigDict(extra='forbid')

    quest: Label
    status: Literal['active', 'succeeded', 'failed']


# 목록에 없는 물건의 이름. 앞뒤 공백을 떼고 비지 않아야 한다
UnlistedName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=UNLISTED_NAME_MAX_LENGTH)
]


class DraftOutput(BaseModel):
    """
    모델의 답 전체. 모두 비어 있을 수 있다. 일어난 일이 없으면 빈 목록이 맞는 답이다.

    unlisted_items 는 장면에서 손에 넣었지만 목록에 없는 물건의 이름이다.
    초안이 되지 않는다(app/drafts/validation.py 가 보지 않는다).
    """

    model_config = ConfigDict(extra='forbid')

    found_items: list[FoundItem] = Field(default_factory=list, max_length=MAX_FOUND_ITEMS)
    quest_changes: list[QuestChange] = Field(default_factory=list, max_length=MAX_QUEST_CHANGES)
    unlisted_items: list[UnlistedName] = Field(default_factory=list, max_length=MAX_UNLISTED_ITEMS)


class OutputError(Exception):
    """모델의 답을 초안으로 읽지 못했다. reason 은 not_json(JSON 이 아니다) 또는 bad_shape(모양이 틀리다)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def strip_fence(text: str) -> str:
    """```json … ``` 껍데기가 있으면 벗긴다. 없으면 앞뒤 공백만 뗀다."""
    matched = FENCE_PATTERN.match(text)
    return matched.group(1) if matched else text.strip()


def read_output(text: str) -> DraftOutput:
    """
    모델의 글을 초안의 모양으로 읽는다.

    JSON 이 아니면 OutputError(not_json), 모양이 틀리면 OutputError(bad_shape).
    """
    try:
        document = json.loads(strip_fence(text))
    except json.JSONDecodeError as error:
        raise OutputError('not_json') from error
    try:
        return DraftOutput.model_validate(document)
    except ValidationError as error:
        raise OutputError('bad_shape') from error
