# trpg-server/app/references/schemas.py

"""
참고 자료 API(찾기, 복사)가 받는 입력과 내보내는 응답의 모양(#482 4단계).
"""

import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.assets.bestiaries.schemas import MonsterDetail
from app.assets.copies import CopiedFrom
from app.assets.lorebooks.schemas import EntryDetail
from app.assets.scenarios.schemas import MonsterSheet
from app.references.records import ReferenceKind

# 한 번에 복사할 수 있는 줄의 수. 로어북과 도감의 상한(100)보다 작게, 화면에서 한 번에 고를 만큼이다
COPY_MAX_REFERENCES = 20
# 찾는 글의 길이
SEARCH_TEXT_MAX_LENGTH = 50


def without_repeats(ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """같은 id 를 두 번 보내면 한 번으로 친다. 차례는 처음 나온 대로다."""
    return list(dict.fromkeys(ids))


class ReferenceItem(BaseModel):
    """
    참고 자료 한 줄. 고르는 화면이 보인다.

    name 과 content 는 보이는 것(한국어로 옮긴 것, 없으면 원본)이다. original_name 은 원본의 이름이다.
    원본의 수치(data)는 싣지 않는다.
    """

    id: uuid.UUID
    source: str
    key: str
    kind: ReferenceKind
    name: str
    original_name: str
    content: str


class ReferencePage(BaseModel):
    """
    찾은 줄들의 한 쪽.

    attributions 는 이 쪽의 줄들이 나온 자료의 출처 표시다. 화면이 함께 보인다(SRD 5.1 은 CC BY 4.0 이다).
    """

    items: list[ReferenceItem]
    total: int
    attributions: list[str]


class ReferenceCopy(BaseModel):
    """복사할 줄들. 고른 차례대로 넣는다."""

    model_config = ConfigDict(extra='forbid')

    reference_ids: Annotated[
        list[uuid.UUID], Field(min_length=1, max_length=COPY_MAX_REFERENCES), AfterValidator(without_repeats)
    ]


class LoreCopyResult(BaseModel):
    """로어북으로 복사한 결과. skipped 는 이미 복사해 두어 건너뛴 줄의 id 다."""

    created: list[EntryDetail]
    skipped: list[uuid.UUID]


class MonsterCopyResult(BaseModel):
    """도감으로 복사한 결과. skipped 는 이미 복사해 두어 건너뛴 줄의 id 다."""

    created: list[MonsterDetail]
    skipped: list[uuid.UUID]


class MonsterSheetProposal(BaseModel):
    """
    몬스터 시트의 제안. 저장하지 않는다. sheet 는 시나리오의 monster_sheets 에 그대로 넣을 수 있는 모양이다.

    notes 는 원본과 다르게 옮긴 것들이다(범위에 맞춘 점수, 옮기지 않은 행동). 제작자가 읽고 고친다.
    copied_from 은 수치를 가져온 참고 자료다.
    """

    sheet: MonsterSheet
    notes: list[str]
    copied_from: CopiedFrom
