# game-server/app/tables/injuries.py

"""
테이블에서 입은 부상(table_injuries)을 만들고 푸는 작은 함수들.

DB 를 모른다. 이미 읽어 온 시트나 NPC 상태의 부상 목록을 받아 고친다. 저장은 부른 쪽이 한다.
부상을 만들고, 나을 시각을 바꾸고, 푸는 길은 여기뿐이다. 판정의 결과로 라운드가 부른다(app/rounds/judging.py).
방장이 손으로 고치는 길은 없다.

부상은 지우지 않는다. 풀리거나 나으면 그 시각을 적는다. 누가 언제 무엇을 입었는지의 기록이다.
어떤 부상인지는 이름만 적는다. 효과와 사실은 판에 굳은 규칙에서 찾는다(app/engine/injury.py).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.tables.models import InjurySource, TableInjury


@dataclass(frozen=True)
class Moment:
    """
    라운드가 닫히는 때. 부상이 생기고 풀리고 낫는 때를 정하는 데 쓴다.

    round_number 는 닫히는 라운드의 번호다. 짧은 부상은 라운드로 센다.
    now 는 그 라운드가 열린 게임 안의 시각, scene_end 는 그 장면이 끝나는 시각이다(다음 라운드가 열릴 때).
    오래 가는 부상은 now 에 생기고, scene_end 가 나을 시각에 닿으면 낫는다.
    round_minutes 는 판의 라운드 하나에 흐르는 기본 시간이다. 규칙에 라운드 수로 적힌 기간을 분으로 바꾼다.
    """

    round_number: int
    now: int
    scene_end: int
    round_minutes: int


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
    heals_at: int | None,
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
        heals_at=heals_at,
    )
    injuries.append(injury)
    return injury


def find_active(injuries: list[TableInjury], key: str) -> TableInjury | None:
    """아직 입고 있는 이 부상. 같은 부상을 둘 입었으면 먼저 생긴 것이다. 입고 있지 않으면 None."""
    return next((injury for injury in active(injuries) if injury.injury == key), None)


def is_expired(injury: TableInjury, round_number: int) -> bool:
    """짧은 부상이 이 라운드가 닫힐 때 풀리는가. 풀리는 라운드가 이 라운드이거나 그 앞이다."""
    return injury.ends_after_round is not None and injury.ends_after_round <= round_number


def is_healed(injury: TableInjury, moment: Moment) -> bool:
    """
    오래 가는 부상이 이 라운드가 닫힐 때 낫는가. 이 장면이 끝나는 때가 나을 시각에 닿았다.

    이 라운드에 생긴 것은 낫지 않는다. 다쳐서 그 장면 안에 나으면 생긴 것과 나은 것이 한 줄에 겹친다.
    """
    return (
        injury.heals_at is not None
        and injury.round_number < moment.round_number
        and injury.heals_at <= moment.scene_end
    )


def is_due(injury: TableInjury, moment: Moment) -> bool:
    """이 라운드가 닫힐 때 풀리거나 낫는 부상인가. 끝난 것은 아니다."""
    return injury.ended_at is None and (is_expired(injury, moment.round_number) or is_healed(injury, moment))


def end(injury: TableInjury) -> None:
    """부상을 끝낸다(풀렸거나 나았다). 끝난 시각을 적는다. 지우지 않는다."""
    injury.ended_at = datetime.now(UTC)


def reschedule(injury: TableInjury, heals_at: int) -> None:
    """
    오래 가는 부상의 나을 시각(분)을 바꾼다. 치료에 성공하면 앞당겨지고, 덧나면 늦춰진다(app/engine/treatment.py).

    이 장면이 끝나는 때보다 앞으로 당겨질 일이면 부른 쪽이 바로 낫게 한다(end).
    """
    injury.heals_at = heals_at
    # 시간으로 낫기 전에 입어 라운드가 적혀 있던 것도 이제 시각으로 낫는다(둘을 함께 적지 않는다)
    injury.ends_after_round = None


def expire(injuries: list[TableInjury], moment: Moment) -> list[TableInjury]:
    """
    이 라운드가 닫힐 때 풀리거나 나을 부상들을 끝낸다. 끝낸 것을 돌려준다.

    짧은 것은 풀리는 라운드가 이 라운드이거나 그 앞일 때, 오래 가는 것은 이 장면이 끝나는 때가 나을 시각에 닿았을 때다.
    결손은 둘 다 없다. 이 라운드에 생긴 것은 풀리거나 낫지 않는다.
    오래 가는 것이 나을 때의 후유증은 부른 쪽이 굴린다(app/rounds/injuries.py).
    """
    ended = [injury for injury in injuries if is_due(injury, moment)]
    for injury in ended:
        end(injury)
    return ended
