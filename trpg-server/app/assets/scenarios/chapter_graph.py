# trpg-server/app/assets/scenarios/chapter_graph.py

"""
장의 갈림길(#289)을 그래프로 읽는다. 시나리오의 초안(schemas.Chapter)과 판(snapshot.ChapterSnapshot)이 함께 쓴다.

  - 앞의 장(predecessors): 장의 after 다. 비우면 목록에서 바로 앞의 장이다. 첫 장에는 없다.
  - 조상(ancestors): 그 장에 오기 전에 지날 수 있는 장들이다.
    after 는 목록의 앞만 가리키므로 목록의 차례로 한 번 훑는다.

장의 id 와 after 만 본다. DB 와 테이블을 모른다.
"""

from collections.abc import Sequence
from typing import Protocol


class ChapterLike(Protocol):
    """장의 id 와 앞의 장. 초안의 장과 판의 장이 둘 다 이 모양이다."""

    id: str
    after: list[str]


def predecessors(ids: list[str], position: int, after: list[str]) -> list[str]:
    """목록의 그 자리의 장이 어느 장 다음에 올 수 있는가. after 를 비웠으면 바로 앞의 장이다. 첫 장은 없다."""
    if after:
        return list(after)
    return [ids[position - 1]] if position > 0 else []


def ancestors(chapters: Sequence[ChapterLike]) -> dict[str, set[str]]:
    """장마다 그 장에 오기 전에 지날 수 있는 장들(자기는 빼고). 첫 장은 빈 집합이다."""
    ids = [chapter.id for chapter in chapters]
    found: dict[str, set[str]] = {}
    for position, chapter in enumerate(chapters):
        before = predecessors(ids, position, chapter.after)
        found[chapter.id] = set(before) | {far for one in before for far in found.get(one, set())}
    return found
