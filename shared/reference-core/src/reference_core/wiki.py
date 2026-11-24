# shared/reference-core/src/reference_core/wiki.py

"""
위키백과를 참고 자료로 넣는 규칙. DB 도 HTTP 도 모르는 순수한 함수다.

정한 것(2026-11-22 유저 결정).
  - 고른 제목 목록만 넣는다(reference_core/wiki_titles.py). 한국어판 먼저, 없으면 영어판이다.
  - 서술에만 쓴다. 로어북·도감으로 복사하지 않는다(records.py 의 COPYABLE_SOURCES).
  - 위키백과의 글은 CC BY-SA 4.0 이다. 데이터 파일도 같은 조건이다. 줄마다 원문의 주소를 data.url 에 둔다.

문서의 도입부(평문)를 한 줄의 글로 만든다. 거르는 것.
  - 괄호와 그 안(외국어 표기, 발음, 생몰년), 각주 번호([1]), 좌표, 겹친 빈칸
  - 실제 세계를 가리키는 문장. 판타지 장면에 "1492년", "포르투갈" 같은 것이 섞이지 않게 한다.
    연도와 세기, 날짜, 나라와 도시의 이름(data/wikipedia-places.txt)이 든 문장을 뺀다.
    목록은 완전하지 않다. 서술의 프롬프트가 한 번 더 막는다(reference_core/prompt.py 의 TOPIC_RULE)
  - 문서를 소개하는 문장("다음을 가리킨다", "may refer to")
남은 문장을 차례대로 1,000자 안에서 문장째 담는다. 남은 문장이 없으면 그 문서는 넣지 않는다(None).
"""

import re
from collections.abc import Iterable, Sequence
from pathlib import Path

from reference_core.records import REFERENCE_CONTENT_MAX_LENGTH

WIKIPEDIA_ATTRIBUTION = (
    'This work includes text adapted from Wikipedia articles (Korean and English editions), '
    'licensed under the Creative Commons Attribution-ShareAlike 4.0 International License '
    '(https://creativecommons.org/licenses/by-sa/4.0/). Each entry links to its source article.'
)
WIKIPEDIA_CHANGES = (
    'Only the lead section was used. Wiki markup and sentences about real-world places, people and dates '
    'were removed, and the text was shortened.'
)
WIKIPEDIA_TRANSLATED = ' Entries from the English edition were translated into Korean.'

# 괄호 하나(안에 괄호가 없는 것). 안쪽부터 여러 번 지운다
PARENTHESES = re.compile(r'\s*[(（][^()（）]*[)）]')
# 각주 번호와 대괄호의 글([1], [주 1], [citation needed])
BRACKETS = re.compile(r'\[[^\[\]]*\]')
# 좌표(37°33′N 126°58′E)
COORDINATES = re.compile(r'\d+(?:\.\d+)?°[^\s,.;]*')
SPACES = re.compile(r'[ \t ]+')
# 문장의 끝. 마침표, 물음표, 느낌표 뒤의 빈칸에서 자른다
SENTENCE_END = re.compile(r'(?<=[.!?。])\s+')
# 실제 세계의 때를 가리키는 말. 한국어(1492년, 15세기, 기원전, 3월 1일)와 영어(1492, 15th century, BC, March 1)
REAL_TIME = re.compile(
    r'\d+\s*년|\d+\s*세기|기원전|서기|\d+\s*월\s*\d+\s*일'
    r'|\b1\d{3}s?\b|\b20\d{2}s?\b|\bcentur(?:y|ies)\b|\b(?:BC|BCE|AD|CE)\b'
    r'|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d',
    re.IGNORECASE,
)
# 문서를 소개하는 문장. 장면에 쓸 것이 없다
ABOUT_THE_ARTICLE = re.compile(r'다음을 가리킨다|may refer to|이 문서는|this article', re.IGNORECASE)
# 아무것도 맞지 않는 식(이름 목록이 비었을 때)
NOTHING = r'(?!)'


def read_places(path: Path) -> list[str]:
    """실제 세계의 나라와 도시의 이름 목록. 한 줄에 하나다. 빈 줄과 # 로 시작하는 줄은 뺀다."""
    lines = (line.strip() for line in path.read_text(encoding='utf-8').splitlines())
    return [line for line in lines if line and not line.startswith('#')]


def places_pattern(places: Iterable[str]) -> re.Pattern[str]:
    """
    이름들 가운데 하나가 든 글을 찾는 식. 영어 이름은 낱말째로 맞는다("Iran" 이 "Tirana" 에 걸리지 않게).
    한국어 이름은 글자가 이어지면 맞는다(조사가 붙는다). 그래서 한국어 이름은 두 글자 이상만 적는다.
    """
    words = sorted({place for place in places if place}, key=len, reverse=True)
    latin = [re.escape(word) for word in words if word.isascii()]
    other = [re.escape(word) for word in words if not word.isascii()]
    parts = ([rf'\b(?:{"|".join(latin)})\b'] if latin else []) + ([f'(?:{"|".join(other)})'] if other else [])
    return re.compile('|'.join(parts) or NOTHING)


def clean_text(text: str) -> str:
    """괄호, 각주, 좌표를 지우고 빈칸을 하나로. 줄은 그대로 둔다(문단의 경계)."""
    previous = None
    while previous != text:
        previous, text = text, PARENTHESES.sub('', text)
    text = COORDINATES.sub('', BRACKETS.sub('', text))
    lines = (SPACES.sub(' ', line).strip() for line in text.splitlines())
    return '\n'.join(line for line in lines if line)


def sentences(text: str) -> list[str]:
    """문단마다 문장으로 나눈다. 문단의 차례와 문장의 차례대로다."""
    return [part.strip() for line in text.splitlines() for part in SENTENCE_END.split(line) if part.strip()]


def is_real_world(sentence: str, places: re.Pattern[str]) -> bool:
    """실제 세계의 때나 곳을 가리키는가, 또는 문서를 소개하는 문장인가."""
    return bool(REAL_TIME.search(sentence) or places.search(sentence) or ABOUT_THE_ARTICLE.search(sentence))


def kept_sentences(text: str, places: re.Pattern[str]) -> list[str]:
    """도입부에서 장면에 써도 되는 문장들."""
    return [sentence for sentence in sentences(clean_text(text)) if not is_real_world(sentence, places)]


def within_length(parts: Sequence[str], limit: int = REFERENCE_CONTENT_MAX_LENGTH) -> str:
    """
    문장들을 차례대로 limit 안에서 이어 붙인다. 들어가지 않는 문장에서 멈춘다.
    글이 이어져야 해서 뒤의 짧은 문장을 끼우지 않는다.
    첫 문장부터 limit 보다 길면 그 문장을 limit 에서 자른다.
    """
    if not parts:
        return ''
    if len(parts[0]) > limit:
        return parts[0][:limit]
    text = parts[0]
    for part in parts[1:]:
        if len(text) + 1 + len(part) > limit:
            break
        text = f'{text} {part}'
    return text


def lead_content(extract: str, places: re.Pattern[str]) -> str | None:
    """문서의 도입부로 만든 글. 남은 문장이 없으면 None 이다(그 문서는 넣지 않는다)."""
    return within_length(kept_sentences(extract, places)) or None
