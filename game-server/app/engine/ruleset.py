# game-server/app/engine/ruleset.py

"""
규칙의 모양. 규칙은 코드가 아니라 데이터다.

어떤 능력치가 있는지, 주사위가 몇 면인지, 난이도가 몇 단계인지, 피해와 회복이 얼마인지,
캐릭터의 숫자를 어떻게 정하는지, 쓰러진 캐릭터가 어떻게 죽는지, 어떤 부상이 언제 생기는지를 한 묶음(Ruleset)에 담는다.
엔진은 이 묶음을 인자로 받는다. 묶음의 값이 달라져도 엔진의 코드는 그대로다.

규칙은 룰북에 담기고(app/assets/models.py 의 Rulebook.rules), 게시할 때 판에 굳는다.
DB 에는 문서(JSON)로 들어간다. DB 는 문서의 안을 검증하지 못한다.
그래서 쓰는 쪽과 읽는 쪽이 모두 이 파일의 모양을 거친다. 이 파일이 규칙의 계약이다.

바꿀 수 있는 것은 값이다. 계산하는 방식(주사위 + 보정이 난이도 이상이면 성공)은 엔진의 코드에 있다.
"""

import enum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# 규칙 하나에 둘 수 있는 능력치, 난이도, 양의 등급의 수. 시트와 화면이 감당할 수 있는 만큼이다
RULESET_MAX_ABILITIES = 12
RULESET_MAX_DIFFICULTIES = 10
RULESET_MAX_MAGNITUDES = 10
# 능력치의 점수와 난이도의 목표값이 가질 수 있는 가장 큰 값
RULESET_MAX_NUMBER = 1000
# 주사위의 면 수
RULESET_MIN_DIE = 2
RULESET_MAX_DIE = 100
# 피해나 회복 한 번에 굴리는 주사위의 개수
RULESET_MAX_DICE = 10
# 점수제의 값표에 둘 수 있는 줄의 수
RULESET_MAX_POINT_COSTS = 30
# 죽음의 굴림에서 모아야 하는 성공과 실패의 수
RULESET_MAX_DEATH_SAVES = 10
# 규칙 하나에 둘 수 있는 부상의 수, 부상 하나의 효과의 수, 부상 표의 줄의 수
RULESET_MAX_INJURIES = 30
RULESET_MAX_EFFECTS = 5
RULESET_MAX_TABLE_ROWS = 20
# 부상이 서술에 주는 사실의 길이. 라운드마다 AI 의 입력에 들어간다
INJURY_FACT_MAX_LENGTH = 200
# 부상이 풀리거나 나을 때까지의 라운드 수
RULESET_MAX_INJURY_ROUNDS = 1000

# 코드와 데이터가 서로를 가리킬 때 쓰는 이름. 영어 소문자로 시작하고, 소문자와 숫자와 밑줄만 쓴다
Key = Annotated[str, StringConstraints(pattern=r'^[a-z][a-z0-9_]*$', max_length=20)]
# 사람에게 보여 주는 이름
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
Number = Annotated[int, Field(ge=0, le=RULESET_MAX_NUMBER)]


class Part(BaseModel):
    """
    규칙을 이루는 조각의 공통 설정. 만든 뒤에 고치지 못하고, 모르는 칸을 받지 않는다.

    목록은 list 가 아니라 tuple 로 둔다. frozen 은 칸을 바꿔 끼우는 것만 막고, list 에 더하는 것은 못 막는다.
    """

    model_config = ConfigDict(frozen=True, extra='forbid')


class Ability(Part):
    """능력치 하나. 예: 근력."""

    key: Key
    name: Name


class Difficulty(Part):
    """난이도 한 단계. 예: 보통(15)."""

    key: Key
    name: Name
    # 주사위와 보정을 더한 값이 이 값 이상이면 성공이다
    target: Annotated[int, Field(ge=1, le=RULESET_MAX_NUMBER)]


class Modifier(Part):
    """
    능력치의 점수를 판정에 더하는 값(보정)으로 바꾸는 방법.

    보정 = (점수 - base) // step. 내림한다.
    base 10, step 2 이면 점수 14 는 +2, 점수 9 는 -1 이다.
    base 0, step 1 이면 점수가 그대로 보정이다.
    """

    base: Number
    step: Annotated[int, Field(ge=1, le=RULESET_MAX_NUMBER)]


