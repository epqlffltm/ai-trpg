# game-server/app/engine/ruleset.py

"""
규칙의 모양. 규칙은 코드가 아니라 데이터다.

어떤 능력치가 있는지, 주사위가 몇 면인지, 난이도가 몇 단계인지, 피해와 회복이 얼마인지,
캐릭터의 숫자를 어떻게 정하는지, 쓰러진 캐릭터가 어떻게 죽는지를 한 묶음(Ruleset)에 담는다.
엔진은 이 묶음을 인자로 받는다. 묶음의 값이 달라져도 엔진의 코드는 그대로다.

규칙은 룰북에 담기고(app/assets/models.py 의 Rulebook.rules), 게시할 때 판에 굳는다.
DB 에는 문서(JSON)로 들어간다. DB 는 문서의 안을 검증하지 못한다.
그래서 쓰는 쪽과 읽는 쪽이 모두 이 파일의 모양을 거친다. 이 파일이 규칙의 계약이다.

바꿀 수 있는 것은 값이다. 계산하는 방식(주사위 + 보정이 난이도 이상이면 성공)은 엔진의 코드에 있다.
"""

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
    def require_known_default(self) -> Self:
        """기본 난이도는 난이도의 단계 중 하나여야 한다."""
        if self.default_difficulty not in [difficulty.key for difficulty in self.difficulties]:
            raise ValueError(f'기본 난이도가 난이도의 단계에 없습니다: {self.default_difficulty}')
        return self
