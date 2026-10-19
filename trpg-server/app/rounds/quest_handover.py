# trpg-server/app/rounds/quest_handover.py

"""
이룬 퀘스트가 가져가는 물건을 일행의 소지품에서 뺀다(#455). 배달 퀘스트의 "가져다줬다"다.

물건 갖기 조건(hold_item)에 consume 을 적은 것만 가져간다. 퀘스트가 성공으로 바뀔 때 보상보다 먼저 뺀다
(app/rounds/quest_goals.py 의 succeed). 보상으로 받은 같은 물건을 바로 가져가지 않는다.

  - 누구의 것을: 조건을 셀 때와 같은 사람들이다. 지금 캐릭터가 있고 죽지 않았다. 쓰러져 있어도 된다.
  - 얼마씩: 고르게 나눈다. 앉은 순서로 한 개씩 돌아가며 뺀다. 적게 가진 사람이 먼저 바닥나면 남은 사람에게서 마저 뺀다.
    약초 3·2·1 개에서 4 개면 2·1·1 개를 뺀다.
  - 조건이 채워졌을 때만 부르므로 모자라지 않는다. 같은 라운드에 앞 퀘스트가 먼저 가져가 모자라면 그 퀘스트는
    아직 이루지 않은 것이다(quest_goals 가 판의 순서로 하나씩 본다).

DB 를 모른다. 소지품을 고치고 이벤트에 적을 모양을 돌려준다.
"""

import uuid
from collections.abc import Sequence

from app.assets.scenarios.snapshot import QuestConditionSnapshot
from app.tables import items
from app.tables.items import CatalogItem
from app.tables.models import TableMember


def split_evenly(holdings: Sequence[int], need: int) -> list[int]:
    """
    need 개를 가진 사람들에게서 고르게 나눠 뺄 개수. holdings 의 순서(앉은 순서)로 한 개씩 돌아가며 뺀다.

    가진 것보다 많이 빼지 않는다. 모두 합쳐도 need 보다 적으면 가진 것을 모두 뺀다.
    """
    taken = [0] * len(holdings)
    left = need
    while left:
        takers = [index for index, have in enumerate(holdings) if taken[index] < have]
        if not takers:
            return taken
        for index in takers[:left]:
            taken[index] += 1
        left -= min(left, len(takers))
    return taken


def take_shares(
    members: Sequence[TableMember], condition: QuestConditionSnapshot, things: dict[uuid.UUID, CatalogItem]
) -> list[tuple[TableMember, dict]]:
    """조건 하나가 가져가는 물건을 사람마다 뺀다. 뺀 사람마다 (사람, 물건 한 줄)이다. 앉은 순서다."""
    holdings = [items.count_of(member.sheet, condition.target) for member in members]
    taken = []
    for member, share in zip(members, split_evenly(holdings, condition.count), strict=True):
        if not share:
            continue
        total = items.remove_items(member.sheet, condition.target, share)
        thing = {
            'entry_id': str(condition.target),
            'name': things[condition.target].name,
            'count': share,
            'total': total,
        }
        taken.append((member, thing))
    return taken


def hand_over(
    members: Sequence[TableMember],
    conditions: Sequence[QuestConditionSnapshot],
    things: dict[uuid.UUID, CatalogItem],
) -> list[dict]:
    """
    가져가는 조건들의 물건을 뺀다. 이벤트에 적을 모양으로 돌려준다. 보상(rewards)과 같은 모양이다.

    낸 사람마다 user_id, character_name, items(물건마다 entry_id, name, count(뺀 개수), total(그 뒤의 개수))다.
    앉은 순서이고 아무것도 내지 않은 사람은 없다. 가져가는 조건이 없으면 빈 목록이다.
    """
    given: dict[uuid.UUID, list[dict]] = {}
    for condition in conditions:
        for member, thing in take_shares(members, condition, things):
            given.setdefault(member.user_id, []).append(thing)
    return [
        {'user_id': str(member.user_id), 'character_name': member.character_name, 'items': given[member.user_id]}
        for member in members
        if member.user_id in given
    ]