class Magnitude(Part):
    """
    피해와 회복의 양을 나타내는 등급 하나. 예: 가벼움(1d4).

    양은 주사위로 정한다. count 개의 sides 면 주사위를 굴려 더한다. count 2, sides 8 이면 2d8 이다.
    피해와 회복이 같은 등급을 쓴다. 가벼운 피해도 가벼운 회복도 1d4 다.
    """

    key: Key
    name: Name
    count: Annotated[int, Field(ge=1, le=RULESET_MAX_DICE)]
    sides: Annotated[int, Field(ge=RULESET_MIN_DIE, le=RULESET_MAX_DIE)]


def find_duplicates(keys: list[str]) -> list[str]:
    """두 번 이상 나온 이름을 처음 나온 순서대로 돌려준다."""
    seen: set[str] = set()
    duplicates: list[str] = []
    for key in keys:
        if key in seen and key not in duplicates:
            duplicates.append(key)
        seen.add(key)
    return duplicates


class PointCost(Part):
    """점수제의 값표 한 줄. 이 점수를 고르는 데 드는 값이다. 예: 점수 14 는 7."""

    score: Number
    cost: Number


class PointBuy(Part):
    """
    점수제. 정해진 총점 안에서 능력치의 점수를 사는 방식이다.

    고를 수 있는 점수는 값표에 있는 것뿐이다. 값표에 없는 점수는 살 수 없다.
    높은 점수일수록 비싸게 매길 수 있다. 값이 점수에 비례하지 않아도 된다.
    """

    # 쓸 수 있는 총점. 다 쓰지 않아도 된다
    budget: Annotated[int, Field(ge=1, le=RULESET_MAX_NUMBER)]
    costs: Annotated[tuple[PointCost, ...], Field(min_length=1, max_length=RULESET_MAX_POINT_COSTS)]

    @model_validator(mode='after')
    def reject_duplicate_scores(self) -> Self:
        """같은 점수가 값표에 두 번 있으면 그 점수의 값이 무엇인지 알 수 없다."""
        scores = [entry.score for entry in self.costs]
        if len(set(scores)) != len(scores):
            raise ValueError('값표에 같은 점수가 두 번 있습니다.')
        return self


class ScoreRoll(Part):
    """
    능력치의 점수 하나를 주사위로 정하는 법. 예: 4d6 을 굴려 높은 셋을 더한다.

    count 개의 sides 면 주사위를 굴려, 높은 것부터 keep 개를 더한 값이 점수 하나다.
    이것을 능력치의 수만큼 되풀이한다. 능력치가 여섯이면 점수 여섯이 나온다.
    """

    count: Annotated[int, Field(ge=1, le=RULESET_MAX_DICE)]
    sides: Annotated[int, Field(ge=RULESET_MIN_DIE, le=RULESET_MAX_DIE)]
    # 더하는 주사위의 수. 굴린 것보다 많이 더할 수 없다
    keep: Annotated[int, Field(ge=1, le=RULESET_MAX_DICE)]

    @model_validator(mode='after')
    def reject_keeping_more_than_rolled(self) -> Self:
        """굴린 주사위보다 많이 더할 수는 없다."""
        if self.keep > self.count:
            raise ValueError('굴린 주사위보다 많이 더할 수 없습니다.')
        return self


class DeathSave(Part):
    """
    죽음의 굴림. 쓰러진 캐릭터가 죽는지를 주사위가 정하는 법이다.

    쓰러진 채로 라운드가 닫힐 때마다 규칙의 주사위(Ruleset.die)를 한 번 굴린다. 능력치의 보정은 더하지 않는다.
    눈이 target 이상이면 성공, 아니면 실패다. 성공과 실패를 따로 센다.
      - 실패가 failures 번 모이면 죽는다.
      - 성공이 successes 번 모이면 고비를 넘긴다. 더 굴리지 않는다. 쓰러진 채로 있고, 회복을 받으면 일어난다.
    회복을 받아 일어나면 센 것은 처음으로 돌아간다.
    """

    target: Annotated[int, Field(ge=1, le=RULESET_MAX_NUMBER)]
    successes: Annotated[int, Field(ge=1, le=RULESET_MAX_DEATH_SAVES)]
    failures: Annotated[int, Field(ge=1, le=RULESET_MAX_DEATH_SAVES)]


