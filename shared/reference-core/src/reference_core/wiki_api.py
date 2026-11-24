# shared/reference-core/src/reference_core/wiki_api.py

"""
MediaWiki API(위키백과)에 보낼 물음과 그 답을 읽는 것. HTTP 는 모른다(보내는 것은 부르는 쪽의 일이다).

덤프가 아니라 API 로 받는다. 고른 제목 수백 개라 덤프(수 GB, 위키 문법을 다 풀어야 한다)보다 맞다.
한 번에 제목 BATCH_SIZE 개를 묻는다(도입부를 받는 extracts 가 한 번에 주는 수의 상한이 20 이다).

    action=query, prop=extracts|revisions|info|pageprops, exintro, explaintext, redirects, formatversion=2

  - extracts: 도입부를 평문으로(위키 문법이 없다)
  - revisions: 지금 판의 번호(받은 판을 줄에 적는다)
  - info: 원문의 주소(fullurl)
  - pageprops: 동음이의어 문서인지(disambiguation). 그런 문서는 없는 것으로 본다
  - redirects: 넘겨주기를 따라간다. 받은 줄의 제목은 따라간 뒤의 제목이다
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# 한 번에 묻는 제목의 수
BATCH_SIZE = 20
# 언어판마다의 API 주소
API_URLS = {'ko': 'https://ko.wikipedia.org/w/api.php', 'en': 'https://en.wikipedia.org/w/api.php'}


@dataclass(frozen=True)
class WikiPage:
    """받은 문서 하나. title 은 넘겨주기를 따라간 뒤의 제목이다."""

    lang: str
    title: str
    page_id: int
    revision_id: int
    url: str
    extract: str


def batches(titles: Sequence[str], size: int = BATCH_SIZE) -> list[list[str]]:
    """제목들을 size 개씩 나눈다. 차례는 그대로다."""
    return [list(titles[start : start + size]) for start in range(0, len(titles), size)]


def query_params(titles: Sequence[str]) -> dict[str, str]:
    """제목들의 도입부, 판, 주소, 동음이의어 여부를 묻는 물음. 서버가 바쁘면 기다리라고 답하게 한다(maxlag)."""
    return {
        'action': 'query',
        'format': 'json',
        'formatversion': '2',
        'prop': 'extracts|revisions|info|pageprops',
        'exintro': '1',
        'explaintext': '1',
        'exlimit': str(BATCH_SIZE),
        'rvprop': 'ids',
        'inprop': 'url',
        'ppprop': 'disambiguation',
        'redirects': '1',
        'maxlag': '5',
        'titles': '|'.join(titles),
    }


def resolved_titles(query: Mapping[str, Any]) -> dict[str, str]:
    """물은 제목 → 답의 제목. 제목 고치기(normalized)와 넘겨주기(redirects)를 차례로 따라간다."""
    steps = {item['from']: item['to'] for key in ('normalized', 'redirects') for item in query.get(key, [])}
    resolved: dict[str, str] = {}
    for start in steps:
        title, seen = start, {start}
        while title in steps and steps[title] not in seen:
            title = steps[title]
            seen.add(title)
        resolved[start] = title
    return resolved


def usable_page(lang: str, page: Mapping[str, Any]) -> WikiPage | None:
    """답의 문서 하나. 없는 문서, 동음이의어 문서, 도입부가 빈 문서는 None 이다."""
    if page.get('missing') or page.get('invalid') or 'disambiguation' in page.get('pageprops', {}):
        return None
    extract = page.get('extract', '').strip()
    revisions = page.get('revisions') or [{}]
    if not extract or 'revid' not in revisions[0]:
        return None
    return WikiPage(
        lang=lang,
        title=page['title'],
        page_id=page['pageid'],
        revision_id=revisions[0]['revid'],
        url=page.get('fullurl', ''),
        extract=extract,
    )


def pages_of(lang: str, titles: Sequence[str], answer: Mapping[str, Any]) -> dict[str, WikiPage]:
    """물은 제목 → 받은 문서. 쓸 수 없는 문서(없음, 동음이의어, 빈 도입부)의 제목은 빠진다."""
    query = answer.get('query', {})
    by_title = {page['title']: page for page in query.get('pages', []) if 'title' in page}
    resolved = resolved_titles(query)
    found: dict[str, WikiPage] = {}
    for title in titles:
        page = by_title.get(resolved.get(title, title))
        usable = usable_page(lang, page) if page is not None else None
        if usable is not None:
            found[title] = usable
    return found
