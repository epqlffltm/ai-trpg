# trpg-server/app/rounds/throws.py

"""
물건을 던지는 행동(#277). 화염병, 투척 단검처럼 가진 소모품 하나를 몬스터 한 마리나 장면의 인물에게 던진다.

던지기는 물건에 적힌 판정으로 하는 치기다. 능력, 난이도, 맞았을 때의 피해를 플레이어가 고르지 않는다.
  - 판정, 방어, 세이브, 피해, 드롭은 치기와 같다(app/rounds/checks.py 의 judge_check 를 그대로 부른다).
    무기와 노려 치기는 없다. 맞은 부위는 굴린다.
  - 던지면 맞든 빗나가든 물건이 하나 없어진다. 던지지 않았으면 없어지지 않는다.
  - 차례가 왔을 때 더 가지고 있지 않으면(not_held) 던지지 않는다. 굴리지 않는다.
  - 겨눈 몬스터가 그사이에 죽었거나 다른 곳에 있으면(target_gone) 던지지 않는다. 치기와 같이 그 까닭도 적는다.
결과는 선언의 outcome 에 치기의 결과와 함께 item_throw 로 적는다. 판정의 능력과 난이도는 그 안에 있다
(판정의 기록과 서술이 읽는다, app/rounds/narration_request.py 의 check_terms).

DB 를 모른다. 시트의 소지품과 맞은 쪽의 상태를 고친다. 저장하지 않는다.
"""

from app.engine.action import ActionKind, CheckAction, ThrowAction, settle
from app.rounds.cast import find_cast_member
from app.rounds.checks import judge_check, target_gone
from app.rounds.effects import Judging
from app.rounds.monster_scene import find_scene_monster
from app.tables import items
from app.tables.items import CatalogItem
from app.tables.models import TableMember


class Reason:
    """던지지 못한 까닭. 결과의 reason 에 적는다."""

    # 그 물건을 더 가지고 있지 않았다
    NOT_HELD = 'not_held'
    # 겨눈 몬스터가 죽었거나 다른 곳에 있었다
    TARGET_GONE = 'target_gone'


def to_check(judging: Judging, item: CatalogItem, action: ThrowAction) -> CheckAction:
    """
    던지기를 그 물건의 판정으로 치는 행동으로 바꾼다. 비워 둔 난이도는 규칙의 기본이다.

    게시할 때 판정이 룰북에 맞는지 봤다(item_throw_invalid). 판에 굳은 룰북이라 바뀌지 않는다.
    """
    check = CheckAction(
        kind=ActionKind.CHECK,
        ability=item.throw.ability,
        difficulty=item.throw.difficulty,
        harm=item.throw.harm,
        npc=action.npc,
        monster=action.monster,
        lethal=action.lethal,
    )
    return settle(judging.ruleset, check)


def target_of(judging: Judging, action: ThrowAction) -> dict:
    """던진 쪽을 결과에 적을 모양. 몬스터면 그 마리의 id 와 이름, 인물이면 항목의 id 와 장면의 호칭이다."""
    if action.monster is not None:
        monster = find_scene_monster(judging.monsters, action.monster)
        return {'monster_id': str(action.monster), 'name': monster.name if monster else None}
    person = find_cast_member(judging.cast, action.npc)
    return {'entry_id': str(action.npc), 'name': person.name if person else None}


def throw_document(
    judging: Judging,
    member: TableMember,
    item: CatalogItem,
    action: ThrowAction,
    check: CheckAction,
    reason: str | None,
) -> dict:
    """던진 결과의 문서(item_throw). 던졌는가, 못 했으면 까닭, 판정의 능력과 난이도와 피해, 맞을 쪽, 남은 개수다."""
    return {
        'entry_id': str(item.entry_id),
        'name': item.name,
        'thrown': reason is None,
        'reason': reason,
        'ability': check.ability,
        'difficulty': check.difficulty,
        'harm': check.harm,
        'target': target_of(judging, action),
        'remaining': items.count_of(member.sheet, action.item),
    }


def judge_throw(judging: Judging, member: TableMember, action: ThrowAction) -> dict:
    """
    물건 하나를 던진다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다.

    던졌으면 치기의 결과(판정, 피해, 방어, 드롭)에 item_throw 를 더한다. 못 던졌으면 item_throw 만 있다.
    겨눈 몬스터가 없어 못 던졌으면 치기와 같은 target_gone 도 있다.
    """
    item = judging.items[action.item]
    check = to_check(judging, item, action)
    if items.count_of(member.sheet, action.item) < 1:
        return {'item_throw': throw_document(judging, member, item, action, check, Reason.NOT_HELD)}
    gone = target_gone(judging, member, check)
    if gone is not None:
        document = throw_document(judging, member, item, action, check, Reason.TARGET_GONE)
        return {'item_throw': document, 'target_gone': gone}
    items.remove_items(member.sheet, action.item, 1)
    outcome = judge_check(judging, member, check)
    return {**outcome, 'item_throw': throw_document(judging, member, item, action, check, None)}
