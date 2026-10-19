# trpg-server/app/rounds/item_actions.py

"""
물건을 쓰고 건네는 행동의 결과를 정한다(#202). 판정(주사위)이 없다.

라운드가 닫기 시작할 때 들어온 순서로 한 번만 한다(app/rounds/judging.py). 결과를 선언에 적고 그 뒤로는 읽기만 한다.
선언을 받을 때 가지고 있었어도 차례가 왔을 때 없을 수 있다. 그사이 방장이 빼앗았다(한 사람의 선언은 하나다).
그때는 아무것도 바뀌지 않고, 왜 못 했는지(reason)를 적는다.
선언을 받을 때 가지고 있어야 한다(app/rounds/acceptance.py). 이 라운드에 건네받을 물건을 미리 쓰겠다고 선언할 수 없다.

  - 쓰기: 소모품 하나를 줄인다. 회복하는 것이면 대상이 그 등급만큼 회복한다(app/rounds/checks.py 의 change_sheet).
    대상이 떠났거나 죽었으면 쓰지 않는다. 물건도 줄지 않는다.
  - 건네기: 준 사람에게서 빼고 받는 사람의 지금 캐릭터에게 더한다. 받는 쪽이 한 가지 99 개를 넘으면 건네지 않는다.

DB 를 모른다. 시트의 소지품과 HP 를 고친다. 저장하지 않는다.
"""

from app.engine.action import GiveAction, UseAction
from app.engine.health import ChangeKind
from app.rounds.checks import change_sheet
from app.rounds.effects import Judging
from app.tables import items, sheets
from app.tables import state as table_state
from app.tables.errors import TableConflictError
from app.tables.models import TableMember


class Reason:
    """쓰거나 건네지 못한 까닭. 결과의 reason 에 적는다."""

    # 그만큼 가지고 있지 않았다
    NOT_HELD = 'not_held'
    # 받을(회복할) 사람이 떠났거나 죽었다
    TARGET_GONE = 'target_gone'
    # 받는 쪽이 그 물건을 더 가질 수 없었다
    TOO_MANY = 'too_many'


def person(member: TableMember | None) -> dict | None:
    """결과에 적을 사람. 누구인지와 그때의 캐릭터 이름이다."""
    if member is None:
        return None
    return {'user_id': str(member.user_id), 'character_name': member.character_name}


def living(member: TableMember | None) -> TableMember | None:
    """살아 있는 캐릭터가 있는 사람이면 그대로, 아니면 None. 떠난 사람도 None 이다."""
    if member is None or member.sheet is None or sheets.is_dead(member):
        return None
    return member


def use_target(judging: Judging, member: TableMember, action: UseAction) -> TableMember | None:
    """회복받을 사람. 대상을 적지 않았으면 자기 자신이다(받을 때 채웠다)."""
    target_id = action.target or member.user_id
    return living(table_state.find_member(judging.table, target_id))


def judge_use(judging: Judging, member: TableMember, action: UseAction) -> dict:
    """
    소모품 하나를 쓴다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다.

    회복하는 것이면 대상의 HP 를 바꾸고 그 내용(effect)을 함께 적는다. 회복의 주사위를 여기서 굴린다.
    """
    item = judging.items[action.item]
    heals = item.heals is not None
    target = use_target(judging, member, action) if heals else None
    reason = None
    if items.count_of(member.sheet, action.item) < 1:
        reason = Reason.NOT_HELD
    elif heals and target is None:
        reason = Reason.TARGET_GONE

    effect = None
    if reason is None:
        items.remove_items(member.sheet, action.item, 1)
        if heals:
            effect = change_sheet(judging, target, ChangeKind.RECOVERY, item.heals)
    used = {
        'entry_id': str(item.entry_id),
        'name': item.name,
        'used': reason is None,
        'reason': reason,
        'target': person(target),
        'remaining': items.count_of(member.sheet, action.item),
    }
    return {'item_use': used, 'effect': effect}


def judge_give(judging: Judging, member: TableMember, action: GiveAction) -> dict:
    """물건을 건넨다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다."""
    item = judging.items[action.item]
    recipient = living(table_state.find_member(judging.table, action.target))
    reason = None
    if items.count_of(member.sheet, action.item) < action.count:
        reason = Reason.NOT_HELD
    elif recipient is None:
        reason = Reason.TARGET_GONE
    else:
        try:
            items.add_items(judging.table.id, recipient.sheet, action.item, action.count)
        except TableConflictError:
            reason = Reason.TOO_MANY
    if reason is None:
        items.remove_items(member.sheet, action.item, action.count)
    given = {
        'entry_id': str(item.entry_id),
        'name': item.name,
        'count': action.count,
        'given': reason is None,
        'reason': reason,
        'target': person(recipient) or {'user_id': str(action.target), 'character_name': None},
        'remaining': items.count_of(member.sheet, action.item),
        'target_total': items.count_of(recipient.sheet, action.item) if recipient is not None else None,
    }
    return {'item_give': given}
