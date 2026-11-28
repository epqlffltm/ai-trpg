# shared/reference-core/src/reference_core/looks.py

"""
위키백과의 줄의 생김새 글 파일(reference_core/data/wikipedia.looks.json)을 읽고 줄에 붙인다.
DB 도 모델도 모르는 순수한 함수다.

생김새 글은 그것이 어떻게 생기고, 어떤 소리와 냄새가 나고, 무엇에 쓰는지를 한두 문장으로 적은 것이다.
벡터로 바꿀 글이 이름과 이것이다(reference_core/texts.py). 위키백과의 도입부는 사전식 정의라
("풀무는 바람을 일으키는 기구이다") 생김새로만 부르는 장면과 멀다. SRD 의 생김새 글과 같은 까닭이다.

SRD 와 다른 것.
  - 번역 파일이 아니라 따로 둔 파일이다. 한국어판의 줄은 번역이 없고(원본이 한국어다), 생김새 글은 한국어판과
    영어판의 줄 모두에 붙는다
  - look_ko 칸에만 넣는다. 글(content, content_ko)은 그대로다. 서술자에게 가는 글은 위키백과의 도입부 그대로다
생김새 글은 위키백과의 글이 아니라 이 프로젝트가 쓴 것이다(도입부와 일반적인 상식으로). 출처 표시의 "바꾼 것"에 적는다.
번역의 글과 같은 규칙(판정의 수치 없음, 300자)을 지킨다. 읽을 때 본다.
"""

from collections.abc import Iterable
from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from reference_core.records import DOCUMENT_FORMAT, REFERENCE_LOOK_MAX_LENGTH, ReferenceRecord, ReferenceSource
from reference_core.translations import MECHANICS_KO


def without_mechanics(value: str) -> str:
    """판정의 수치가 든 생김새 글은 받지 않는다(번역의 글과 같은 규칙)."""
    found = MECHANICS_KO.search(value)
    if found:
        raise ValueError(f'판정의 수치가 있다: {found.group()}')
    return value


# 줄 하나의 생김새 글. 비지 않고, 300자 이하다
Look = Annotated[
    str,
    StringConstraints(min_length=1, max_length=REFERENCE_LOOK_MAX_LENGTH, strip_whitespace=True),
    AfterValidator(without_mechanics),
]


class LooksDocument(BaseModel):
    """생김새 글 파일 하나. 자료 하나다. entries 는 key 에서 생김새 글로다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    format: int = Field(ge=DOCUMENT_FORMAT, le=DOCUMENT_FORMAT)
    source: ReferenceSource
    entries: dict[str, Look]


def read_looks(path: Path) -> LooksDocument:
    """생김새 글 파일을 읽어 검사한다. 모양이 틀리면 ValidationError 다."""
    return LooksDocument.model_validate_json(path.read_text(encoding='utf-8'))


def unknown_look_keys(records: Iterable[ReferenceRecord], looks: LooksDocument) -> list[str]:
    """자료에 없는 줄의 생김새 글. 제목을 지웠거나 오타다. 없으면 빈 목록이다."""
    keys = {record.key for record in records}
    return sorted(key for key in looks.entries if key not in keys)


def unlooked_keys(records: Iterable[ReferenceRecord], looks: LooksDocument) -> list[str]:
    """생김새 글이 없는 줄. 차례는 자료의 차례다."""
    return [record.key for record in records if record.key not in looks.entries]


def with_look(record: ReferenceRecord, looks: LooksDocument) -> ReferenceRecord:
    """줄 하나에 생김새 글을 붙인다. 없으면 그대로다. 글과 다른 이름은 바꾸지 않는다."""
    look = looks.entries.get(record.key)
    if look is None:
        return record
    return record.model_copy(update={'look_ko': look})


def apply_looks(records: Iterable[ReferenceRecord], looks: LooksDocument) -> list[ReferenceRecord]:
    """자료의 줄마다 생김새 글을 붙인다. 차례는 그대로다."""
    return [with_look(record, looks) for record in records]
