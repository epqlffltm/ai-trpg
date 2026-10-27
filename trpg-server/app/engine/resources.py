# trpg-server/app/engine/resources.py

"""
HP 말고 캐릭터가 가지는 수치(#804)의 계산. 마나, 스태미나, 광기 같은 것이다.

수치가 무엇인지는 규칙의 데이터다(app/engine/ruleset.py 의 Resource). 엔진이 하는 일은 다섯이다.
  - 최대: 기준값(base)에 능력치의 보정을 더하고 상한(cap)을 넘지 않는다. 최소보다 작아지지 않는다.
  - 시작: 시트를 받을 때 최대나 최소로 둔다.
  - 쉬기: 짧은 휴식과 긴 휴식이 올리거나 내리거나 채우거나 비운다. 라운드가 닫힐 때마다도 같은 모양으로 바뀔 수 있다.
  - 맞추기(adjust): 물건의 효과가 그만큼 올리거나 내린다.
  - 문턱: 값이 최소나 최대에 닿아 있으면 규칙이 정한 부상을 입는다(그 부상의 이름표를 낸다).
누가 숫자를 보는지(visibility)도 여기서 정한다. 숨긴 수치는 숫자 대신 네 단계의 말(band_of)로 전한다.
값은 늘 최소와 최대 사이다. 지금 값은 시트에 이름표에서 값으로 적힌다(table_sheets.resources).
시트에 없는 이름표(이 칸이 생기기 전의 시트)는 시작 값으로 읽는다.

여기의 함수는 DB 도 HTTP 도 모른다. 규칙과 능력치와 지금 값을 받아 계산만 한다.
"""

from dataclasses import dataclass

from app.engine.check import modifier_of
from app.engine.ruleset import Resource, ResourceShift, ResourceShiftKind, ResourceStart, ResourceVisibility, Ruleset


@dataclass(frozen=True)
class Level:
    """수치 하나의 지금. 규칙의 수치와 값과 최대다. 최소는 resource.min 이다."""

    resource: Resource
    value: int
    maximum: int


@dataclass(frozen=True)
class Shift:
    """수치 하나가 바뀐 것. 바뀌기 전과 뒤의 값과 최대다."""

    resource: Resource
    before: int
    after: int
    maximum: int


def find_resource(ruleset: Ruleset, key: str) -> Resource | None:
    """규칙에서 수치를 찾는다. 없으면 None."""
    return next((resource for resource in ruleset.resources if resource.key == key), None)


def maximum_of(ruleset: Ruleset, resource: Resource, abilities: dict[str, int]) -> int:
    """
    이 캐릭터의 그 수치의 최대. 기준값에 능력치의 보정을 더하고 상한을 넘지 않는다. 최소보다 작지 않다.

    능력치의 점수가 시트에 없으면(규칙이 바뀐 판) 보정 없이 기준값이다.
    """
    value = resource.max.base
    if resource.max.ability is not None and resource.max.ability in abilities:
        value += modifier_of(ruleset, abilities[resource.max.ability])
    if resource.max.cap is not None:
        value = min(value, resource.max.cap)
    return max(value, resource.min)


def clamp(value: int, resource: Resource, maximum: int) -> int:
    """최소와 최대 사이로."""
    return max(resource.min, min(value, maximum))


def start_of(resource: Resource, maximum: int) -> int:
    """시작 값. 가득이면 최대, 비운 채면 최소다."""
    return maximum if resource.start == ResourceStart.MAX else resource.min


def starting_values(ruleset: Ruleset, abilities: dict[str, int]) -> dict[str, int]:
    """시트를 받을 때의 값들. 이름표에서 값으로. 규칙의 차례다."""
    return {
        resource.key: start_of(resource, maximum_of(ruleset, resource, abilities)) for resource in ruleset.resources
    }


def level_of(ruleset: Ruleset, resource: Resource, abilities: dict[str, int], values: dict) -> Level:
    """지금의 그 수치. 적힌 값이 없으면 시작 값이다. 범위 밖으로 적혀 있으면(최대가 바뀌었다) 범위 안으로 읽는다."""
    maximum = maximum_of(ruleset, resource, abilities)
    stored = values.get(resource.key)
    value = start_of(resource, maximum) if stored is None else clamp(stored, resource, maximum)
    return Level(resource=resource, value=value, maximum=maximum)


