# trpg-server/app/tables/resources.py

"""
시트의 수치(#804, table_sheets.resources)를 읽고 바꾼다. 계산은 app/engine/resources.py 에 있다.

시트를 받을 때 값을 채우지 않는다. 적히지 않은 이름표는 시작 값으로 읽는다(능력치가 바뀌지 않아 늘 같은 값이다).
바뀔 때만 적는다. 바꾸는 것은 엔진뿐이다(쉬기, 물건의 맞추기).

DB 를 모른다. 시트를 고친다. 저장하지 않는다.
"""

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


def rest(ruleset: Ruleset, sheet: TableSheet, long: bool) -> list[Shift]:
    """
    휴식 하나가 수치들에 하는 일(규칙의 resources[].rest). 바뀐 것만 돌려준다. 규칙의 차례다.

    그 휴식에 하는 일이 없거나, 해도 값이 같으면(이미 가득) 적지 않는다.
    """
    shifts = []
    for level in levels_of(ruleset, sheet):
        shift: ResourceShift | None = level.resource.rest.long if long else level.resource.rest.short
        if shift is None:
            continue
        after = engine.shifted(level, shift)
        if after != level.value:
            shifts.append(write(sheet, level, after))
    return shifts


def shift_document(shift: Shift) -> dict:
    """바뀐 것을 결과와 이벤트에 적을 모양. 이름표, 이름, 전과 뒤의 값, 최대다."""
    return {
        'resource': shift.resource.key,
        'name': shift.resource.name,
        'before': shift.before,
        'after': shift.after,
        'max': shift.maximum,
    }
