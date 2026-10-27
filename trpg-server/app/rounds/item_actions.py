# trpg-server/app/rounds/item_actions.py

"""
물건을 쓰고 건네는 행동의 결과를 정한다(#202).

라운드가 닫기 시작할 때 들어온 순서로 한 번만 한다(app/rounds/judging.py). 결과를 선언에 적고 그 뒤로는 읽기만 한다.
선언을 받을 때 가지고 있었어도 차례가 오면 다시 본다. 없으면 아무것도 바뀌지 않고, 왜 못 했는지(reason)를 적는다.
선언을 받을 때 가지고 있어야 한다(app/rounds/acceptance.py). 이 라운드에 건네받을 물건을 미리 쓰겠다고 선언할 수 없다.

  - 쓰기: 소모품 하나를 줄이고, 그 물건의 효과들(#800, app/engine/item_effects.py)을 적힌 차례대로 대상에게 낸다.
    자기와 동료에게는 굴리지 않는다. 인물과 몬스터에게 쓰면 맞히는 판정을 거친다(app/rounds/item_targets.py).
      - heal: 그 등급만큼 회복한다(app/rounds/checks.py 의 change_sheet). damage: 그 등급만큼 피해를 입는다.
      - cure: 대상이 입은 그 부상들을 모두 푼다. 오래 가는 것이 나으면 후유증 표를 굴린다(#277).
        대상이 그 부상을 입고 있지 않아도 쓴다(쓰고 아무 일도 없다).
      - injure: 그 부상을 입힌다. 이미 입고 있으면 또 입히지 않는다.
      - adjust: 그 수치(#804)를 양만큼 올리거나 내린다. 범위 밖으로 가지 않는다.
    대상이 떠났거나 죽었으면 쓰지 않는다. 물건도 줄지 않는다.
    해로운 효과(피해, 부상)가 있는 물건을 동료에게 쓰는 것은 치기와 같다(#803, app/rounds/friendly_fire.py).
    차례가 오면 해칠 수 있는지 다시 본다. 받아들이지 않게 바뀌었으면 friendly_fire_off, 쓰러졌거나 다른 곳에 있으면
    target_gone 이다. 장난이면 HP 를 1 아래로 내리지 않고 짧은 부상만 입힌다.
  - 건네기: 준 사람에게서 빼고 받는 사람의 지금 캐릭터에게 더한다. 받는 쪽이 한 가지 99 개를 넘으면 건네지 않는다.

DB 를 모른다. 시트의 소지품과 HP 와 부상을 고친다. 저장하지 않는다.
"""

from app.engine import injury as injury_rules
from app.engine.action import GiveAction, UseAction
from app.engine.health import ChangeKind
from app.engine.item_effects import EffectKind
from app.rounds import friendly_fire
from app.rounds import injuries as round_injuries
from app.rounds.checks import change_sheet
from app.rounds.effects import Judging
from app.tables import injuries, items, resources, sheets
from app.tables import state as table_state
from app.tables.errors import TableConflictError
from app.tables.items import CatalogItem
from app.tables.models import TableInjury, TableMember


class Reason:
    """쓰거나 건네지 못한 까닭. 결과의 reason 에 적는다."""

    # 그만큼 가지고 있지 않았다
    NOT_HELD = 'not_held'
    # 받을(회복할) 사람이 떠났거나 죽었다. 인물이나 몬스터면 그사이에 죽었거나 다른 곳에 있었다
    TARGET_GONE = 'target_gone'
    # 받는 쪽이 그 물건을 더 가질 수 없었다
    TOO_MANY = 'too_many'
    # 해로운 물건을 쓸 동료가 받아들이지 않게 바뀌었다(#803)
    FRIENDLY_FIRE_OFF = 'friendly_fire_off'


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
    """물건을 받을 사람. 대상을 적지 않았으면 자기 자신이다(받을 때 채웠다)."""
    target_id = action.target or member.user_id
    return living(table_state.find_member(judging.table, target_id))


def cure_one(judging: Judging, row: TableInjury, rows: list[TableInjury]) -> dict:
    """
    부상 하나를 푼다. 푼 것을 결과에 적을 모양으로 돌려준다(이름표, 이름, 후유증).

    오래 가는 것이면 나은 것이라 후유증 표를 굴린다(치료로 나을 때와 같다). 짧은 것이면 풀릴 뿐이다.
    """
    ruleset = judging.ruleset
    aftermath = None
    if round_injuries.is_lasting(ruleset, row):
        aftermath = round_injuries.heal(ruleset, judging.dice, row, rows, judging.table.id, judging.moment)
    else:
        injuries.end(row)
    definition = injury_rules.find_injury(ruleset, row.injury)
    return {'injury': row.injury, 'name': definition.name if definition else row.injury, 'aftermath': aftermath}


def cure(judging: Judging, rows: list[TableInjury], keys: list[str]) -> list[dict]:
    """입은 부상 중 그 이름표의 것을 모두 푼다. 생긴 순서다. 푼 것들을 돌려준다(#277)."""
    return [cure_one(judging, row, rows) for row in injuries.active(rows) if row.injury in keys]