def levels(ruleset: Ruleset, abilities: dict[str, int], values: dict) -> list[Level]:
    """이 캐릭터의 수치들의 지금. 규칙의 차례다."""
    return [level_of(ruleset, resource, abilities, values) for resource in ruleset.resources]


def shifted(level: Level, shift: ResourceShift) -> int:
    """쉬기 하나가 한 뒤의 값. 범위 밖으로 가지 않는다."""
    if shift.kind == ResourceShiftKind.FILL:
        return level.maximum
    if shift.kind == ResourceShiftKind.EMPTY:
        return level.resource.min
    step = shift.amount if shift.kind == ResourceShiftKind.RAISE else -shift.amount
    return clamp(level.value + step, level.resource, level.maximum)


def adjusted(level: Level, amount: int) -> int:
    """물건의 맞추기(adjust) 뒤의 값. amount 만큼 올리거나(양수) 내린다(음수). 범위 밖으로 가지 않는다."""
    return clamp(level.value + amount, level.resource, level.maximum)


def shift_of(level: Level, after: int) -> Shift:
    """바뀐 것의 모양."""
    return Shift(resource=level.resource, before=level.value, after=after, maximum=level.maximum)


def thresholds_of(level: Level) -> list[str]:
    """
    이 수치가 지금 닿아 있는 문턱의 부상들(#804). 최소에 닿았으면 at_min, 최대에 닿았으면 at_max 다.

    능력치의 보정이 낮아 최대가 최소와 같으면 둘 다 닿아 있다. 문턱에 부상이 없으면 빈 목록이다.
    """
    touched = []
    if level.resource.at_min is not None and level.value <= level.resource.min:
        touched.append(level.resource.at_min)
    if level.resource.at_max is not None and level.value >= level.maximum:
        touched.append(level.resource.at_max)
    return touched


def wanted_injuries(levels_now: list[Level]) -> list[str]:
    """수치들이 지금 입혀야 할 부상들. 규칙의 차례이고 같은 부상은 한 번이다."""
    wanted: list[str] = []
    for level in levels_now:
        wanted.extend(key for key in thresholds_of(level) if key not in wanted)
    return wanted


# 숨긴 수치를 말로 전하는 네 단계(#804). 가득 → 넉넉함 → 모자람 → 바닥
BAND_FULL = '가득'
BAND_PLENTY = '넉넉함'
BAND_LOW = '모자람'
BAND_EMPTY = '바닥'


def band_of(value: int, minimum: int, maximum: int) -> str:
    """
    값을 네 단계의 말로. 최대면 가득, 최소면 바닥, 그 사이는 범위의 절반 이상이면 넉넉함, 아래면 모자람이다.

    숫자를 서술에 흘리지 않으려는 것이다. 몇인지가 아니라 어느 쪽에 가까운지만 전한다.
    """
    if value >= maximum:
        return BAND_FULL
    if value <= minimum:
        return BAND_EMPTY
    return BAND_PLENTY if (value - minimum) * 2 >= maximum - minimum else BAND_LOW


def is_open(resource: Resource) -> bool:
    """앉은 사람 모두가 숫자를 보는 수치인가."""
    return resource.visibility == ResourceVisibility.EVERYONE


def is_recorded(resource: Resource) -> bool:
    """바뀐 것을 이벤트에 적는 수치인가. 엔진만 보는 것은 적지 않는다."""
    return resource.visibility != ResourceVisibility.ENGINE


def shown_to(visibility: str, is_owner: bool) -> bool:
    """이 보이기의 수치를 그 사람이 숫자로 보는가. 모두면 늘, 가진 사람만이면 그 사람만, 엔진만이면 아무도 아니다."""
    if visibility == ResourceVisibility.EVERYONE:
        return True
    return visibility == ResourceVisibility.OWNER and is_owner
