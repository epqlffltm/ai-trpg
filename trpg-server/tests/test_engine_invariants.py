# trpg-server/tests/test_engine_invariants.py

"""
엔진의 불변 조건을 무작위 입력으로 검증한다(#812). Hypothesis 의 상태 기계 시험이다.

예시로 고른 몇 가지 대신, 무작위로 고른 행동의 열을 엔진의 순수 함수에 차례로 넣는다. 단계마다 불변 조건을 본다.
실패하면 Hypothesis 가 실패를 내는 가장 짧은 열로 줄여 보여 준다. DB 가 붙는 부분(라운드 닫기, 차례)은 다음 일이다.

캐릭터 한 명을 DB 없이 굴린다. 기계는 셋이다. 하나에 모두 넣으면 고를 규칙이 많아,
한 갈래(죽음의 굴림을 끝까지 가기 같은)에 깊이 들어가는 열이 드물어진다.
  - HealthMachine: HP 와 죽음의 굴림(app/engine/health.py, app/engine/death.py). 규칙은 SRD 5 템플릿이다.
  - BelongingsMachine: 메모리의 시트(TableSheet)의 소지품, 착용, 돈(app/tables/items.py, app/tables/equipment.py,
    app/tables/money.py).
  - ResourceMachine: 수치(app/engine/resources.py). 규칙은 가벼운 템플릿(마나, 스태미나)이다.

불변 조건.
  - HP 는 0 이상, 최대 HP 이하다. 피해는 HP 를 올리지 않고 회복은 내리지 않는다.
    장난의 피해는 HP 1 아래로 내리지 않는다.
  - 죽음의 굴림: 센 성공과 실패는 규칙의 수를 넘지 않는다. 죽음은 되돌리지 못한다(죽은 뒤에는 굴리지 않고 죽은 채다).
  - 소지품: 한 가지는 한 줄이고, 0 개인 줄은 없고, 99 개(ITEM_STACK_MAX)를 넘지 않는다. 착용은 가진 개수를 넘지 않는다.
    거절된 주기와 빼기는 아무것도 바꾸지 않는다. 엔진의 개수는 따로 센 개수와 늘 같다.
  - 돈: 0 이상, MONEY_MAX 이하다. 거절은 아무것도 바꾸지 않는다.
  - 수치: 최소와 최대 사이다.
  - 같은 눈이면 판정과 HP 의 변화가 같다(엔진은 받은 것과 주사위만 보고 정한다).
"""

import uuid

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, precondition, rule

from app.assets.models import ITEM_STACK_MAX, MONEY_MAX
from app.engine.check import find_difficulty, resolve_hindered
from app.engine.death import Fate, add_failures, fate_of, roll_death_save
from app.engine.dice import ScriptedDice
from app.engine.health import PRANK_FLOOR, ChangeKind, Nature, change_hp, find_magnitude, spare
from app.engine.injury import Hindrance
from app.engine.resources import adjusted, level_of, shifted
from app.engine.ruleset import ResistLevel, ResourceShift, ResourceShiftKind
from app.engine.templates import from_template
from app.tables import items, money
from app.tables.equipment import worn_of
from app.tables.errors import TableConflictError
from app.tables.models import TableSheet, TableWorn

SRD = from_template('srd5')
LIGHT = from_template('light')
TABLE = uuid.UUID('00000000-0000-4000-8000-000000000001')
# 물건 세 가지. 무작위 열이 같은 물건을 자주 고르도록 적게 둔다
THINGS = [uuid.UUID(f'00000000-0000-4000-8000-00000000001{n}') for n in range(3)]
MAX_HP = 12

magnitudes = st.sampled_from(SRD.magnitudes)
levels = st.sampled_from([None, ResistLevel.RESIST, ResistLevel.IMMUNE, ResistLevel.VULNERABLE])
# 작은 수를 자주 고르고 상한 근처와 넘는 수도 고른다
counts = st.one_of(st.integers(min_value=1, max_value=5), st.integers(min_value=1, max_value=ITEM_STACK_MAX + 20))
amounts = st.one_of(st.integers(min_value=1, max_value=50), st.integers(min_value=1, max_value=MONEY_MAX + 1000))
shifts = st.one_of(
    st.builds(ResourceShift, kind=st.sampled_from([ResourceShiftKind.FILL, ResourceShiftKind.EMPTY])),
    st.builds(
        ResourceShift,
        kind=st.sampled_from([ResourceShiftKind.RAISE, ResourceShiftKind.LOWER]),
        amount=st.integers(min_value=1, max_value=20),
    ),
)


