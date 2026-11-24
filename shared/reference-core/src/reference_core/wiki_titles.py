# shared/reference-core/src/reference_core/wiki_titles.py

"""
위키백과에서 받을 제목 목록(data/wikipedia-titles.txt)을 읽는다. 순수한 함수다.

한 줄에 한 항목이다.

    한국어 제목 | 영어 제목 | 다른 이름, 다른 이름

  - 한국어 제목은 꼭 적는다. 한국어판에 그 문서가 있으면 그것을 받는다
  - 영어 제목은 한국어판에 없을 때 받는다. 비워도 된다(그러면 한국어판에만 찾는다)
  - 다른 이름은 장면에서 그 낱말이 나오면 고르는 이름이다(reference_core/selection.py). 비워도 된다
  - # 로 시작하는 줄은 주석, 빈 줄은 건너뛴다. # 으로 묶음(탈것, 건축)을 나눈다
한국어 제목의 괄호(동음이의어를 가르는 "성 (건축)")는 장면의 이름이 아니라서 다른 이름에서 뗀다.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from reference_core.records import REFERENCE_ALIAS_MAX_LENGTH, REFERENCE_MAX_ALIASES

# 제목 뒤의 괄호(동음이의어 가르기)
DISAMBIGUATION = re.compile(r'\s*\([^()]*\)\s*$')


def without_disambiguation(title: str) -> str:
    """제목 뒤의 괄호(동음이의어 가르기)를 뗀 이름. "성 (건축)" 은 "성" 이다."""
    return DISAMBIGUATION.sub('', title)


class TitleLineError(ValueError):
    """제목 목록의 줄이 틀렸다. 줄 번호를 함께 알린다."""


@dataclass(frozen=True)
class WikiTitle:
    """받을 문서 하나. ko 는 한국어판의 제목, en 은 영어판의 제목(없으면 빈 글), aliases 는 적은 다른 이름이다."""

    ko: str
    en: str = ''
    aliases: tuple[str, ...] = field(default_factory=tuple)

    @property
    def korean_name(self) -> str:
        """장면에서 부르는 한국어 이름. 제목 뒤의 괄호를 뗀다."""
        return without_disambiguation(self.ko)

    def names(self, found: Sequence[str] = ()) -> list[str]:
        """
        줄의 다른 이름(aliases). 한국어 이름이 맨 앞, 그다음 받은 문서의 이름(found, 넘겨주기를 따라간 한국어판의 제목),
        그다음 목록에 적은 다른 이름이다. 겹친 것과 긴 것(30자 넘음)은 뺀다. 다섯까지다.
        """
        picked: list[str] = []
        for name in (self.korean_name, *found, *self.aliases):
            if name and name not in picked and len(name) <= REFERENCE_ALIAS_MAX_LENGTH:
                picked.append(name)
        return picked[:REFERENCE_MAX_ALIASES]


def parse_line(line: str, number: int) -> WikiTitle | None:
    """줄 하나. 주석과 빈 줄은 None. 칸이 셋보다 많거나 한국어 제목이 없으면 TitleLineError 다."""
    text = line.strip()
    if not text or text.startswith('#'):
        return None
    parts = [part.strip() for part in text.split('|')]
    if len(parts) > 3 or not parts[0]:
        raise TitleLineError(f'{number}번째 줄: "한국어 제목 | 영어 제목 | 다른 이름" 의 모양이 아니다: {text}')
    en = parts[1] if len(parts) > 1 else ''
    aliases = tuple(name.strip() for name in parts[2].split(',') if name.strip()) if len(parts) > 2 else ()
    return WikiTitle(ko=parts[0], en=en, aliases=aliases)


def parse_titles(text: str) -> list[WikiTitle]:
    """목록 전체. 같은 한국어 제목이 두 번 나오면 TitleLineError 다(어느 줄의 다른 이름을 쓸지 모른다)."""
    titles: list[WikiTitle] = []
    seen: set[str] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        title = parse_line(line, number)
        if title is None:
            continue
        if title.ko in seen:
            raise TitleLineError(f'{number}번째 줄: 한국어 제목이 겹친다: {title.ko}')
        seen.add(title.ko)
        titles.append(title)
    return titles


def read_titles(path: Path) -> list[WikiTitle]:
    """제목 목록 파일을 읽는다."""
    return parse_titles(path.read_text(encoding='utf-8'))
