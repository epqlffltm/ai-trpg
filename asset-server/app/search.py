# asset-server/app/search.py

"""
공개 목록의 검색어(#984). 화면의 검색칸에 적은 한 줄을 거르는 값으로 바꾼다. DB 를 부르지 않는 순수한 함수다.

  - "#"로 시작하면 태그 하나를 찾는다("#판타지" → 태그 "판타지"가 붙은 것).
  - 아니면 이름에 그 글이 들어 있는 것을 찾는다(대소문자를 가리지 않는다).
글자 조각 색인(pg_trgm, docker/postgres/init/03-extensions.sql)이 ILIKE 를 빠르게 한다.
시나리오의 공개 목록(trpg-server/app/listings/search.py)과 규칙이 같다. 서버끼리 코드를 나눠 쓰지 않으므로 따로 둔다.
"""

from dataclasses import dataclass

from sqlalchemy import ColumnElement, String, literal_column

# 검색어의 길이. 캐릭터·세계관의 이름보다 길게 적을 일은 없다
SEARCH_MAX_LENGTH = 50

# 찾을 글이 한 글자는 있어야 한다. 앞의 공백과 "#" 하나를 지나서 공백도 "#"도 아닌 글자가 와야 한다
SEARCH_PATTERN = r'^\s*(?:#\s*)?[^\s#]'

# ILIKE 의 특수 문자를 글자 그대로 찾게 할 때 앞에 붙이는 문자
LIKE_ESCAPE = '\\'


@dataclass(frozen=True)
class SearchTerms:
    """검색어를 나눈 것. 둘 중 하나만 찬다."""

    text: str | None = None
    tag: str | None = None


def parse_search(raw: str) -> SearchTerms | None:
    """
    검색어 한 줄을 나눈다. 앞뒤 공백을 지우고 비면 None 이다(거르지 않는다).

    "#" 뒤가 비었으면("#" 하나) 거르지 않는다.
    """
    query = raw.strip()
    if query.startswith('#'):
        tag = query[1:].strip()
        return SearchTerms(tag=tag) if tag else None
    return SearchTerms(text=query) if query else None


def contains_pattern(text: str) -> str:
    """ILIKE 로 "이 글이 들어 있다"를 찾는 모양. 사용자가 적은 %, _, \\ 는 글자 그대로 찾는다."""
    escaped = text.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2).replace('%', f'{LIKE_ESCAPE}%').replace('_', f'{LIKE_ESCAPE}_')
    return f'%{escaped}%'


def name_of(document: ColumnElement) -> ColumnElement[str]:
    """
    판의 문서(JSONB)에서 이름을 글로 꺼내는 식(document ->> 'name').

    키 'name' 을 값으로 넘기지 않고 글자 그대로 적는다. 값으로 넘기면 DB 가 이 식을 색인의 식
    (ix_character_versions_name_trgm, ix_world_versions_name_trgm)과 같은 것으로 알아보지 못할 때가 있다.
    """
    return document.op('->>', return_type=String)(literal_column("'name'"))