def rolls_for(data, magnitude) -> list[int]:
    """그 등급이 굴릴 눈들을 무작위로 고른다."""
    return [data.draw(st.integers(min_value=1, max_value=magnitude.sides)) for _ in range(magnitude.count)]


def rolled_change(kind: ChangeKind, magnitude, hp: int, rolls: list[int], cut: int = 0, nature=None):
    """정한 눈으로 HP 를 한 번 바꾼다. 눈을 다 썼는지 본다."""
    dice = ScriptedDice(rolls)
    change = change_hp(kind, magnitude, hp, MAX_HP, dice, cut=cut, nature=nature)
    assert dice.remaining == 0
    return change


class HealthMachine(RuleBasedStateMachine):
    """캐릭터 한 명의 HP 와 죽음의 굴림을 무작위 열로 굴린다."""

    def __init__(self) -> None:
        super().__init__()
        self.hp = MAX_HP
        self.successes = 0
        self.failures = 0
        self.dead = False

    @precondition(lambda self: not self.dead)
    @rule(
        data=st.data(),
        magnitude=magnitudes,
        cut=st.integers(min_value=0, max_value=10),
        level=levels,
        prank=st.booleans(),
    )
    def take_damage(self, data, magnitude, cut: int, level, prank: bool) -> None:
        nature = Nature(key='fire', level=level) if level is not None else None
        change = rolled_change(ChangeKind.DAMAGE, magnitude, self.hp, rolls_for(data, magnitude), cut, nature)
        if prank:
            change = spare(change)
            assert change.after >= min(self.hp, PRANK_FLOOR)
        assert change.before == self.hp
        assert change.after <= self.hp
        assert change.blocked <= cut
        self.hp = change.after

    @precondition(lambda self: not self.dead)
    @rule(data=st.data(), magnitude=magnitudes)
    def recover(self, data, magnitude) -> None:
        change = rolled_change(ChangeKind.RECOVERY, magnitude, self.hp, rolls_for(data, magnitude))
        assert change.after >= self.hp
        self.hp = change.after
        if self.hp > 0:
            # 일어나면 죽음의 굴림을 처음부터 센다(app/rounds 가 하는 것과 같다)
            self.successes = self.failures = 0

    @precondition(lambda self: self.hp == 0)
    @rule(roll=st.integers(min_value=1, max_value=SRD.die))
    def roll_death(self, roll: int) -> None:
        dice = ScriptedDice([roll])
        rolled = roll_death_save(SRD, self.successes, self.failures, dice)
        if rolled is None:
            # 갈림길이 이미 정해졌다. 주사위를 건드리지 않는다
            assert dice.remaining == 1
            assert fate_of(SRD.death_save, self.successes, self.failures) != Fate.DYING
            return
        self.successes, self.failures = rolled.successes, rolled.failures
        self.dead = rolled.fate == Fate.DEAD

    @precondition(lambda self: self.hp == 0)
    @rule(count=st.integers(min_value=1, max_value=3))
    def struck_while_down(self, count: int) -> None:
        struck = add_failures(SRD.death_save, self.successes, self.failures, count)
        assert struck.added >= 0
        if self.dead:
            assert struck.fate == Fate.DEAD
        self.failures = struck.failures
        self.dead = struck.fate == Fate.DEAD

    @invariant()
    def hp_stays_in_range(self) -> None:
        assert 0 <= self.hp <= MAX_HP

    @invariant()
    def death_counts_stay_in_range(self) -> None:
        death_save = SRD.death_save
        assert 0 <= self.successes <= death_save.successes
        assert 0 <= self.failures <= death_save.failures
        if self.dead:
            assert fate_of(death_save, self.successes, self.failures) == Fate.DEAD


