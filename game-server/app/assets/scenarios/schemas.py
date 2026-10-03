# game-server/app/assets/scenarios/schemas.py

"""
시나리오 API 가 받는 입력과 내보내는 응답의 모양. 공통 모양(app/assets/schemas.py)에 시나리오의 칸을 더한다.
"""

import uuid
from typing import Annotated, ClassVar

from pydantic import StringConstraints

from app.assets.models import SCENARIO_OPENING_MAX_LENGTH
from app.assets.schemas import AssetCreate, AssetSummary, AssetUpdate

Opening = Annotated[str, StringConstraints(max_length=SCENARIO_OPENING_MAX_LENGTH)]


class ScenarioCreate(AssetCreate):
    """
    시나리오를 만들 때 받는 값. 제목만 필수다.

    룰북 없이도 만들 수 있다(임시 저장). 게시할 때 룰북이 있는지 검사한다.
    """

    rulebook_id: uuid.UUID | None = None
    world_id: uuid.UUID | None = None
    opening: Opening = ''


class ScenarioUpdate(AssetUpdate):
    """
    시나리오를 고칠 때 받는 값. 보낸 칸만 바꾼다.

    rulebook_id 와 world_id 는 null 을 보내면 떼어 낸다. 보내지 않으면 그대로 둔다.
    """

    clearable: ClassVar[frozenset[str]] = frozenset({'rulebook_id', 'world_id'})

    rulebook_id: uuid.UUID | None = None
    world_id: uuid.UUID | None = None
    opening: Opening | None = None


class ScenarioDetail(AssetSummary):
    """만든 사람이 자기 시나리오를 볼 때의 값. 가리키는 자산은 ID 만 싣는다. 내용은 그 자산의 주소에서 읽는다."""

    rulebook_id: uuid.UUID | None
    world_id: uuid.UUID | None
    opening: str
