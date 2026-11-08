# trpg-server/app/engine/dice_notation.py

"""
주사위 설명(#404). "2d6+1" 같은 글을 정해진 모양으로 읽고 검증하고, 서버의 주사위로 굴린다.

자유 굴림(app/tables/free_rolls.py)이 쓴다. 게임의 상태와 무관하다. 판정도 피해도 아니다.
받는 모양은 하나다: [개수]d면수[+보정 또는 -보정]. 개수를 비우면 하나다. 대소문자와 앞뒤 공백은 가리지 않는다.
여러 묶음(2d6+1d4), 곱하기, 버리기(4d6kh3)는 받지 않는다. 받는 모양을 넓힐 때는 읽는 곳만 고친다.

여기의 함수는 DB 도 HTTP 도 모른다. 주사위만 밖에서 받는다. 같은 눈을 주면 같은 결과가 나온다.
"""

import re
from dataclasses import dataclass

from app.engine.dice import Dice

# 굴릴 수 있는 면 수. 흔한 다면체 주사위만 받는다
ALLOWED_SIDES = (4, 6, 8, 10, 12, 20, 100)
# 한 번에 굴리는 주사위의 개수 상한
MAX_COUNT = 10
# 더하거나 빼는 보정의 상한(절댓값)
MAX_BONUS = 100
# 받는 글의 길이 상한. "10d100+100" 이 가장 길다
MAX_LENGTH = 16

NOTATION = re.compile(r'(?P<count>\d{1,2})?d(?P<sides>\d{1,3})(?P<bonus>[+-]\d{1,3})?')


class NotationError(ValueError):
    """주사위 설명이 받는 모양이 아니다. 까닭(reason)으로 무엇이 틀렸는지 가린다."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Notation:
    """읽은 주사위 설명. 면 수가 sides 인 주사위 count 개를 굴려 더하고 bonus 를 더한다."""

    count: int
    sides: int
    bonus: int

    @property
    def text(self) -> str:
        """다시 쓴 설명. 개수가 하나면 적지 않고, 보정이 0 이면 적지 않는다. "d20", "2d6+1", "3d8-2"."""
        count = '' if self.count == 1 else str(self.count)
        bonus = '' if self.bonus == 0 else f'{self.bonus:+d}'
        return f'{count}d{self.sides}{bonus}'


@dataclass(frozen=True)
class Rolled:
    """굴린 결과. 눈들과 보정과 합."""

    notation: Notation
    faces: tuple[int, ...]

    @property
    def total(self) -> int:
        """눈들의 합에 보정을 더한 값."""
        return sum(self.faces) + self.notation.bonus


def parse(text: str) -> Notation:
    """
    주사위 설명을 읽는다. 받는 모양이 아니면 NotationError.

    까닭: format(모양이 틀림), count(개수가 1~MAX_COUNT 밖), sides(면 수가 ALLOWED_SIDES 에 없음),
    bonus(보정이 -MAX_BONUS~MAX_BONUS 밖).
    """
    cleaned = text.strip().lower()
    matched = NOTATION.fullmatch(cleaned) if len(cleaned) <= MAX_LENGTH else None
    if matched is None:
        raise NotationError('format')
    notation = Notation(count=int(matched['count'] or 1), sides=int(matched['sides']), bonus=int(matched['bonus'] or 0))
    check_bounds(notation)
    return notation


def check_bounds(notation: Notation) -> None:
    """읽은 설명이 상한 안인가. 아니면 NotationError."""
    if not 1 <= notation.count <= MAX_COUNT:
        raise NotationError('count')
    if notation.sides not in ALLOWED_SIDES:
        raise NotationError('sides')
    if abs(notation.bonus) > MAX_BONUS:
        raise NotationError('bonus')


def roll(notation: Notation, dice: Dice) -> Rolled:
    """설명대로 서버의 주사위를 굴린다. 굴린 순서대로 눈을 담는다."""
    return Rolled(notation=notation, faces=tuple(dice.roll(notation.sides) for _ in range(notation.count)))