class BelongingsMachine(RuleBasedStateMachine):
    """캐릭터 한 명의 소지품, 착용, 돈을 무작위 열로 굴린다. 엔진과 따로 센 개수와 돈을 함께 든다."""

    def __init__(self) -> None:
        super().__init__()
        self.sheet = TableSheet(items=[], worn=[], money=0)
        self.expected_items = {thing: 0 for thing in THINGS}
        self.expected_money = 0

    @rule(thing=st.sampled_from(THINGS), count=counts)
    def give(self, thing: uuid.UUID, count: int) -> None:
        before = self.snapshot()
        try:
            total = items.add_items(TABLE, self.sheet, thing, count)
        except TableConflictError:
            assert self.expected_items[thing] + count > ITEM_STACK_MAX
            assert self.snapshot() == before
            return
        self.expected_items[thing] += count
        assert total == self.expected_items[thing]

    @rule(thing=st.sampled_from(THINGS), count=counts)
    def reward(self, thing: uuid.UUID, count: int) -> None:
        given = items.add_up_to(TABLE, self.sheet, thing, count)
        assert 0 <= given <= count
        self.expected_items[thing] += given

    @rule(thing=st.sampled_from(THINGS), count=counts)
    def take_away(self, thing: uuid.UUID, count: int) -> None:
        before = self.snapshot()
        try:
            left = items.remove_items(self.sheet, thing, count)
        except TableConflictError:
            assert self.expected_items[thing] < count
            assert self.snapshot() == before
            return
        self.expected_items[thing] -= count
        assert left == self.expected_items[thing]

    @rule(thing=st.sampled_from(THINGS))
    def take_all(self, thing: uuid.UUID) -> None:
        """가진 것을 모두 뺀다. 착용한 것도 함께 없어져야 한다."""
        held = self.expected_items[thing]
        if held == 0:
            return
        assert items.remove_items(self.sheet, thing, held) == 0
        self.expected_items[thing] = 0

    @rule(thing=st.sampled_from(THINGS))
    def wear(self, thing: uuid.UUID) -> None:
        """하나 더 착용한다. 가진 개수만큼만 착용한다(app/tables/wearing.py 가 받을 때 막는 것)."""
        if len(worn_of(self.sheet, thing)) < items.count_of(self.sheet, thing):
            self.sheet.worn.append(TableWorn(table_id=TABLE, entry_id=thing, slots=['hand']))

    @rule(amount=amounts)
    def earn(self, amount: int) -> None:
        before = self.sheet.money
        try:
            money.add_money(self.sheet, amount)
        except TableConflictError:
            assert before + amount > MONEY_MAX
            assert self.sheet.money == before
            return
        self.expected_money += amount

    @rule(amount=amounts)
    def earn_up_to(self, amount: int) -> None:
        self.expected_money += money.add_up_to(self.sheet, amount)

    @rule(amount=amounts)
    def spend(self, amount: int) -> None:
        before = self.sheet.money
        try:
            money.remove_money(self.sheet, amount)
        except TableConflictError:
            assert amount > before
            assert self.sheet.money == before
            return
        self.expected_money -= amount

    def snapshot(self) -> tuple:
        """소지품과 착용의 지금. 거절이 아무것도 바꾸지 않았는지 볼 때 쓴다."""
        held = sorted((item.entry_id, item.count) for item in self.sheet.items)
        worn = sorted(row.entry_id for row in self.sheet.worn)
        return tuple(held), tuple(worn)

    @invariant()
    def items_stay_whole(self) -> None:
        entries = [item.entry_id for item in self.sheet.items]
        assert len(entries) == len(set(entries))
        assert all(1 <= item.count <= ITEM_STACK_MAX for item in self.sheet.items)
        assert {thing: items.count_of(self.sheet, thing) for thing in THINGS} == self.expected_items

    @invariant()
    def wearing_never_exceeds_holding(self) -> None:
        for thing in THINGS:
            assert len(worn_of(self.sheet, thing)) <= items.count_of(self.sheet, thing)

    @invariant()
    def money_stays_in_range(self) -> None:
        assert 0 <= self.sheet.money <= MONEY_MAX
        assert self.sheet.money == self.expected_money


