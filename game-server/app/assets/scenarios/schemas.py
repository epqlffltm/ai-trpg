# game-server/app/assets/scenarios/schemas.py

"""
시나리오 API 가 받는 입력과 내보내는 응답의 모양. 공통 모양(app/assets/schemas.py)에 시나리오의 칸을 더한다.
"""

import uuid
from datetime import datetime
from typing import Annotated, ClassVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.assets.models import SCENARIO_MAX_LOREBOOKS, SCENARIO_OPENING_MAX_LENGTH, VERSION_NOTE_MAX_LENGTH
from app.assets.scenarios.snapshot import Snapshot
from app.assets.schemas import AssetCreate, AssetSummary, AssetUpdate

Opening = Annotated[str, StringConstraints(max_length=SCENARIO_OPENING_MAX_LENGTH)]


def reject_duplicates(lorebook_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """같은 로어북이 두 번 있으면 거부한다."""
    if len(set(lorebook_ids)) != len(lorebook_ids):
        raise ValueError('같은 로어북이 두 번 있습니다.')
    return lorebook_ids


LorebookIds = Annotated[list[uuid.UUID], Field(max_length=SCENARIO_MAX_LOREBOOKS), AfterValidator(reject_duplicates)]


class ScenarioCreate(AssetCreate):
    """
    시나리오를 만들 때 받는 값. 제목만 필수다.

    룰북 없이도 만들 수 있다(임시 저장). 게시할 때 룰북이 있는지 검사한다.
    """

    rulebook_id: uuid.UUID | None = None
    world_id: uuid.UUID | None = None
    lorebook_ids: LorebookIds = []
    opening: Opening = ''


class ScenarioUpdate(AssetUpdate):
    """
    시나리오를 고칠 때 받는 값. 보낸 칸만 바꾼다.

    rulebook_id 와 world_id 는 null 을 보내면 떼어 낸다. 보내지 않으면 그대로 둔다.
    lorebook_ids 는 보낸 목록으로 통째로 바꾼다. 전부 떼려면 빈 목록을 보낸다.
    """

    clearable: ClassVar[frozenset[str]] = frozenset({'rulebook_id', 'world_id'})

    rulebook_id: uuid.UUID | None = None
    world_id: uuid.UUID | None = None
    lorebook_ids: LorebookIds | None = None
    opening: Opening | None = None


class ScenarioDetail(AssetSummary):
    """만든 사람이 자기 시나리오를 볼 때의 값. 가리키는 자산은 ID 만 싣는다. 내용은 그 자산의 주소에서 읽는다."""

    rulebook_id: uuid.UUID | None
    world_id: uuid.UUID | None
    lorebook_ids: list[uuid.UUID]
    opening: str


VersionNote = Annotated[str, StringConstraints(max_length=VERSION_NOTE_MAX_LENGTH)]


class VersionCreate(BaseModel):
    """
    게시할 때 받는 값. 변경 내용만 적는다. 비워도 된다.

    판의 내용은 받지 않는다. 서버가 초안에서 직접 읽어 굳힌다.
    """

    model_config = ConfigDict(extra='forbid')

    note: VersionNote = ''


class VersionSummary(BaseModel):
    """판의 목록에 싣는 값. 굳힌 내용은 싣지 않는다."""

    id: uuid.UUID
    number: int
    note: str
    created_at: datetime


class VersionDetail(VersionSummary):
    """만든 사람이 자기 판을 볼 때의 값. 굳힌 내용까지 싣는다. GM 전용 글이 들어 있다."""

    snapshot: Snapshot