class EffectKind(enum.StrEnum):
    """
    부상이 엔진에 주는 효과의 종류. 엔진이 실제로 집행하는 것은 이것뿐이다.

    "그 손을 못 쓴다" 같은 것은 엔진이 알 수 없다. 행동에는 능력만 있고 몸의 부위는 없다.
    그런 것은 부상의 사실(Injury.fact)로 서술자에게 준다.
    """

    # 정한 능력의 판정에 보정 -amount
    PENALTY = 'penalty'
    # 정한 능력의 판정에서 주사위를 두 번 굴려 낮은 눈을 쓴다
    DISADVANTAGE = 'disadvantage'
    # 행동을 붙일 수 없다. 글만 낼 수 있다(쓰러진 것과 같다)
    NO_ACTIONS = 'no_actions'


class Effect(Part):
    """
    부상의 효과 하나.

    abilities 는 영향을 받는 능력이다. 비우면 모든 능력이다. 행동 불가에는 능력이 없다.
    amount 는 보정을 깎는 크기다. 보정 깎기에만 있다.
    """

    kind: EffectKind
    abilities: Annotated[tuple[Key, ...], Field(max_length=RULESET_MAX_ABILITIES)] = ()
    amount: Annotated[int, Field(ge=0, le=RULESET_MAX_NUMBER)] = 0

    @model_validator(mode='after')
    def require_amount_for_penalty(self) -> Self:
        """보정 깎기에는 크기가 있어야 하고, 다른 효과에는 크기가 없다."""
        if (self.kind == EffectKind.PENALTY) != (self.amount > 0):
            raise ValueError('amount 는 penalty 에만, 1 이상으로 적습니다.')
        return self

    @model_validator(mode='after')
    def reject_abilities_for_no_actions(self) -> Self:
        """행동 불가는 능력을 가리지 않는다."""
        if self.kind == EffectKind.NO_ACTIONS and self.abilities:
            raise ValueError('no_actions 에는 abilities 를 적지 않습니다.')
        return self


class Healing(enum.StrEnum):
    """부상이 낫는 방식."""

    # 짧은 것. 정한 라운드가 지나면 저절로 풀린다(기절, 중독)
    ROUNDS = 'rounds'
    # 오래 가는 것. 정한 라운드가 지나거나 치료를 받으면 낫는다. 나을 때 후유증 표를 굴린다(골절)
    HEALS = 'heals'
    # 결손. 낫지 않는다(손을 잃음)
    PERMANENT = 'permanent'


class TableRow(Part):
    """부상 표의 한 줄. 눈이 low 이상 high 이하면 이 줄이다. injury 가 None 이면 부상이 없다."""

    low: Annotated[int, Field(ge=1, le=RULESET_MAX_DIE)]
    high: Annotated[int, Field(ge=1, le=RULESET_MAX_DIE)]
    injury: Key | None


class InjuryTable(Part):
    """
    부상 표. sides 면 주사위를 한 번 굴려, 그 눈이 든 줄의 부상이 생긴다.

    모든 눈이 정확히 한 줄에 든다. 줄은 낮은 눈부터 빈틈없이 이어진다. "부상 없음" 줄을 넉넉히 두면 자주 다치지 않는다.
    """

    sides: Annotated[int, Field(ge=RULESET_MIN_DIE, le=RULESET_MAX_DIE)]
    rows: Annotated[tuple[TableRow, ...], Field(min_length=1, max_length=RULESET_MAX_TABLE_ROWS)]

    @model_validator(mode='after')
    def require_every_face_once(self) -> Self:
        """줄이 1 부터 sides 까지를 빈틈도 겹침도 없이 차례로 덮어야 한다. 어느 눈이 나와도 줄이 하나로 정해진다."""
        expected = 1
        for row in self.rows:
            if row.low != expected or row.high < row.low:
                raise ValueError(f'부상 표의 줄이 {expected} 부터 이어지지 않습니다.')
            expected = row.high + 1
        if expected != self.sides + 1:
            raise ValueError(f'부상 표가 1 부터 {self.sides} 까지를 덮지 않습니다.')
        return self

    def injury_keys(self) -> set[str]:
        """표에 나오는 부상들."""
        return {row.injury for row in self.rows if row.injury is not None}


