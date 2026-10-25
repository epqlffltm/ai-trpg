# trpg-server/app/rounds/throws.py

"""
물건을 던지는 행동(#277, #801). 가진 물건 하나를 몬스터 한 마리나 장면의 인물에게 던진다. 어떤 물건이든 된다.

던지기는 맞히는 판정이다. 능력과 난이도를 플레이어가 고르지 않는다. 물건에 던지는 판정(throw)이 있으면 그것,
없으면 룰북의 맞히는 판정(rules.item_check)이다. 맞으면 그 물건의 효과 목록(#800)이 대상에게 든다.
물약을 던지면 인물이 회복하고, 독을 던지면 중독된다. 효과가 없는 물건(밧줄, 연막탄)은 맞아도 아무 일이 없다.
  - 판정과 효과는 물건을 인물이나 몬스터에게 쓰는 것과 같다(app/rounds/item_targets.py). 피해가 있으면 그 등급의
    타격으로 판정해 방어, 세이브, 부상 표, 드롭이 치기와 같다. 무기와 노려 치기는 없다. 맞은 부위는 굴린다.
  - 던지면 맞든 빗나가든 물건이 하나 없어진다. 던지지 않았으면 없어지지 않는다. 착용한 물건이면 그만큼 벗는다.
  - 차례가 왔을 때 더 가지고 있지 않으면(not_held) 던지지 않는다. 굴리지 않는다.
  - 겨눈 몬스터가 그사이에 죽었거나 다른 곳에 있으면(target_gone) 던지지 않는다. 치기와 같이 그 까닭도 적는다.
결과는 선언의 outcome 에 판정의 결과와 함께 item_throw 로 적는다. 판정의 능력과 난이도는 그 안에 있다
(판정의 기록과 서술이 읽는다, app/rounds/narration_request.py 의 check_terms).

DB 를 모른다. 시트의 소지품과 맞은 쪽의 상태를 고친다. 저장하지 않는다.
"""

from app.engine.action import CheckAction, ThrowAction
from app.rounds.checks import judge_check, monster_gone
from app.rounds.effects import Judging
from app.rounds.item_targets import apply_after_hit, landed, mark_harm, target_of, to_check
from app.tables import items
from app.tables.items import CatalogItem
from app.tables.models import TableMember

# 맞지 않았거나 효과가 없는 던지기의 효과 결과
NOTHING_APPLIED = {'cured': [], 'injured': []}


class Reason:
    """던지지 못한 까닭. 결과의 reason 에 적는다."""

    # 그 물건을 더 가지고 있지 않았다
    NOT_HELD = 'not_held'
    # 겨눈 몬스터가 죽었거나 다른 곳에 있었다
    TARGET_GONE = 'target_gone'


def throw_terms(judging: Judging, item: CatalogItem) -> tuple[str, str | None]:
    """
    던지는 판정의 능력과 난이도. 물건에 적혀 있으면 그것, 없으면 룰북의 맞히는 판정이다(#801).

    받을 때 둘 중 하나가 있는지 봤다(app/rounds/acceptance.py 의 accept_throw).
    """
    if item.throw is not None:
        return item.throw.ability, item.throw.difficulty
    rule = judging.ruleset.item_check
    return rule.ability, rule.difficulty


def throw_document(
    judging: Judging,
    member: TableMember,
    item: CatalogItem,
    action: ThrowAction,
    check: CheckAction,
    reason: str | None,
) -> dict:
    """던진 결과의 문서(item_throw). 던졌는가, 못 했으면 까닭, 판정의 능력과 난이도, 맞을 쪽, 남은 개수다."""
    return {
        'entry_id': str(item.entry_id),
        'name': item.name,
        'thrown': reason is None,
        'reason': reason,
        'ability': check.ability,
        'difficulty': check.difficulty,
        'target': target_of(judging, action),
        'remaining': items.count_of(member.sheet, action.item),
        **NOTHING_APPLIED,
    }


def judge_throw(judging: Judging, member: TableMember, action: ThrowAction) -> dict:
    """
    물건 하나를 던진다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다.

    던졌으면 판정의 결과(판정, 대상의 변화, 방어, 드롭)에 item_throw 를 더한다. item_throw 에는 맞힌 대상에게서
    푼 부상(cured)과 입힌 부상(injured)이 있다. 못 던졌으면 item_throw 만 있다.
    겨눈 몬스터가 없어 못 던졌으면 치기와 같은 target_gone 도 있다.
    """
    item = judging.items[action.item]
    check = to_check(judging, item, action, *throw_terms(judging, item))
    if items.count_of(member.sheet, action.item) < 1:
        return {'item_throw': throw_document(judging, member, item, action, check, Reason.NOT_HELD)}
    gone = monster_gone(judging, member, action.monster) if action.monster is not None else None
    if gone is not None:
        document = throw_document(judging, member, item, action, check, Reason.TARGET_GONE)
        return {'item_throw': document, 'target_gone': gone}
    mark_harm(judging, member, item, action, check)
    items.remove_items(member.sheet, action.item, 1)
    outcome = judge_check(judging, member, check)
    applied = apply_after_hit(judging, item, action) if landed(outcome, check) else NOTHING_APPLIED
    thrown = {**throw_document(judging, member, item, action, check, None), **applied}
    return {**outcome, 'item_throw': thrown}
