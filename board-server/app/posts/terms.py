# board-server/app/posts/terms.py

"""
글 검색의 검색어를 다루는 규칙과 셈. 순수한 함수들이다.

검색어를 낱말로 나누고, 낱말마다 "제목이나 본문에 이 글자들이 들어 있는가"를 본다. 모든 낱말이 들어 있는 글이 나온다.
낱말의 어디에 있든 찾는다(부분 일치). 한국어는 낱말에 조사가 붙어서, 낱말이 통째로 같을 때만 찾으면
"공지"로 "공지를"을 찾지 못한다.
"""

import re

from app.core.checks import NOT_SPACE, SPACE

# 검색어 전체의 최대 길이(글자)
MAX_QUERY_LENGTH = 50
# 낱말 하나의 최소 길이(글자). 한 글자로 찾으면 거의 모든 글이 걸린다
MIN_TERM_LENGTH = 2
# 검색어에 적을 수 있는 낱말의 수. 낱말마다 조건이 하나씩 는다
MAX_TERMS = 5

# 낱말마다 MIN_TERM_LENGTH 자 이상이다. 빈칸 하나로 나뉜 검색어(normalize_query 를 거친 것)에 쓴다
TERMS_LONG_ENOUGH = re.compile(rf'\A{NOT_SPACE}{{{MIN_TERM_LENGTH},}}( {NOT_SPACE}{{{MIN_TERM_LENGTH},}})*\Z')
# 낱말이 MAX_TERMS 개 이하다
NOT_TOO_MANY_TERMS = re.compile(rf'\A{NOT_SPACE}+( {NOT_SPACE}+){{0,{MAX_TERMS - 1}}}\Z')

SPACES = re.compile(f'{SPACE}+')
# LIKE 에서 뜻이 있는 글자들. 역빗금은 이 글자들의 뜻을 없애는 글자라 함께 다룬다
LIKE_SPECIAL = re.compile(r'[\\%_]')


def terms_of(query: str) -> list[str]:
    """검색어를 낱말들로 나눈다. 빈칸에서 나눈다. 같은 낱말은 한 번만 남긴다."""
    terms = [term for term in SPACES.split(query) if term != '']
    return list(dict.fromkeys(terms))


def normalize_query(value: object) -> object:
    """
    검색어를 다듬는다. 앞뒤 빈칸을 떼고, 이어진 빈칸(줄바꿈과 탭도)을 빈칸 하나로 줄인다.
    글자가 아니면 그대로 둔다. 그것은 뒤의 검사가 거부한다.
    """
    return ' '.join(terms_of(value)) if isinstance(value, str) else value


def escape_like(term: str) -> str:
    """
    낱말에서 LIKE 가 기호로 읽는 글자(%, _)와 역빗금 앞에 역빗금을 붙인다.
    "100%"를 찾는 사람은 글자 % 를 찾는 것이다. 그대로 넘기면 "100 뒤에 아무 글자나"가 된다.
    """
    return LIKE_SPECIAL.sub(lambda special: '\\' + special.group(0), term)


def contains_pattern(term: str) -> str:
    """이 낱말이 어디에든 들어 있는 글을 고르는 LIKE 의 모양."""
    return f'%{escape_like(term)}%'