class ResourceMachine(RuleBasedStateMachine):
    """캐릭터 한 명의 수치(마나, 스태미나)를 무작위 열로 굴린다."""

    def __init__(self) -> None:
        super().__init__()
        self.abilities: dict[str, int] = {}
        self.values: dict[str, int] = {}

    @initialize(heart=st.integers(min_value=-3, max_value=8), body=st.integers(min_value=-3, max_value=8))
    def set_abilities(self, heart: int, body: int) -> None:
        """가벼운 템플릿의 능력치(보정이 곧 점수다). 수치의 최대가 이것으로 정해진다."""
        self.abilities = {'heart': heart, 'body': body}

    @rule(resource=st.sampled_from(LIGHT.resources), shift=shifts)
    def rest(self, resource, shift: ResourceShift) -> None:
        level = level_of(LIGHT, resource, self.abilities, self.values)
        self.values[resource.key] = shifted(level, shift)

    @rule(resource=st.sampled_from(LIGHT.resources), amount=st.integers(min_value=-30, max_value=30))
    def adjust(self, resource, amount: int) -> None:
        level = level_of(LIGHT, resource, self.abilities, self.values)
        self.values[resource.key] = adjusted(level, amount)

    @invariant()
    def values_stay_in_range(self) -> None:
        for resource in LIGHT.resources:
            level = level_of(LIGHT, resource, self.abilities, self.values)
            stored = self.values.get(resource.key, level.value)
            assert resource.min <= stored <= level.maximum


MACHINE_SETTINGS = settings(
    max_examples=200, stateful_step_count=40, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
HealthMachine.TestCase.settings = MACHINE_SETTINGS
BelongingsMachine.TestCase.settings = MACHINE_SETTINGS
ResourceMachine.TestCase.settings = MACHINE_SETTINGS
TestHealth = HealthMachine.TestCase
TestBelongings = BelongingsMachine.TestCase
TestResources = ResourceMachine.TestCase


# --- 같은 눈이면 같은 결과 ---


@given(
    data=st.data(),
    score=st.integers(min_value=1, max_value=30),
    difficulty=st.sampled_from(SRD.difficulties),
    penalty=st.integers(min_value=0, max_value=5),
    disadvantage=st.booleans(),
    bonus=st.integers(min_value=-3, max_value=3),
)
@settings(deadline=None)
def test_the_same_rolls_give_the_same_check(data, score, difficulty, penalty, disadvantage, bonus):
    hindrance = Hindrance(penalty=penalty, disadvantage=disadvantage)
    rolls = [data.draw(st.integers(min_value=1, max_value=SRD.die)) for _ in range(2 if disadvantage else 1)]

    first = resolve_hindered(SRD, score, difficulty, ScriptedDice(rolls), hindrance, bonus=bonus)
    again = resolve_hindered(SRD, score, difficulty, ScriptedDice(rolls), hindrance, bonus=bonus)

    assert first == again
    assert first.check.roll == min(rolls)
    assert first.check.success == (first.check.total >= difficulty.target)


@given(data=st.data(), magnitude=magnitudes, hp=st.integers(min_value=0, max_value=MAX_HP), level=levels)
@settings(deadline=None)
def test_the_same_rolls_give_the_same_change(data, magnitude, hp, level):
    rolls = rolls_for(data, magnitude)
    nature = Nature(key='fire', level=level) if level is not None else None

    first = rolled_change(ChangeKind.DAMAGE, magnitude, hp, rolls, nature=nature)
    again = rolled_change(ChangeKind.DAMAGE, magnitude, hp, rolls, nature=nature)

    assert first == again


def test_the_templates_have_what_the_machine_uses():
    """시험이 기대는 규칙의 모양. 템플릿이 바뀌면 여기서 먼저 알린다."""
    assert SRD.death_save is not None
    assert find_magnitude(SRD, 'light') is not None
    assert find_difficulty(SRD, None) is not None
    assert {resource.key for resource in LIGHT.resources} == {'mana', 'stamina'}
