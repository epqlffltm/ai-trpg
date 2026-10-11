# game-server/app/tables/injuries.py

"""
테이블에서 입은 부상(table_injuries)을 만들고 푸는 작은 함수들.

DB 를 모른다. 이미 읽어 온 시트나 NPC 상태의 부상 목록을 받아 고친다. 저장은 부른 쪽이 한다.
부상을 만들고 푸는 길은 여기뿐이다. 판정의 결과로 라운드가 부른다(app/rounds/service.py).
방장이 손으로 고치는 길은 없다.

부상은 지우지 않는다. 풀리거나 나으면 그 시각을 적는다. 누가 언제 무엇을 입었는지의 기록이다.
어떤 부상인지는 이름만 적는다. 효과와 사실은 판에 굳은 규칙에서 찾는다(app/engine/injury.py).
"""

import uuid
from datetime import UTC, datetime

from app.tables.models import InjurySource, TableInjury


def active(injuries: list[TableInjury]) -> list[TableInjury]:
    """아직 입고 있는 부상들. 생긴 순서다."""
    return [injury for injury in injuries if injury.ended_at is None]


def active_keys(injuries: list[TableInjury]) -> list[str]:
    """아직 입고 있는 부상들의 이름. 생긴 순서다. 같은 부상을 두 번 입었으면 두 번 나온다."""
    return [injury.injury for injury in active(injuries)]


def inflict(
    injuries: list[TableInjury],
    table_id: uuid.UUID,
    key: str,
    source: InjurySource,
    round_number: int,
    ends_after_round: int | None,
) -> TableInjury:
    """
    부상 하나를 입힌다. injuries 는 입는 쪽(시트나 NPC 상태)의 부상 목록이다. 그 맨 뒤에 놓고 돌려준다.

    누가 입었는지(sheet_id, npc_entry_id)는 목록의 주인이 채운다(관계).
    """
    injury = TableInjury(
        table_id=table_id,
        injury=key,
        source=source,
        round_number=round_number,
        ends_after_round=ends_after_round,
    )
    injuries.append(injury)
    return injury


def expire(injuries: list[TableInjury], round_number: int) -> list[TableInjury]:
    """
    이 라운드가 닫힐 때 풀릴 부상들을 푼다. 푼 것을 돌려준다.

    풀리는 라운드가 이 라운드이거나 그 앞인 짧은 부상이다. 이 라운드에 생긴 것은 풀리는 라운드가 뒤라서 풀리지 않는다.
    """
    ended = [
        injury
        for injury in active(injuries)
        if injury.ends_after_round is not None and injury.ends_after_round <= round_number
    ]
    now = datetime.now(UTC)
    for injury in ended:
        injury.ended_at = now
    return ended
