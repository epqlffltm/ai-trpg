# shared/reference-core/src/reference_core/wiki_build.py

"""
제목 목록으로 위키백과의 문서를 받아 데이터 파일(data/wikipedia.json)을 쓴다.
개발자의 명령(trpg-server 의 scripts/build_wiki.py)이 부른다.

받는 것(HTTP)은 넘겨받는다(fetch). 이 파일은 차례와 규칙만 안다. 그래서 시험은 네트워크를 쓰지 않는다.
  1. 목록의 한국어 제목을 한국어판에 묻는다(20개씩)
  2. 한국어판에 없거나(없음, 동음이의어, 빈 도입부) 거르고 남은 글이 없으면 영어 제목을 영어판에 묻는다
  3. 둘 다 안 되면 건너뛰고 알린다(BuildReport)
줄의 모양(trpg-server/README.md 의 "위키백과").
  - key: "<언어>/<받은 제목>"(ko/범선, en/Carrack). 넘겨주기를 따라간 뒤의 제목이다
  - kind: topic. name: 받은 제목. aliases: 한국어 이름이 맨 앞, 그다음 한국어판의 받은 제목(넘겨주기로 바뀐 이름,
    "갤리온" 이 "갈레온" 으로), 목록에 적은 다른 이름
  - content: 도입부에서 거르고 남은 글(reference_core/wiki.py)
  - name_ko: 영어판의 줄이면 목록의 한국어 이름. 한국어판의 줄은 비운다(원본이 한국어다)
  - content_ko: 한국어판의 줄은 비운다. 영어판의 줄은 번역 파일(data/wikipedia.ko.json)이 있으면 그것으로 채운다
번역 파일은 영어판의 줄만 옮긴다(reference_core/translations.py, SRD 와 같은 모양). 번역이 없는 영어판의 줄과,
지금 자료에 없는 줄의 번역(한국어판으로 바뀌었거나 제목을 지웠다)은 알린다. 멈추지는 않는다.
  - look_ko: 생김새 글 파일(data/wikipedia.looks.json)이 있으면 모든 줄에 붙인다(reference_core/looks.py).
    생김새 글이 없는 줄과 자료에 없는 줄의 생김새 글은 번역과 같이 알린다
  - data: lang, page_id, revision_id(받은 판), url(원문). 서술자에게 가지 않는다
같은 문서에 닿은 두 제목은 앞의 것만 넣는다. 다시 만들면 그때의 판을 받는다(revision_id 가 바뀐 줄만 diff 에 보인다).
"""

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reference_core.looks import LooksDocument, apply_looks, read_looks, unknown_look_keys, unlooked_keys
from reference_core.records import (
    DOCUMENT_FORMAT,
    REFERENCE_KEY_MAX_LENGTH,
    REFERENCE_NAME_MAX_LENGTH,
    ReferenceDocument,
    ReferenceKind,
    ReferenceOrigin,
    ReferenceRecord,
    ReferenceSource,
    read_document,
    write_document,
)
from reference_core.translations import TranslationDocument, apply_translations, read_translations, unknown_keys
from reference_core.wiki import WIKIPEDIA_ATTRIBUTION, lead_content, places_pattern, read_places, wiki_changes
from reference_core.wiki_api import WikiPage, batches, pages_of
from reference_core.wiki_titles import WikiTitle, read_titles, without_disambiguation

# 데이터 파일의 원본 이름
WIKIPEDIA_DATASET = 'Wikipedia (Korean and English editions)'
WIKIPEDIA_LICENSE = 'CC-BY-SA-4.0'

# 언어판과 제목들을 받아 API 의 답(JSON)을 돌려주는 것. 부르는 쪽이 HTTP 로 보낸다
type Fetch = Callable[[str, list[str]], Mapping[str, Any]]


