# trpg-server/app/references/records.py

"""
참고 자료의 한 줄(ReferenceRecord)과 데이터 파일의 모양(ReferenceDocument). DB 도 모델도 모르는 값들이다.

참고 자료는 미리 넣어 둔 바깥 자료다(#482). 제작자의 로어북과 달리 운영자가 관리 명령으로 넣는다.
  - 데이터 파일: 바깥 자료를 이 모양으로 옮긴 JSON 하나(data/references/). 저장소에 넣는다.
    넣는 결과가 늘 같고, 무엇을 넣었는지 리뷰할 수 있다. 원본의 출처와 판(커밋)을 함께 적는다.
  - 넣기(app/references/loading.py): 파일의 줄들을 DB 에 맞춘다. 같은 파일을 두 번 넣어도 같다.

한 줄의 칸.
  - key: 자료 안에서 그 줄을 가리키는 이름(monsters/aboleth). 다시 넣을 때 같은 줄을 찾는다.
  - kind: 종류(ReferenceKind).
  - name: 원본의 이름. aliases: 장면에서 부를 다른 이름(한국어 이름 등).
  - content: 서술자가 읽는 글. 수치(HP, 명중, 피해, 난이도)를 넣지 않는다. 판정은 엔진이 한다.
  - name_ko, content_ko: 한국어로 옮긴 이름과 글(번역 파일에서 온다, app/references/translations.py).
    있으면 서술과 복사(기본 자산)가 이것을 쓴다. 원본의 글과 같은 규칙(수치 없음, 1,000자)을 지킨다.
  - data: 원본의 수치를 정리한 것. 서술자에게 가지 않는다. 기본 자산(시트 채우기)에 쓴다.
"""

import enum
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# 데이터 파일의 형식 번호. 모양을 바꾸면 올리고 읽는 쪽이 옛 형식을 어떻게 다룰지 정한다
DOCUMENT_FORMAT = 1

REFERENCE_KEY_MAX_LENGTH = 100
REFERENCE_NAME_MAX_LENGTH = 100
# 서술자가 읽는 글의 상한. 로어북 항목(500자)보다 길다. 원본의 특성과 행동을 몇 개 담을 만큼이다
REFERENCE_CONTENT_MAX_LENGTH = 1000
REFERENCE_MAX_ALIASES = 5
REFERENCE_ALIAS_MAX_LENGTH = 30


class ReferenceSource(enum.StrEnum):
    """어느 자료인가. 자료마다 출처 표시와 라이선스가 다르다."""

    # System Reference Document 5.1. CC BY 4.0
    SRD51 = 'srd51'


class ReferenceKind(enum.StrEnum):
    """참고 자료 한 줄의 종류. 서술의 프롬프트가 종류를 붙여 보인다."""

    MONSTER = 'monster'
    ITEM = 'item'


Key = Annotated[str, StringConstraints(min_length=1, max_length=REFERENCE_KEY_MAX_LENGTH)]
Name = Annotated[str, StringConstraints(min_length=1, max_length=REFERENCE_NAME_MAX_LENGTH)]
Alias = Annotated[str, StringConstraints(min_length=1, max_length=REFERENCE_ALIAS_MAX_LENGTH)]
Content = Annotated[str, StringConstraints(max_length=REFERENCE_CONTENT_MAX_LENGTH)]


class ReferenceRecord(BaseModel):
    """참고 자료 한 줄. 데이터 파일의 entries 하나다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    key: Key
    kind: ReferenceKind
    name: Name
    aliases: list[Alias] = Field(default_factory=list, max_length=REFERENCE_MAX_ALIASES)
    content: Content = ''
    data: dict[str, Any] = Field(default_factory=dict)
    name_ko: Annotated[str, StringConstraints(max_length=REFERENCE_NAME_MAX_LENGTH)] = ''
    content_ko: Content = ''


class ReferenceOrigin(BaseModel):
    """데이터 파일을 무엇에서 만들었나. 같은 원본으로 다시 만들 수 있게 적는다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    dataset: str
    revision: str
    license: str
    attribution: str
    # 원본을 어떻게 바꿨나(CC BY 4.0 은 바꾼 것을 밝히게 한다). 바꾸지 않았으면 비어 있다
    changes: str = ''


class ReferenceDocument(BaseModel):
    """데이터 파일 하나. 자료 하나의 줄 전부다. key 는 겹치지 않는다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    format: int = Field(ge=DOCUMENT_FORMAT, le=DOCUMENT_FORMAT)
    source: ReferenceSource
    origin: ReferenceOrigin
    entries: list[ReferenceRecord]

    def model_post_init(self, context: Any, /) -> None:
        """key 가 겹치면 받지 않는다. 다시 넣을 때 어느 줄인지 알 수 없다."""
        keys = [record.key for record in self.entries]
        duplicated = sorted({key for key in keys if keys.count(key) > 1})
        if duplicated:
            raise ValueError(f'겹치는 key 가 있다: {", ".join(duplicated[:5])}')


def read_document(path: Path) -> ReferenceDocument:
    """데이터 파일을 읽어 검사한다. 모양이 틀리면 ValidationError 다."""
    return ReferenceDocument.model_validate_json(path.read_text(encoding='utf-8'))


def write_document(document: ReferenceDocument, path: Path) -> None:
    """
    데이터 파일을 쓴다. 한 줄에 한 항목이다.

    줄마다 나눠 두면 원본이 바뀌어 다시 만들었을 때 바뀐 항목만 diff 에 보인다.
    키의 차례를 정해 같은 내용이면 같은 글이다.
    """
    head = document.model_dump(mode='json', exclude={'entries'})
    records = [record.model_dump(mode='json') for record in document.entries]
    lines = [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]
    body = ',\n'.join(f'    {line}' for line in lines)
    # 들여 쓴 JSON 은 늘 "\n}" 로 끝난다. 그 앞에 entries 를 잇는다
    head_text = json.dumps(head, ensure_ascii=False, sort_keys=True, indent=2).removesuffix('\n}')
    path.write_text(f'{head_text},\n  "entries": [\n{body}\n  ]\n}}\n', encoding='utf-8')


@dataclass(frozen=True)
class StoredReference:
    """DB 에 든 참고 자료 한 줄. 저장소(repository)가 돌려준다. 넣기가 파일의 줄과 견주고, 색인이 글을 만든다."""

    id: uuid.UUID
    key: str
    name: str
    aliases: list[str] = field(default_factory=list)
    content: str = ''
    kind: str = ReferenceKind.ITEM
    data: dict[str, Any] = field(default_factory=dict)
    name_ko: str = ''
    content_ko: str = ''

    @property
    def shown_name(self) -> str:
        """서술과 복사에 쓰는 이름. 한국어 이름이 있으면 그것, 없으면 원본의 이름이다."""
        return self.name_ko or self.name

    @property
    def shown_content(self) -> str:
        """서술과 복사에 쓰는 글. 한국어 글이 있으면 그것, 없으면 원본의 글이다."""
        return self.content_ko or self.content

    def matches(self, record: ReferenceRecord) -> bool:
        """파일의 줄과 값이 모두 같은가(key 는 같다고 본다)."""
        mine = (self.kind, self.name, self.aliases, self.content, self.data, self.name_ko, self.content_ko)
        return mine == (
            record.kind,
            record.name,
            record.aliases,
            record.content,
            record.data,
            record.name_ko,
            record.content_ko,
        )
