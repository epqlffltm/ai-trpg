# asset-server/app/characters/publishing.py

"""
캐릭터를 게시할 수 있는지 보는 규칙과, 게시할 때 소개를 거르는 것(#567). DB 를 모르는 순수한 함수다.

막는 것(problems)과 알리는 것(removed)을 나눈다.
  - 막는 것: 이것이 없으면 대화를 시작할 수 없다. 게시가 409 로 돌려준다.
  - 알리는 것: 소개에서 걸러 낸 태그, 속성, CSS, 링크, 그림. 게시는 되고, 거른 소개가 판에 들어간다.
나이와 성별로 막는 검사는 없다(2026-10-21).
"""

import enum

from app.characters.models import Character
from app.content.html import Cleaned, clean_intro


class Problem(enum.StrEnum):
    """게시할 수 없는 이유."""

    # 시작 상황이 하나도 없다. 대화는 시작 상황을 고르고 들어간다
    START_MISSING = 'start_missing'


class CharacterNotReadyError(Exception):
    """게시할 조건을 갖추지 못했다. problems 는 갖추지 못한 것 전부다(한 번에 알린다)."""

    def __init__(self, problems: list[Problem]) -> None:
        super().__init__(', '.join(problems))
        self.problems = problems


def find_problems(character: Character) -> list[Problem]:
    """게시를 막는 것들. 없으면 빈 목록이다."""
    problems = []
    if not character.starts:
        problems.append(Problem.START_MISSING)
    return problems


def cleaned_intro(character: Character) -> Cleaned:
    """초안의 소개를 거른 것과 걸러 낸 것들."""
    return clean_intro(character.intro_html)
