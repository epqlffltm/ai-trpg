# trpg-server/app/references/translations.py

"""
참고 자료의 한국어 번역 파일(data/references/srd51.ko.json)을 읽고 자료의 줄에 붙인다.
DB 도 모델도 모르는 순수한 함수다.

번역은 미리 해서 저장소에 넣는다(2026-10-21 유저 결정). 넣는 결과가 늘 같고 리뷰할 수 있다.
복사할 때마다 모델에게 옮기게 하면 값이 들고, 결과가 매번 다르고, 틀린 번역을 막기 어렵다.

붙이는 것.
  - name_ko, content_ko: 번역한 이름과 글. 서술과 복사(기본 자산)가 이것을 쓴다.
  - aliases: 한국어 이름을 다른 이름으로 더한다. 한국어 장면에 그 이름이 나오면 고른다(app/references/retrieval.py).
번역의 글도 원본의 글과 같은 규칙(수치 없음, 1,000자)을 지킨다. 번역 파일을 읽을 때 본다.
번역이 없는 줄은 그대로다(영어로 쓴다).
"""

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.references.records import (
    DOCUMENT_FORMAT,
    REFERENCE_ALIAS_MAX_LENGTH,
    REFERENCE_CONTENT_MAX_LENGTH,
    ReferenceRecord,
    ReferenceSource,
)

# 번역의 글에 있으면 안 되는 판정의 수치와 낱말. 원본의 글을 거르는 것(app/references/srd.py)과 같은 뜻이다
# 주사위를 굴리는 말("6면체 주사위", "주사위를 굴린다")과 주사위의 눈("6이 나오면")도 뺀다
MECHANICS_KO = re.compile(
    r'\bDC\b|\b\d*d\d+\b|[+-]\d+\b|난이도\s*\d+|명중\s*[+-]?\d+|내성 굴림|피해 굴림'
    r'|면체 주사위|주사위를[^.]*굴|\d+\s*[이가]\s*나오면',
    re.IGNORECASE,
)


class Translation(BaseModel):
    """줄 하나의 번역. 이름은 다른 이름(aliases)으로도 쓰여서 그 길이(30자)를 넘지 않는다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    name: Annotated[str, StringConstraints(min_length=1, max_length=REFERENCE_ALIAS_MAX_LENGTH, strip_whitespace=True)]
    content: Annotated[str, StringConstraints(max_length=REFERENCE_CONTENT_MAX_LENGTH)] = ''

    @field_validator('content')
    @classmethod
    def without_mechanics(cls, value: str) -> str:
        """판정의 수치가 든 번역은 받지 않는다. 원본에서 뺀 것이 번역에서 되살아나면 안 된다."""
        found = MECHANICS_KO.search(value)
        if found:
            raise ValueError(f'판정의 수치가 있다: {found.group()}')
        return value


class TranslationDocument(BaseModel):
    """번역 파일 하나. 자료 하나의 한 언어다. entries 는 key 에서 번역으로다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    format: int = Field(ge=DOCUMENT_FORMAT, le=DOCUMENT_FORMAT)
    source: ReferenceSource
    language: str = Field(pattern=r'^[a-z]{2}$')
    entries: dict[str, Translation]


def read_translations(path: Path) -> TranslationDocument:
    """번역 파일을 읽어 검사한다. 모양이 틀리면 ValidationError 다."""
    return TranslationDocument.model_validate_json(path.read_text(encoding='utf-8'))


def unknown_keys(records: Iterable[ReferenceRecord], translations: TranslationDocument) -> list[str]:
    """자료에 없는 줄의 번역. 원본이 바뀌어 빠진 줄이거나 오타다. 없으면 빈 목록이다."""
    keys = {record.key for record in records}
    return sorted(key for key in translations.entries if key not in keys)


def translated(record: ReferenceRecord, translation: Translation | None) -> ReferenceRecord:
    """
    줄 하나에 번역을 붙인다. 번역이 없으면 그대로다.

    한국어 이름을 다른 이름의 맨 앞에 더한다(이미 있으면 더하지 않는다). 원본의 이름과 같으면 더하지 않는다.
    """
    if translation is None:
        return record
    aliases = list(record.aliases)
    if translation.name != record.name and translation.name not in aliases:
        aliases = [translation.name, *aliases]
    return record.model_copy(
        update={'name_ko': translation.name, 'content_ko': translation.content, 'aliases': aliases}
    )


def apply_translations(records: Iterable[ReferenceRecord], translations: TranslationDocument) -> list[ReferenceRecord]:
    """자료의 줄마다 번역을 붙인다. 차례는 그대로다."""
    return [translated(record, translations.entries.get(record.key)) for record in records]