@dataclass
class BuildReport:
    """
    만든 결과. english 는 영어판으로 받은 한국어 제목, missing 은 둘 다 없던 것, emptied 는 거르고 남은 글이 없던 것,
    duplicated 는 앞의 제목과 같은 문서에 닿은 것이다.
    """

    written: int = 0
    english: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    emptied: list[str] = field(default_factory=list)
    duplicated: list[str] = field(default_factory=list)
    # 번역이 없는 영어판의 줄(key)과, 자료에 없는 줄의 번역(key)
    untranslated: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    # 생김새 글이 없는 줄(key)과, 자료에 없는 줄의 생김새 글(key)
    unlooked: list[str] = field(default_factory=list)
    stale_looks: list[str] = field(default_factory=list)


def fetch_pages(fetch: Fetch, lang: str, titles: Sequence[str]) -> dict[str, WikiPage]:
    """제목들을 묶음마다 물어 받은 문서들. 물은 제목 → 문서다."""
    pages: dict[str, WikiPage] = {}
    for batch in batches(list(dict.fromkeys(titles))):
        pages.update(pages_of(lang, batch, fetch(lang, batch)))
    return pages


def record_of(title: WikiTitle, page: WikiPage, places: re.Pattern[str]) -> ReferenceRecord | None:
    """받은 문서로 만든 줄. 거르고 남은 글이 없거나 제목이 key·이름의 길이를 넘으면 None 이다."""
    content = lead_content(page.extract, places)
    key = f'{page.lang}/{page.title}'
    if content is None or len(key) > REFERENCE_KEY_MAX_LENGTH or len(page.title) > REFERENCE_NAME_MAX_LENGTH:
        return None
    return ReferenceRecord(
        key=key,
        kind=ReferenceKind.TOPIC,
        name=page.title,
        aliases=title.names([without_disambiguation(page.title)] if page.lang == 'ko' else []),
        content=content,
        name_ko='' if page.lang == 'ko' else title.korean_name,
        data={'lang': page.lang, 'page_id': page.page_id, 'revision_id': page.revision_id, 'url': page.url},
    )


def from_korean(
    titles: Sequence[WikiTitle], pages: Mapping[str, WikiPage], places: re.Pattern[str]
) -> tuple[list[tuple[WikiTitle, ReferenceRecord]], list[WikiTitle]]:
    """한국어판으로 만든 줄들과, 한국어판으로 만들지 못해 영어판을 볼 제목들."""
    made: list[tuple[WikiTitle, ReferenceRecord]] = []
    left: list[WikiTitle] = []
    for title in titles:
        page = pages.get(title.ko)
        record = record_of(title, page, places) if page is not None else None
        if record is None:
            left.append(title)
        else:
            made.append((title, record))
    return made, left


def from_english(
    titles: Sequence[WikiTitle], pages: Mapping[str, WikiPage], places: re.Pattern[str], report: BuildReport
) -> list[tuple[WikiTitle, ReferenceRecord]]:
    """영어판으로 만든 줄들. 만들지 못한 제목은 알림에 적는다(문서가 없음, 남은 글이 없음)."""
    made: list[tuple[WikiTitle, ReferenceRecord]] = []
    for title in titles:
        page = pages.get(title.en) if title.en else None
        record = record_of(title, page, places) if page is not None else None
        if record is not None:
            made.append((title, record))
            report.english.append(title.ko)
        elif page is not None:
            report.emptied.append(title.ko)
        else:
            report.missing.append(title.ko)
    return made


def unique_records(made: Sequence[tuple[WikiTitle, ReferenceRecord]], report: BuildReport) -> list[ReferenceRecord]:
    """key 가 겹치면(두 제목이 같은 문서에 닿았다) 앞의 것만 둔다. 뒤의 제목은 알림에 적는다."""
    records: dict[str, ReferenceRecord] = {}
    for title, record in made:
        if record.key in records:
            report.duplicated.append(title.ko)
        else:
            records[record.key] = record
    return list(records.values())