class Injury(Part):
    """
    부상 하나. 예: 팔 골절.

    효과(effects)는 엔진이 판정에 적용하고, 사실(fact)은 서술자가 지킨다. 둘을 함께 적는다.
    rounds 는 짧은 것이 풀리기까지, 오래 가는 것이 저절로 낫기까지의 라운드 수다. 결손에는 없다.
    aftermath 는 오래 가는 것이 나을 때 굴리는 후유증 표다. 없으면 깨끗이 낫는다.
    aimable 은 노려 쳐서 일부러 입힐 수 있는 부상인가다.
    시간은 지금 라운드로 센다. 게임 속 달력과 시계가 생기면 그것으로 옮긴다.
    오래 가는 것의 낫기, 후유증, 노려 치기는 다음 단계에서 쓴다(#114 나, 다). 규칙의 모양은 한 번에 정해 둔다.
    """

    key: Key
    name: Name
    fact: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=INJURY_FACT_MAX_LENGTH)]
    effects: Annotated[tuple[Effect, ...], Field(max_length=RULESET_MAX_EFFECTS)] = ()
    healing: Healing
    rounds: Annotated[int, Field(ge=1, le=RULESET_MAX_INJURY_ROUNDS)] | None = None
    aftermath: InjuryTable | None = None
    aimable: bool = False

    @model_validator(mode='after')
    def require_rounds_unless_permanent(self) -> Self:
        """결손이 아니면 라운드 수가 있어야 하고, 결손에는 없다."""
        if (self.healing == Healing.PERMANENT) != (self.rounds is None):
            raise ValueError('rounds 는 결손(permanent)이 아닌 부상에만 적습니다.')
        return self

    @model_validator(mode='after')
    def allow_aftermath_only_when_healing(self) -> Self:
        """후유증 표는 오래 가는 부상에만 있다. 짧은 것은 흔적 없이 풀리고, 결손은 낫지 않는다."""
        if self.aftermath is not None and self.healing != Healing.HEALS:
            raise ValueError('aftermath 는 오래 가는 부상(heals)에만 적습니다.')
        return self


class InjuryTriggers(Part):
    """
    부상 표를 언제 굴리는가. 룰북이 골라 켜고 끈다.

    big_hit_percent: 한 번의 피해(주사위가 정한 양)가 최대 HP 의 이 비율(%) 이상이면 굴린다. None 이면 끈다.
    downed: HP 가 0 이 되어 쓰러질 때 굴린다.
    called_shot: 노려 치기를 허용한다(#114 나).
    한 번의 피해에 여럿이 맞아도 한 번만 굴린다. 죽은 대상에게는 굴리지 않는다.
    """

    big_hit_percent: Annotated[int, Field(ge=1, le=100)] | None
    downed: bool
    called_shot: bool


class CalledShotMode(enum.StrEnum):
    """노려 치기가 판정을 어렵게 하는 방식."""

    # 난이도의 목표값에 amount 를 더한다. 보정이 큰 캐릭터가 유리하다
    TARGET_PLUS = 'target_plus'
    # 주사위를 두 번 굴려 낮은 눈을 쓴다. 능력치와 상관없이 일정하게 어렵다
    DISADVANTAGE = 'disadvantage'


class CalledShot(Part):
    """노려 치기의 어려움. 목표값을 올리는 크기(amount)는 그 방식에만 있다."""

    mode: CalledShotMode
    amount: Annotated[int, Field(ge=0, le=RULESET_MAX_NUMBER)] = 0

    @model_validator(mode='after')
    def require_amount_for_target_plus(self) -> Self:
        """목표값을 올리는 방식에는 크기가 있어야 하고, 불리함에는 없다."""
        if (self.mode == CalledShotMode.TARGET_PLUS) != (self.amount > 0):
            raise ValueError('amount 는 target_plus 에만, 1 이상으로 적습니다.')
        return self


