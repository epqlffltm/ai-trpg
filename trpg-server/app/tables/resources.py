# trpg-server/app/tables/resources.py

"""
시트의 수치(#804, table_sheets.resources)를 읽고 바꾼다. 계산은 app/engine/resources.py 에 있다.

시트를 받을 때 값을 채우지 않는다. 적히지 않은 이름표는 시작 값으로 읽는다(능력치가 바뀌지 않아 늘 같은 값이다).
바뀔 때만 적는다. 바꾸는 것은 엔진뿐이다(쉬기, 물건의 맞추기, 라운드마다의 변화).

DB 를 모른다. 시트를 고친다. 저장하지 않는다.
"""

import uuid
from collections.abc import Callable

from app.engine import resources as engine
from app.engine.resources import Level, Shift
from app.engine.ruleset import Resource, ResourceShift, Ruleset
from app.tables.models import TableSheet


def levels_of(ruleset: Ruleset, sheet: TableSheet) -> list[Level]:
    """이 시트의 수치들의 지금. 규칙의 차례다."""
    return engine.levels(ruleset, sheet.abilities, sheet.resources or {})


def level_of(ruleset: Ruleset, sheet: TableSheet, resource: Resource) -> Level:
    """이 시트의 수치 하나의 지금."""
    return engine.level_of(ruleset, resource, sheet.abilities, sheet.resources or {})


def write(sheet: TableSheet, level: Level, after: int) -> Shift:
    """
    수치 하나를 after 로 적고, 바뀐 것을 돌려준다.

    새 묶음으로 바꿔 끼운다. 안을 고치면 DB 의 JSON 칸이 바뀐 줄 모른다.
    """
    sheet.resources = {**(sheet.resources or {}), level.resource.key: after}
    return engine.shift_of(level, after)


def adjust(ruleset: Ruleset, sheet: TableSheet, key: str, amount: int) -> Shift | None:
    """물건의 맞추기(adjust). 그 수치를 amount 만큼 올리거나 내린다. 규칙에 없는 수치면 None(게시할 때 막았다)."""
    resource = engine.find_resource(ruleset, key)
    if resource is None:
        return None
    level = level_of(ruleset, sheet, resource)
    return write(sheet, level, engine.adjusted(level, amount))


def apply_shifts(ruleset: Ruleset, sheet: TableSheet, pick: Callable[[Resource], ResourceShift | None]) -> list[Shift]:
    """
    수치마다 pick 이 고른 변화를 한다. 바뀐 것만 돌려준다. 규칙의 차례다.

    고른 변화가 없거나, 해도 값이 같으면(이미 가득) 적지 않는다.
    """
    shifts = []
    for level in levels_of(ruleset, sheet):
        shift = pick(level.resource)
        if shift is None:
            continue
        after = engine.shifted(level, shift)
        if after != level.value:
            shifts.append(write(sheet, level, after))
    return shifts


def rest(ruleset: Ruleset, sheet: TableSheet, long: bool) -> list[Shift]:
    """휴식 하나가 수치들에 하는 일(규칙의 resources[].rest). 바뀐 것만 돌려준다."""
    return apply_shifts(ruleset, sheet, lambda resource: resource.rest.long if long else resource.rest.short)


def each_round(ruleset: Ruleset, sheet: TableSheet) -> list[Shift]:
    """라운드가 닫힐 때 수치들이 저절로 하는 일(규칙의 resources[].each_round, #804). 바뀐 것만 돌려준다."""
    return apply_shifts(ruleset, sheet, lambda resource: resource.each_round)


def wanted_injuries(ruleset: Ruleset, sheet: TableSheet) -> list[str]:
    """이 시트의 수치들이 지금 닿아 있는 문턱의 부상들(#804). 규칙의 차례다."""
    return engine.wanted_injuries(levels_of(ruleset, sheet))


def shift_document(shift: Shift, owner_id: uuid.UUID) -> dict:
    """
    바뀐 것을 결과와 이벤트에 적을 모양. 이름표, 이름, 전과 뒤의 값, 최대, 그리고 최소다.

    누구의 수치인지(user_id)와 누가 보는지(visibility, #804)도 적는다. 응답이 보는 사람에 따라 거른다(visible_shifts).
    서술은 거르지 않고 읽어, 숨긴 것은 말로 바꾼다.
    """
    return {
        'resource': shift.resource.key,
        'name': shift.resource.name,
        'before': shift.before,
        'after': shift.after,
        'max': shift.maximum,
        'min': shift.resource.min,
        'user_id': str(owner_id),
        'visibility': shift.resource.visibility.value,
    }


def visible_shifts(shifts: list[dict] | None, viewer_id: uuid.UUID) -> list[dict]:
    """
    결과에 적힌 바뀐 수치들 중 그 사람이 숫자로 보는 것만. 보이기가 없는 옛 문서는 모두에게 보인다.

    결과는 테이블의 앉은 사람 모두가 읽는다. 가진 사람만 보는 수치는 그 사람에게만 싣고,
    엔진만 보는 것은 아무에게도 싣지 않는다.
    """
    return [
        shift
        for shift in shifts or []
        if engine.shown_to(shift.get('visibility', 'everyone'), shift.get('user_id') == str(viewer_id))
    ]
