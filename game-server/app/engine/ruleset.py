# game-server/app/engine/ruleset.py

"""
규칙의 모양. 규칙은 코드가 아니라 데이터다.

어떤 능력치가 있는지, 주사위가 몇 면인지, 난이도가 몇 단계인지, 피해와 회복이 얼마인지를 한 묶음(Ruleset)에 담는다.
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
