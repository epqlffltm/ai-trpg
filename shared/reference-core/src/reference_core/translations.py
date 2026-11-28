# shared/reference-core/src/reference_core/translations.py

"""
참고 자료의 한국어 번역 파일(reference_core/data/srd51.ko.json)을 읽고 자료의 줄에 붙인다.
DB 도 모델도 모르는 순수한 함수다.

번역은 미리 해서 저장소에 넣는다(2026-10-21 유저 결정). 넣는 결과가 늘 같고 리뷰할 수 있다.
복사할 때마다 모델에게 옮기게 하면 값이 들고, 결과가 매번 다르고, 틀린 번역을 막기 어렵다.

붙이는 것.
  - name_ko, content_ko: 번역한 이름과 글. 서술과 복사(기본 자산)가 이것을 쓴다.
    생김새 글(look)이 있으면 글의 맨 앞에 붙인다. SRD 의 글은 규칙의 요약이라("중형 괴물류, 이동: 걷기 …")
    생김새로만 부르는 장면("뚜껑이 숨 쉬듯 움직이는 상자")과 멀다. 벡터도 서술도 이 글을 쓴다.
    생김새 글은 SRD 의 글이 아니라 이 프로젝트가 쓴 것이다(SRD 의 특성과 일반적인 판타지의 상식으로).
    SRD 가 아닌 책(몬스터 매뉴얼 등)의 설명을 옮기지 않는다.
  - aliases: 한국어 이름과, 번역에 적은 다른 한국어 이름(aliases)을 다른 이름으로 더한다.
    한국어 장면에 그 이름이 나오면 고른다(reference_core/selection.py).
    다른 한국어 이름은 장면에서 흔히 부르는 말이 번역한 이름과 다를 때 적는다("스켈레톤" 에 "해골 병사").
번역의 글도 원본의 글과 같은 규칙(수치 없음, 1,000자)을 지킨다. 번역 파일을 읽을 때 본다.
번역이 없는 줄은 그대로다(영어로 쓴다).
"""

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from reference_core.records import (
    DOCUMENT_FORMAT,
    REFERENCE_ALIAS_MAX_LENGTH,
    REFERENCE_CONTENT_MAX_LENGTH,
    REFERENCE_LOOK_MAX_LENGTH,
    REFERENCE_MAX_ALIASES,
    ReferenceRecord,
    ReferenceSource,
)

# 번역의 글에 있으면 안 되는 판정의 수치와 낱말. 원본의 글을 거르는 것(reference_core/srd.py)과 같은 뜻이다
# 주사위를 굴리는 말("6면체 주사위", "주사위를 굴린다")과 주사위의 눈("6이 나오면")도 뺀다
MECHANICS_KO = re.compile(
    r'\bDC\b|\b\d*d\d+\b|[+-]\d+\b|난이도\s*\d+|명중\s*[+-]?\d+|내성 굴림|피해 굴림'
    r'|면체 주사위|주사위를[^.]*굴|\d+\s*[이가]\s*나오면',
    re.IGNORECASE,
)


# 생김새 글의 글자 수의 상한. 한두 문장이다. 번역의 글과 합쳐 줄의 글(1,000자) 안에 든다
LOOK_MAX_LENGTH = REFERENCE_LOOK_MAX_LENGTH

# 번역의 이름과 다른 한국어 이름 하나
KoreanName = Annotated[
    str, StringConstraints(min_length=1, max_length=REFERENCE_ALIAS_MAX_LENGTH, strip_whitespace=True)
]


class Translation(BaseModel):
    """
    줄 하나의 번역. 이름과 다른 한국어 이름(aliases)은 줄의 다른 이름으로 쓰여서 그 길이(30자)를 넘지 않는다.
    다른 한국어 이름은 이름과 합쳐 다른 이름의 상한(5개) 안이다.
    생김새 글(look)은 글(content)의 앞에 붙는다. 둘을 합쳐 줄의 글의 상한(1,000자) 안이다.
    """

    model_config = ConfigDict(extra='forbid', frozen=True)

    name: KoreanName
    aliases: list[KoreanName] = Field(default_factory=list, max_length=REFERENCE_MAX_ALIASES - 1)
    content: Annotated[str, StringConstraints(max_length=REFERENCE_CONTENT_MAX_LENGTH)] = ''
    look: Annotated[str, StringConstraints(max_length=LOOK_MAX_LENGTH, strip_whitespace=True)] = ''

    @field_validator('content', 'look')
    @classmethod
    def without_mechanics(cls, value: str) -> str:
        """판정의 수치가 든 번역은 받지 않는다. 원본에서 뺀 것이 번역에서 되살아나면 안 된다."""
        found = MECHANICS_KO.search(value)
        if found:
            raise ValueError(f'판정의 수치가 있다: {found.group()}')
        return value

    @model_validator(mode='after')
    def within_content_length(self) -> 'Translation':
        """생김새 글과 글을 합친 것이 줄의 글의 상한을 넘지 않는다."""
        if len(korean_content(self)) > REFERENCE_CONTENT_MAX_LENGTH:
            raise ValueError(f'생김새 글과 글을 합쳐 {REFERENCE_CONTENT_MAX_LENGTH}자를 넘는다')
        return self


class TranslationDocument(BaseModel):
    """번역 파일 하나. 자료 하나의 한 언어다. entries 는 key 에서 번역으로다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    format: int = Field(ge=DOCUMENT_FORMAT, le=DOCUMENT_FORMAT)
    source: ReferenceSource
    language: str = Field(pattern=r'^[a-z]{2}$')
    entries: dict[str, Translation]


def korean_content(translation: Translation) -> str:
    """줄의 한국어 글. 생김새 글이 있으면 그것이 맨 앞이고, 그다음 번역의 글이다."""
    return ' '.join(part for part in (translation.look, translation.content) if part)


def described(translations: TranslationDocument) -> bool:
    """생김새 글이 든 번역이 하나라도 있는가. 출처 표시의 "바꾼 것"에 적는다(reference_core/srd.py)."""
    return any(translation.look for translation in translations.entries.values())


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

    한국어 이름과 다른 한국어 이름을 다른 이름의 앞에 더한다. 이미 있는 것과 원본의 이름과 같은 것은 더하지 않는다.
    원본의 다른 이름이 그 뒤다. 다섯을 넘으면 뒤의 것을 뺀다.
    """
    if translation is None:
        return record
    return record.model_copy(
        update={
            'name_ko': translation.name,
            'content_ko': korean_content(translation),
            'look_ko': translation.look,
            'aliases': merged_aliases(record, translation),
        }
    )


def merged_aliases(record: ReferenceRecord, translation: Translation) -> list[str]:
    """번역을 붙인 줄의 다른 이름. 새로 더한 한국어 이름, 다른 한국어 이름, 그다음 원본의 다른 이름의 차례다."""
    added: list[str] = []
    for name in (translation.name, *translation.aliases):
        if name != record.name and name not in record.aliases and name not in added:
            added.append(name)
    return [*added, *record.aliases][:REFERENCE_MAX_ALIASES]


def apply_translations(records: Iterable[ReferenceRecord], translations: TranslationDocument) -> list[ReferenceRecord]:
    """자료의 줄마다 번역을 붙인다. 차례는 그대로다."""
    return [translated(record, translations.entries.get(record.key)) for record in records]