def injure(
    judging: Judging, rows: list[TableInjury], key: str, immune=round_injuries.NO_IMMUNITY, prank: bool = False
) -> dict:
    """
    부상 하나를 입힌다(#800). 생긴 일의 문서를 돌려준다. 이미 입고 있었거나 면역이면 부상이 비어 있다.

    prank 면 동료의 장난이다(#803). 오래 가는 것과 결손은 입히지 않는다(문서의 spared).
    """
    return round_injuries.take_from_item(judging.ruleset, key, rows, judging.table.id, judging.moment, immune, prank)


def apply_to_member(judging: Judging, target: TableMember, item: CatalogItem, prank: bool = False) -> dict:
    """
    물건의 효과들을 앉은 사람 하나에게 차례대로 낸다(#800). 굴리지 않는다.

    돌려주는 것은 HP 의 변화(effect, 회복이나 피해 하나), 푼 부상들(cured), 입힌 부상들(injured),
    맞춘 수치들(resources, #804)이다. prank 면 동료의 장난이다(#803). 피해와 부상이 상한을 지킨다.
    """
    effect = None
    cured: list[dict] = []
    injured: list[dict] = []
    shifts: list[dict] = []
    rows = target.sheet.injuries
    for one in item.effects:
        if one.kind == EffectKind.HEAL:
            effect = change_sheet(judging, target, ChangeKind.RECOVERY, one.magnitude)
        elif one.kind == EffectKind.DAMAGE:
            effect = change_sheet(judging, target, ChangeKind.DAMAGE, one.magnitude, prank=prank)
        elif one.kind == EffectKind.CURE:
            cured.extend(cure(judging, rows, one.injuries))
        elif one.kind == EffectKind.INJURE:
            injured.append(injure(judging, rows, one.injury, prank=prank))
        elif one.kind == EffectKind.ADJUST:
            shifts.extend(adjust(judging, target, one.resource, one.amount))
    return {'effect': effect, 'cured': cured, 'injured': injured, 'resources': shifts}


def adjust(judging: Judging, target: TableMember, key: str, amount: int) -> list[dict]:
    """앉은 사람 하나의 수치를 맞춘다(#804). 바뀐 것의 문서를 돌려준다. 값이 같으면(이미 끝) 바뀐 것이 없다."""
    shift = resources.adjust(judging.ruleset, target.sheet, key, amount)
    if shift is None or shift.before == shift.after:
        return []
    return [resources.shift_document(shift, target.user_id)]


def harm_refused(judging: Judging, member: TableMember, item: CatalogItem, target: TableMember) -> str | None:
    """
    해로운 물건을 동료에게 쓰려는데 지금 해칠 수 없으면 쓰지 못한 까닭(#803). 쓸 수 있거나 해롭지 않으면 None.

    받아들이지 않게 바뀌었으면 friendly_fire_off, 쓰러졌거나 다른 곳에 있으면 target_gone 이다.
    """
    if target.user_id == member.user_id or not items.is_harmful(item):
        return None
    gone = friendly_fire.ally_gone(judging, member, target.user_id)
    if gone is None:
        return None
    return (
        Reason.FRIENDLY_FIRE_OFF if gone['reason'] == friendly_fire.AllyGone.FRIENDLY_FIRE_OFF else Reason.TARGET_GONE
    )


def is_prank_use(judging: Judging, member: TableMember, item: CatalogItem, target: TableMember) -> bool:
    """해로운 물건을 동료에게 쓰는 장난인가(#803). 자기 자신이나 이로운 물건이면 아니다."""
    if target.user_id == member.user_id or not items.is_harmful(item):
        return False
    return friendly_fire.is_prank_toward(judging, member, target)


def use_document(item: CatalogItem, member: TableMember, reason: str | None, target: dict | None) -> dict:
    """쓴 결과의 문서(item_use)의 머리. 무엇을, 썼는가, 못 했으면 까닭, 대상, 남은 개수다."""
    return {
        'entry_id': str(item.entry_id),
        'name': item.name,
        'used': reason is None,
        'reason': reason,
        'target': target,
        'remaining': items.count_of(member.sheet, item.entry_id),
        'cured': [],
        'injured': [],
        'resources': [],
    }


def judge_use(judging: Judging, member: TableMember, action: UseAction) -> dict:
    """
    소모품 하나를 쓴다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다.

    자기와 동료에게 쓰는 것이다. 굴리지 않는다. 인물이나 몬스터에게 쓰는 것은 app/rounds/item_targets.py 다.
    HP 가 바뀌었으면 그 내용(effect)을, 푼 부상(cured)과 입힌 부상(injured)을 item_use 에 함께 적는다.
    """
    item = judging.items[action.item]
    aimed = items.takes_target(item)
    target = use_target(judging, member, action) if aimed else None
    reason = None
    if items.count_of(member.sheet, action.item) < 1:
        reason = Reason.NOT_HELD
    elif aimed and target is None:
        reason = Reason.TARGET_GONE
    elif aimed:
        reason = harm_refused(judging, member, item, target)
    if reason is not None:
        return {'item_use': use_document(item, member, reason, person(target)), 'effect': None}
    items.remove_items(member.sheet, action.item, 1)
    applied = (
        apply_to_member(judging, target, item, is_prank_use(judging, member, item, target))
        if aimed
        else {'effect': None, 'cured': [], 'injured': [], 'resources': []}
    )
    used = {
        **use_document(item, member, None, person(target)),
        'cured': applied['cured'],
        'injured': applied['injured'],
        'resources': applied['resources'],
    }
    return {'item_use': used, 'effect': applied['effect']}


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
