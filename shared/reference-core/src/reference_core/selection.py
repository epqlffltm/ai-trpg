# shared/reference-core/src/reference_core/selection.py

"""
이번 장면에 넣을 참고 자료를 고르는 규칙. DB 도 모델도 모르는 순수한 함수다(고를 줄과 거리는 받는다).

로어북 검색과 같은 방식이다. 찾는 글(장면과 말)과 자료의 벡터와의 거리를 잰 것을 받아 고른다.
  1. 다른 이름: 줄의 다른 이름(한국어 이름, aliases)이 글에 그대로 들어 있고, 거리가 keyword_max_distance 이하인 것.
     원본의 이름(영어)으로는 고르지 않는다. 한국어 장면에 나오지 않고, 짧은 영어 이름("Bat")은 낱말 속에서 잘못 걸린다.
  2. 벡터: 거리가 max_distance 이하인 것, 가까운 순으로 limit 개까지.
다른 이름으로 고른 것을 먼저, 그다음 가까운 순으로 넣는다. 글자 수의 합이 남은 자리(room)를 넘지 않는다.
남은 자리를 셈하는 것(로어북이 쓰고 남은 것)은 서버마다 다르다. 서버가 정해 넘긴다.
"""

import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from reference_core.records import StoredReference

# 넣는 참고 자료의 글자 수(이름 + 글)의 합의 상한. 한 줄이 1,000자 안쪽이라 한두 줄이다
REFERENCE_MAX_CHARS = 1500
# 넣는 참고 자료의 수의 상한
REFERENCE_LIMIT = 3
# 이보다 짧은 다른 이름으로는 고르지 않는다
MIN_ALIAS_LENGTH = 2
# 이보다 먼 줄은 벡터로 고르지 않는다. 서버의 설정 REFERENCE_MAX_DISTANCE 의 기본값. 로어북의 것(bge-m3)과 같게 두었다.
# 켠 것과 끈 것을 견주는 평가로 다시 잰다
MAX_DISTANCE = 0.45
# 다른 이름으로 걸린 줄도 거리가 이보다 멀면 넣지 않는다(동음이의어).
# 서버의 설정 REFERENCE_KEYWORD_MAX_DISTANCE 의 기본값
KEYWORD_MAX_DISTANCE = 0.50


@dataclass(frozen=True)
class ReferenceThresholds:
    """고르는 규칙의 숫자들. 거리는 코사인 거리다."""

    max_distance: float = MAX_DISTANCE
    keyword_max_distance: float = KEYWORD_MAX_DISTANCE
    limit: int = REFERENCE_LIMIT
    max_chars: int = REFERENCE_MAX_CHARS


def mentions_alias(reference: StoredReference, text: str) -> bool:
    """
    줄의 다른 이름 중 하나가 글에 그대로 들어 있는가. 대소문자는 가리지 않는다.

    한 글자 이름("쥐")은 보지 않는다. 낱말 속("쥐었다")에서 잘못 걸린다. 그런 줄은 뜻(벡터)으로 고른다.
    """
    folded = text.casefold()
    names = [alias.strip() for alias in reference.aliases]
    return any(name.casefold() in folded for name in names if len(name) >= MIN_ALIAS_LENGTH)


def alias_hits(references: Sequence[StoredReference], text: str) -> list[StoredReference]:
    """다른 이름이 글에 들어 있는 줄들. 받은 차례대로다."""
    return [reference for reference in references if mentions_alias(reference, text)]


def near_enough(reference: StoredReference, distances: Mapping[uuid.UUID, float], max_distance: float) -> bool:
    """다른 이름으로 걸린 줄을 넣어도 되는가. 거리가 max_distance 이하이거나, 거리를 모르면(벡터가 없음) 넣는다."""
    return distances.get(reference.id, -math.inf) <= max_distance


def reference_size(reference: StoredReference) -> int:
    """줄 하나가 서술에 차지하는 글자 수(이름 + 글). 로어북 항목과 같은 셈이다."""
    return len(reference.shown_name) + len(reference.shown_content)


def pick(ordered: Sequence[StoredReference], room: int, limit: int) -> list[StoredReference]:
    """
    차례대로 넣되 글자 수의 합이 room 을, 수가 limit 을 넘지 않게 고른다. 같은 줄은 한 번만.

    들어가지 않는 줄은 건너뛰고 다음 것을 본다. 뒤의 짧은 줄은 들어갈 수 있다.
    """
    picked: list[StoredReference] = []
    seen: set[uuid.UUID] = set()
    used = 0
    for reference in ordered:
        size = reference_size(reference)
        if len(picked) >= limit:
            break
        if reference.id in seen or used + size > room:
            continue
        picked.append(reference)
        seen.add(reference.id)
        used += size
    return picked


def choose(
    hits: Sequence[StoredReference],
    distances: Mapping[uuid.UUID, float],
    nearest: Sequence[StoredReference],
    thresholds: ReferenceThresholds,
    room: int,
) -> list[StoredReference]:
    """
    넣을 줄을 고른다. 다른 이름으로 걸리고 거리가 가까운 것을 먼저, 그다음 뜻이 가까운 것(nearest)을, room 안에서.

    nearest 는 이미 거리 기준 안의 가까운 순이다(repository.nearest). distances 는 다른 이름으로 걸린 줄의 거리다.
    """
    near_hits = [hit for hit in hits if near_enough(hit, distances, thresholds.keyword_max_distance)]
    return pick([*near_hits, *nearest], room, thresholds.limit)
