# game-server/app/rounds/place_item_actions.py

"""
장소에 놓인 물건을 줍고(take) 찾는(search) 일(#279). 선언을 받을 때 보고(accept_take), 라운드가 닫힐 때 정한다.

방장은 PC 라서 얻는 것을 정하지 않는다(#367). 판에 놓인 물건을 엔진이 준다.
  - 줍기: 지금 서 있는 장소에 보이게 놓인 물건을 count 개 가져간다. 판정이 없다.
    받을 때 그 장소에 보이게 남아 있는지 보고, 차례가 오면 다시 본다. 그사이 앞사람이 가져갔을 수 있다.
    남은 것보다 많이 불렀으면 남은 만큼, 한 가지의 상한(99)에 닿으면 거기까지 줍는다. 못 주운 것은 그 자리에 남는다.
  - 찾기(숨긴 물건): 찾기 행동이 숨긴 길과 함께 이 장소의 숨긴 물건마다 판의 판정을 굴린다(app/rounds/map_actions.py).
    찾으면 찾은 사람이 바로 갖는다. 상한을 넘어 남은 것은 그 자리에 보이는 물건으로 남는다.
    **찾지 못한 판정은 아무 데도 적지 않는다.** 숨긴 길과 같다. 숨긴 물건이 있었는지 드러나지 않는다.
맵에 서 있지 않은 캐릭터는 줍지 못한다(not_on_map).

DB 를 모른다. 남은 개수(app/tables/place_items.py)와 소지품을 고친다. 저장하지 않는다.
"""

from app.assets.scenarios.snapshot import PlaceItemSnapshot
from app.engine.action import TakeAction
from app.engine.check import find_difficulty, resolve_hindered
from app.rounds import injuries as round_injuries
from app.rounds.effects import Judging
from app.rounds.errors import ActionTargetError
from app.rounds.map_actions import standing_place
from app.tables import items, place_items, places
from app.tables.models import GameTable, TableMember, TablePlaceItem


class Source:
    """장소에서 얻은 물건의 출처. items_gained 이벤트의 source 에 적는다. 몬스터의 드롭은 monster 다."""

    # 보이게 놓인 물건을 주웠다
    PLACE = 'place'
    # 숨긴 물건을 찾았다
    SEARCH = 'search'


class Reason:
    """주운 것이 부른 것보다 적은 까닭. 결과의 reason 에 적는다."""

    # 차례가 왔을 때 그 물건이 하나도 남아 있지 않았다(앞사람이 가져갔다)
    GONE = 'gone'
    # 남은 것이 부른 것보다 적었다. 남은 만큼 주웠다
    NOT_ENOUGH = 'not_enough'
    # 한 가지를 가질 수 있는 개수(99)에 닿았다. 그만큼만 주웠다
    FULL = 'full'


def accept_take(table: GameTable, member: TableMember, action: TakeAction) -> dict:
    """
    줍는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다.

      - 맵에 서 있지 않으면 RoundConflictError(not_on_map).
      - 그 장소에 보이게 남아 있는 물건이 아니면 ActionTargetError(item).
        숨긴 물건, 다른 장소의 물건, 없는 물건을 가르지 않는다. 가르면 숨긴 물건이 드러난다.
    """
    here = standing_place(member)
    if place_items.available(table, here, action.item) == 0:
        raise ActionTargetError('item')
    return action.model_dump(mode='json')


def shortfall(asked: int, left: int, taken: int) -> str | None:
    """주운 것이 부른 것보다 적은 까닭. 다 주웠으면 None."""
    if taken == asked:
        return None
    if left == 0:
        return Reason.GONE
    if taken < min(asked, left):
        return Reason.FULL
    return Reason.NOT_ENOUGH


def judge_take(judging: Judging, member: TableMember, action: TakeAction) -> dict:
    """
    차례가 온 사람이 줍는다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다.

    count 는 부른 개수, taken 은 주운 개수, total 은 주운 뒤의 개수다. 다 줍지 못했으면 까닭(reason)이 있다.
    """
    table, here = judging.table, member.sheet.place_id
    left = place_items.available(table, here, action.item) if here is not None else 0
    taken = items.add_up_to(table.id, member.sheet, action.item, min(action.count, left)) if left else 0
    if taken:
        place_items.take_from(table, here, action.item, taken)
    return {
        'take': {
            'user_id': str(member.user_id),
            'character_name': member.character_name,
            'place': places.describe(judging.snapshot, here),
            'entry_id': str(action.item),
            'name': judging.items[action.item].name,
            'count': action.count,
            'taken': taken,
            'total': items.count_of(member.sheet, action.item),
            'reason': shortfall(action.count, left, taken),
        }
    }


def finds_item(judging: Judging, member: TableMember, rule: PlaceItemSnapshot) -> bool:
    """
    숨긴 물건 한 줄을 찾는 판정을 굴린다. 찾았는가.

    숨긴 길과 같다. 판에 적힌 능력과 난이도(비웠으면 규칙의 기본 난이도)로 굴리고 입은 부상의 영향을 받는다.
    판에 굳을 때 규칙에 있는 능력과 난이도인지 봤다(게시의 place_item_find_invalid).
    """
    ruleset, sheet = judging.ruleset, member.sheet
    difficulty = find_difficulty(ruleset, rule.find.difficulty)
    hindrance = round_injuries.hindrance_for(ruleset, sheet.injuries, rule.find.ability)
    score = sheet.abilities[rule.find.ability]
    return resolve_hindered(ruleset, score, difficulty, judging.dice, hindrance).check.success


def keep_found(judging: Judging, member: TableMember, row: TablePlaceItem) -> dict:
    """
    찾은 숨긴 물건 한 줄을 찾은 사람이 갖는다. 상한까지만 갖고 남은 것은 그 자리에 보이게 둔다. 문서로 돌려준다.

    count 는 가진 개수, left 는 그 자리에 남은 개수, total 은 가진 뒤의 개수다.
    """
    kept = items.add_up_to(judging.table.id, member.sheet, row.entry_id, row.count)
    left = place_items.uncover(row, kept)
    return {
        'entry_id': str(row.entry_id),
        'name': judging.items[row.entry_id].name,
        'count': kept,
        'left': left,
        'total': items.count_of(member.sheet, row.entry_id),
    }


def search_items(judging: Judging, member: TableMember) -> list[dict]:
    """
    지금 장소의 숨긴 물건마다 찾는 판정을 굴린다. 찾은 것을 찾은 사람이 갖는다. 찾은 것만 문서로 돌려준다.

    같은 라운드에 앞사람이 먼저 찾은 줄은 이미 보이는 줄이라 다시 굴리지 않는다.
    """
    here = member.sheet.place_id
    if here is None:
        return []
    rules = judging.snapshot.place_items
    return [
        keep_found(judging, member, row)
        for row in place_items.hidden_rows(judging.table, here)
        if finds_item(judging, member, rules[row.slot])
    ]