class Ruleset(Part):
    """
    규칙 한 벌.

    template 은 어느 템플릿에서 왔는지를 적어 둔 것이다(app/engine/templates.py). 엔진은 이 값을 보지 않는다.
    """

    template: Key
    # 능력치들. 시트는 이 목록의 능력치를 빠짐없이 가져야 한다
    abilities: Annotated[tuple[Ability, ...], Field(min_length=1, max_length=RULESET_MAX_ABILITIES)]
    # 능력치의 점수가 가질 수 있는 범위
    score_min: Number
    score_max: Number
    modifier: Modifier
    # 판정에 굴리는 주사위의 면 수. 20 이면 d20 이다
    die: Annotated[int, Field(ge=RULESET_MIN_DIE, le=RULESET_MAX_DIE)]
    # 난이도의 단계들. 행동은 숫자가 아니라 이 중 하나를 고른다
    difficulties: Annotated[tuple[Difficulty, ...], Field(min_length=1, max_length=RULESET_MAX_DIFFICULTIES)]
    # 행동이 난이도를 고르지 않았을 때 쓰는 단계
    default_difficulty: Key
    # 피해와 회복의 양을 나타내는 등급들. 행동은 숫자가 아니라 이 중 하나를 고른다
    magnitudes: Annotated[tuple[Magnitude, ...], Field(min_length=1, max_length=RULESET_MAX_MAGNITUDES)]
    # 최대 HP 에 보정을 더하는 능력치. 플레이어가 능력치를 정한 캐릭터의 최대 HP 를 구할 때 쓴다.
    # None 이면 능력치가 최대 HP 에 닿지 않는다. 칸 자체는 늘 있어야 한다(기본값이 없다)
    hp_ability: Key | None
    # 점수제. None 이면 이 규칙에는 점수제가 없다. 칸 자체는 늘 있어야 한다(기본값이 없다)
    point_buy: PointBuy | None
    # 능력치의 점수를 주사위로 정하는 법. None 이면 이 규칙에는 그런 방식이 없다. 칸 자체는 늘 있어야 한다
    score_roll: ScoreRoll | None
    # 죽음의 굴림. None 이면 이 규칙에서는 주사위가 캐릭터를 죽이지 않는다. 쓰러진 채로 있다.
    # 칸 자체는 늘 있어야 한다
    death_save: DeathSave | None
    # 부상들. 비어 있으면 이 규칙에는 부상이 없다
    injuries: Annotated[tuple[Injury, ...], Field(max_length=RULESET_MAX_INJURIES)]
    # 큰 타격이나 쓰러짐에 굴리는 부상 표. None 이면 표가 없다
    injury_table: InjuryTable | None
    # 부상 표를 언제 굴리는가
    injury_triggers: InjuryTriggers
    # 노려 치기의 어려움. None 이면 노려 치기가 없다
    called_shot: CalledShot | None

    @model_validator(mode='after')
    def reject_duplicate_abilities(self) -> Self:
        """같은 이름의 능력치가 둘이면 시트가 어느 것을 가리키는지 알 수 없다."""
        duplicates = find_duplicates([ability.key for ability in self.abilities])
        if duplicates:
            raise ValueError(f'같은 능력치가 두 번 있습니다: {", ".join(duplicates)}')
        return self

    @model_validator(mode='after')
    def reject_duplicate_difficulties(self) -> Self:
        """같은 이름의 난이도가 둘이면 행동이 어느 것을 고른 것인지 알 수 없다."""
        duplicates = find_duplicates([difficulty.key for difficulty in self.difficulties])
        if duplicates:
            raise ValueError(f'같은 난이도가 두 번 있습니다: {", ".join(duplicates)}')
        return self

    @model_validator(mode='after')
    def reject_duplicate_magnitudes(self) -> Self:
        """같은 이름의 등급이 둘이면 행동이 어느 것을 고른 것인지 알 수 없다."""
        duplicates = find_duplicates([magnitude.key for magnitude in self.magnitudes])
        if duplicates:
            raise ValueError(f'같은 양의 등급이 두 번 있습니다: {", ".join(duplicates)}')
        return self

    @model_validator(mode='after')
    def require_known_hp_ability(self) -> Self:
        """최대 HP 에 닿는 능력치는 능력치 중 하나여야 한다."""
        if self.hp_ability is not None and self.hp_ability not in [ability.key for ability in self.abilities]:
            raise ValueError(f'최대 HP 에 닿는 능력치가 능력치에 없습니다: {self.hp_ability}')
        return self

    @model_validator(mode='after')
    def require_purchasable_scores_in_range(self) -> Self:
        """점수제로 살 수 있는 점수는 규칙의 점수 범위 안이어야 한다. 범위 밖의 점수는 시트에 넣을 수 없다."""
        if self.point_buy is None:
            return self
        outside = [entry.score for entry in self.point_buy.costs if not self.score_min <= entry.score <= self.score_max]
        if outside:
            raise ValueError(f'점수제의 값표에 점수의 범위를 벗어난 점수가 있습니다: {outside}')
        return self

    @model_validator(mode='after')
    def require_rolled_scores_in_range(self) -> Self:
        """
        주사위로 나올 수 있는 점수는 모두 규칙의 점수 범위 안이어야 한다.

        가장 작은 것은 더하는 주사위가 모두 1 일 때, 가장 큰 것은 모두 가장 큰 눈일 때다.
        범위 밖의 점수가 나올 수 있으면, 서버가 굴린 값을 시트에 넣지 못하는 일이 생긴다.
        """
        if self.score_roll is None:
            return self
        lowest, highest = self.score_roll.keep, self.score_roll.keep * self.score_roll.sides
        if lowest < self.score_min or highest > self.score_max:
            raise ValueError(f'주사위로 나올 수 있는 점수({lowest}~{highest})가 점수의 범위를 벗어납니다.')
        return self

    @model_validator(mode='after')
    def require_survivable_death_save(self) -> Self:
        """죽음의 굴림은 성공할 수 있어야 한다. 목표값이 주사위의 가장 큰 눈보다 크면 쓰러진 캐릭터는 반드시 죽는다."""
        if self.death_save is not None and self.death_save.target > self.die:
            raise ValueError('죽음의 굴림의 목표값이 주사위의 가장 큰 눈보다 큽니다.')
        return self

    @model_validator(mode='after')
    def require_score_range(self) -> Self:
        """점수의 범위가 뒤집혀 있으면 어떤 점수도 들어갈 수 없다."""
        if self.score_min > self.score_max:
            raise ValueError('점수의 가장 작은 값이 가장 큰 값보다 큽니다.')
        return self

    @model_validator(mode='after')
    def reject_duplicate_injuries(self) -> Self:
        """같은 이름의 부상이 둘이면 표와 기록이 어느 것을 가리키는지 알 수 없다."""
        duplicates = find_duplicates([injury.key for injury in self.injuries])
        if duplicates:
            raise ValueError(f'같은 부상이 두 번 있습니다: {", ".join(duplicates)}')
        return self

    @model_validator(mode='after')
    def require_known_effect_abilities(self) -> Self:
        """부상의 효과가 가리키는 능력은 능력치 중 하나여야 한다."""
        known = {ability.key for ability in self.abilities}
        unknown = sorted(
            {key for injury in self.injuries for effect in injury.effects for key in effect.abilities} - known
        )
        if unknown:
            raise ValueError(f'부상의 효과가 가리키는 능력이 능력치에 없습니다: {", ".join(unknown)}')
        return self

    @model_validator(mode='after')
    def require_known_table_injuries(self) -> Self:
        """부상 표와 후유증 표에 나오는 부상은 부상 중 하나여야 한다."""
        known = {injury.key for injury in self.injuries}
        tables = [self.injury_table, *(injury.aftermath for injury in self.injuries)]
        unknown = sorted({key for table in tables if table is not None for key in table.injury_keys()} - known)
        if unknown:
            raise ValueError(f'표에 나오는 부상이 부상에 없습니다: {", ".join(unknown)}')
        return self

    @model_validator(mode='after')
    def require_table_for_triggers(self) -> Self:
        """큰 타격이나 쓰러짐에 굴리게 켰으면 굴릴 표가 있어야 한다."""
        triggers = self.injury_triggers
        if (triggers.big_hit_percent is not None or triggers.downed) and self.injury_table is None:
            raise ValueError('부상 표를 굴리게 켰는데 부상 표가 없습니다.')
        return self

    @model_validator(mode='after')
    def require_called_shot_setup(self) -> Self:
        """노려 치기를 켰으면 어려움을 정하는 법과 노릴 수 있는 부상이 하나는 있어야 한다."""
        if not self.injury_triggers.called_shot:
            return self
        if self.called_shot is None or not any(injury.aimable for injury in self.injuries):
            raise ValueError('노려 치기를 켰는데 어려움을 정하는 법이나 노릴 수 있는 부상이 없습니다.')
        return self

    @model_validator(mode='after')
    def require_known_default(self) -> Self:
        """기본 난이도는 난이도의 단계 중 하나여야 한다."""
        if self.default_difficulty not in [difficulty.key for difficulty in self.difficulties]:
            raise ValueError(f'기본 난이도가 난이도의 단계에 없습니다: {self.default_difficulty}')
        return self
