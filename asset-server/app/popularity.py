# asset-server/app/popularity.py

"""
캐릭터와 세계관이 얼마나 쓰였는가(#985). 받아 쌓아 둔 시작 수(app/stats/)를 쓴다.

  - 카드의 수(start_count)는 모든 기간의 수다. 작품의 행에 적어 두고 받아 올 때마다 고친다(app/stats/repository.py)
  - 인기순은 최근 7일에 시작한 수가 많은 것부터, 같으면 모든 수, 그것도 같으면 최근에 게시한 것이다(랭킹과 같다)
수는 한 시간까지 늦다. 시나리오의 것은 trpg-server 가 테이블을 바로 센다.
"""

import enum
from typing import Any

from sqlalchemy import Select, func

from app.stats.models import WorkKind, WorkStarts


class ListingOrder(enum.StrEnum):
    """공개 목록의 차례. recent 는 최근에 게시한 것부터, popular 는 최근 7일에 많이 시작한 것부터다."""

    RECENT = 'recent'
    POPULAR = 'popular'


def by_popularity(query: Select, kind: WorkKind, work: Any) -> Select:
    """목록을 인기순으로 줄 세운다. 받은 수가 없는 것은 0 으로 보고 뒤에 둔다."""
    return query.outerjoin(WorkStarts, (WorkStarts.kind == kind) & (WorkStarts.work_id == work.id)).order_by(
        func.coalesce(WorkStarts.recent, 0).desc(),
        func.coalesce(WorkStarts.total, 0).desc(),
        work.published_at.desc(),
        work.id,
    )
