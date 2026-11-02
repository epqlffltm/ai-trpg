# asset-server/tests/test_search.py

"""
공개 목록의 검색어를 나누는 순수한 함수를 검증한다(app/search.py, #984).

DB 에서 실제로 찾는 것은 tests/test_characters_api.py 와 tests/test_world_listings.py 가 본다.
"""

import re

import pytest

from app.search import SEARCH_PATTERN, SearchTerms, contains_pattern, parse_search


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('은하', SearchTerms(text='은하')),
        ('  은하 추격 ', SearchTerms(text='은하 추격')),
        ('#판타지', SearchTerms(tag='판타지')),
        ('  # 판타지 ', SearchTerms(tag='판타지')),
        ('', None),
        ('   ', None),
        ('#', None),
        ('# ', None),
    ],
)
def test_parses_a_search(raw: str, expected: SearchTerms | None):
    assert parse_search(raw) == expected


@pytest.mark.parametrize(
    ('text', 'expected'),
    [('은하', '%은하%'), ('100%', '%100\\%%'), ('a_b', '%a\\_b%'), ('a\\b', '%a\\\\b%')],
)
def test_escapes_like_wildcards(text: str, expected: str):
    assert contains_pattern(text) == expected


@pytest.mark.parametrize('raw', ['은하', ' 은하', '#판타지', '# 판타지', ' #판타지'])
def test_the_pattern_accepts_something_to_search(raw: str):
    assert re.search(SEARCH_PATTERN, raw)


@pytest.mark.parametrize('raw', ['', '   ', '#', '#  ', ' # ', '##'])
def test_the_pattern_rejects_nothing_to_search(raw: str):
    assert re.search(SEARCH_PATTERN, raw) is None
