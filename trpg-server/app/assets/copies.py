# trpg-server/app/assets/copies.py

"""
바깥에서 복사해 온 줄(로어북 항목, 몬스터)의 모양. 자산 쪽은 어디서 왔는지(자료와 key)만 안다.

참고 자료(#482)를 고르고 옮기는 것은 app/references/copying.py 가 한다. 자산 쪽은 참고 자료를 모른다.
그래서 자산의 서비스는 이 모양만 받는다. 참고 자료가 아닌 다른 바깥 자료가 생겨도 같은 길로 들어온다.
"""

import uuid
from dataclasses import dataclass, field

from pydantic import BaseModel


@dataclass(frozen=True)
class Copy[Data]:
    """
    복사할 줄 하나. data 는 그 줄을 만들 입력(EntryCreate, MonsterCreate)이다.

    reference_id 는 고른 줄의 id 다. 이미 복사해 두어 건너뛴 줄을 알릴 때 쓴다.
    source, key 는 출처다. 같은 출처를 한 로어북(도감)에 두 번 넣지 않는다.
    """

    reference_id: uuid.UUID
    source: str
    key: str
    data: Data


@dataclass(frozen=True)
class CopyOutcome[Row]:
    """복사한 결과. created 는 새로 만든 행, skipped 는 이미 있어 건너뛴 줄의 reference_id 다."""

    created: list[Row] = field(default_factory=list)
    skipped: list[uuid.UUID] = field(default_factory=list)


class CopiedFrom(BaseModel):
    """복사한 줄의 출처. 응답에 싣는다. 화면이 출처 표시(SRD 는 CC BY 4.0)를 한다."""

    source: str
    key: str


def copied_from(source: str | None, key: str | None) -> CopiedFrom | None:
    """행의 출처 칸을 응답의 모양으로. 직접 쓴 행이면 None 이다."""
    if source is None or key is None:
        return None
    return CopiedFrom(source=source, key=key)


def split_copied[Data](
    copies: list[Copy[Data]], existing: set[tuple[str, str]]
) -> tuple[list[Copy[Data]], list[uuid.UUID]]:
    """이미 있는 출처를 뺀다. 새로 넣을 것과 건너뛸 것의 reference_id 다. 차례는 그대로다."""
    fresh = [copy for copy in copies if (copy.source, copy.key) not in existing]
    skipped = [copy.reference_id for copy in copies if (copy.source, copy.key) in existing]
    return fresh, skipped