def collect(
    titles: Sequence[WikiTitle], fetch: Fetch, places: re.Pattern[str]
) -> tuple[list[ReferenceRecord], BuildReport]:
    """목록의 차례대로 줄을 만든다. 한국어판 먼저, 없으면 영어판이다."""
    report = BuildReport()
    korean, left = from_korean(titles, fetch_pages(fetch, 'ko', [title.ko for title in titles]), places)
    english = from_english(left, fetch_pages(fetch, 'en', [title.en for title in left if title.en]), places, report)
    by_title = {title.ko: (title, record) for title, record in [*korean, *english]}
    records = unique_records([by_title[title.ko] for title in titles if title.ko in by_title], report)
    report.written = len(records)
    return records, report


def with_translations(
    records: list[ReferenceRecord], translations: TranslationDocument, report: BuildReport
) -> list[ReferenceRecord]:
    """번역을 붙인다. 번역이 없는 영어판의 줄과 자료에 없는 줄의 번역을 알림에 적는다."""
    if translations.source != ReferenceSource.WIKIPEDIA:
        raise ValueError(f'위키백과의 번역 파일이 아니다: {translations.source}')
    report.stale = unknown_keys(records, translations)
    translated = apply_translations(records, translations)
    report.untranslated = [
        record.key for record in translated if record.data.get('lang') != 'ko' and not record.content_ko
    ]
    return translated


def with_looks(records: list[ReferenceRecord], looks: LooksDocument, report: BuildReport) -> list[ReferenceRecord]:
    """생김새 글을 붙인다. 생김새 글이 없는 줄과 자료에 없는 줄의 생김새 글을 알림에 적는다."""
    if looks.source != ReferenceSource.WIKIPEDIA:
        raise ValueError(f'위키백과의 생김새 글 파일이 아니다: {looks.source}')
    report.unlooked = unlooked_keys(records, looks)
    report.stale_looks = unknown_look_keys(records, looks)
    return apply_looks(records, looks)


def wiki_document(records: list[ReferenceRecord], revision: str) -> ReferenceDocument:
    """위키백과의 줄들을 데이터 파일 하나로. revision 은 받은 날(YYYY-MM-DD)이다. 줄마다의 판은 data 에 있다."""
    origin = ReferenceOrigin(
        dataset=WIKIPEDIA_DATASET,
        revision=revision,
        license=WIKIPEDIA_LICENSE,
        attribution=WIKIPEDIA_ATTRIBUTION,
        changes=wiki_changes(records),
    )
    return ReferenceDocument(format=DOCUMENT_FORMAT, source=ReferenceSource.WIKIPEDIA, origin=origin, entries=records)


def build(
    titles: Path,
    places: Path,
    output: Path,
    fetch: Fetch,
    revision: str,
    translation: Path | None = None,
    looks: Path | None = None,
) -> BuildReport:
    """
    제목 목록과 거를 이름의 목록으로 데이터 파일을 쓴다. 번역 파일과 생김새 글 파일이 있으면 붙인다.
    만든 결과를 돌려준다.
    """
    records, report = collect(read_titles(titles), fetch, places_pattern(read_places(places)))
    if translation is not None and translation.exists():
        records = with_translations(records, read_translations(translation), report)
    if looks is not None and looks.exists():
        records = with_looks(records, read_looks(looks), report)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_document(wiki_document(records, revision), output)
    return report


def refresh_looks(output: Path, looks: Path) -> BuildReport:
    """
    이미 만든 데이터 파일에 생김새 글만 다시 붙인다. 위키백과에 묻지 않는다.
    생김새 글을 고쳤을 때 쓴다. 다시 받으면 모든 줄의 판이 바뀌어 diff 가 커진다. 받은 날(revision)은 그대로다.
    """
    document = read_document(output)
    english = [record.name_ko or record.name for record in document.entries if record.data.get('lang') != 'ko']
    report = BuildReport(written=len(document.entries), english=english)
    records = with_looks(list(document.entries), read_looks(looks), report)
    write_document(wiki_document(records, document.origin.revision), output)
    return report
